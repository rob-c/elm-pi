"""agent/extensions/workflow-script.ts: a `workflow` script given by its checked file, a prompt that names
text it is never given, and the line a syntax error points at. All three from test15 (2026-11-13).

The parser check needs acorn, which comes with pi-dynamic-workflows: those tests skip in a checkout that
has not been bootstrapped.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "templates/extensions"
AGENT = ROOT / "agent"
HAS_ACORN = (AGENT / "npm/node_modules/acorn").exists()

# test15's script, cut down: the page task names sharedStyles, and nothing puts its text in the task.
TEST15 = """export const meta = { name: "dinosaur_website", description: "A five-page dinosaur website" };

const sharedStyles = `/* Global styles - must be identical across all pages */
body { font-family: 'Georgia', serif; line-height: 1.6; }`;

const buildPage = (pageName) => `Create the ${pageName} page for a dinosaur website.

Write to: site/${pageName}.html

Requirements:
- Use the EXACT same CSS as all other pages (copy sharedStyles verbatim into <style> tag)`;

const pages = await parallel(["index", "facts"].map((p) => () => agent(buildPage(p))));
return { report: pages.join("\\n") };
"""
FIXED = TEST15.replace("(copy sharedStyles verbatim into <style> tag)", "- put this CSS in a <style> tag:\n${sharedStyles}")

RUNNER = r"""
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[1]).href);
const h = {};
m.default({ on: (e, f) => { h[e] = f; } });
const [steps, cwd] = [JSON.parse(process.argv[2]), process.argv[3]];
const out = [];
for (const step of steps) {
  if (step.error) {
    const r = await h.tool_result({ toolName: "workflow", isError: true, input: step.input,
                                   content: [{ type: "text", text: step.error }] }, { cwd });
    out.push(r ? r.content.map((c) => c.text).join("\n") : null);
  } else {
    const input = step.input;
    const r = await h.tool_call({ toolName: step.tool ?? "workflow", input }, { cwd });
    out.push({ block: r?.block ? r.reason : null, script: input.script });
  }
}
console.log(JSON.stringify(out));
"""


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


class WorkflowScriptTests(unittest.TestCase):
    def setUp(self):
        self.binary = node()
        if not self.binary:
            self.skipTest("needs node")
        self.cwd = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.cwd)
        (self.cwd / ".pi/tmp").mkdir(parents=True)

    def node(self, script, *args, source=EXT / "workflow-script.ts"):
        run = subprocess.run([self.binary, "--no-warnings", "--input-type=module", "-e", script, str(source), *args],
                             capture_output=True, text=True, timeout=60,
                             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PI_CODING_AGENT_DIR": str(AGENT)})
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        return json.loads(run.stdout.strip().splitlines()[-1])

    def steps(self, steps):
        return self.node(RUNNER, json.dumps(steps), str(self.cwd))

    def test_the_checked_file_named_as_script_is_what_runs(self):
        (self.cwd / ".pi/tmp/site.mjs").write_text(FIXED)
        named, = self.steps([{"input": {"script": ".pi/tmp/site.mjs"}}])
        self.assertIsNone(named["block"])
        self.assertEqual(FIXED, named["script"])
        quoted, absolute = self.steps([{"input": {"script": '".pi/tmp/site.mjs"'}},
                                       {"input": {"script": str(self.cwd / ".pi/tmp/site.mjs")}}])
        self.assertEqual(FIXED, quoted["script"])
        self.assertEqual(FIXED, absolute["script"])

    def test_a_named_file_that_is_not_there_is_refused(self):
        missing, = self.steps([{"input": {"script": ".pi/tmp/nope.mjs"}}])
        self.assertEqual("No file .pi/tmp/nope.mjs: write the script there, check it with `workflow-check`, and pass "
                         "that path as `script`.", missing["block"])

    def test_a_script_given_as_text_runs_as_given(self):
        inline, = self.steps([{"input": {"script": FIXED}}])
        self.assertIsNone(inline["block"])
        self.assertEqual(FIXED, inline["script"])

    def test_a_prompt_that_names_text_it_is_never_given_is_not_started(self):
        if not HAS_ACORN:
            self.skipTest("acorn comes with pi-dynamic-workflows (run bootstrap.sh)")
        (self.cwd / ".pi/tmp/site.mjs").write_text(TEST15)
        refused, by_file, fixed = self.steps([{"input": {"script": TEST15}}, {"input": {"script": ".pi/tmp/site.mjs"}},
                                              {"input": {"script": FIXED}}])
        self.assertEqual(
            "Not started: `sharedStyles` is never used, so no agent gets its text - yet a prompt says \"- Use the EXACT "
            "same CSS as all other pages (copy sharedStyles verbatim into <style> tag)\". An agent sees only its prompt: "
            "put ${sharedStyles} in the prompt where the text belongs, check the script again, and call `workflow` again.",
            refused["block"])
        self.assertEqual(refused["block"], by_file["block"])
        self.assertIsNone(fixed["block"])

    def test_an_unused_constant_no_prompt_names_and_a_named_one_that_is_passed_go_through(self):
        if not HAS_ACORN:
            self.skipTest("acorn comes with pi-dynamic-workflows (run bootstrap.sh)")
        spare = FIXED.replace("const buildPage", "const note = `kept for later`;\nconst buildPage")
        both = FIXED.replace("- put this CSS", "- sharedStyles, below, is the CSS; put this CSS")
        keyed = TEST15.replace("const pages =", "const opts = { sharedStyles: 1 };\nconst pages =")
        out = self.steps([{"input": {"script": spare}}, {"input": {"script": both}}, {"input": {"script": keyed}}])
        self.assertEqual([None, None], [o["block"] for o in out[:2]])
        self.assertIn("`sharedStyles` is never used", out[2]["block"])  # an object key is not a use

    def test_a_syntax_error_shows_the_line_it_points_at(self):
        # test15's retyped copy: the last template literal escaped as \` and \${, which the file had not
        broken = "export const meta = { name: 'x', description: 'x' };\nconst a = await agent('x');\n" \
                 "return { report: \\`## Done\\n\\${a}\\` };\n"
        shown, other = self.steps([
            {"input": {"script": broken}, "error": "Expecting Unicode escape sequence \\uXXXX (3:18)"},
            {"input": {"script": broken}, "error": "Workflow failed: agent quota exhausted"}])
        self.assertIn("Expecting Unicode escape sequence \\uXXXX (3:18)\n\nLine 3 of the script:\n"
                      "return { report: \\`## Done\\n\\${a}\\` };\n" + " " * 18 + "^", shown)
        self.assertIn("pass the file's path as `script`", shown)
        self.assertIsNone(other)

    def test_the_other_readers_of_a_script_read_the_named_file_too(self):
        """pi loads a folder's extensions in no set order, so permission-mode and report-guard may see the path."""
        writes = TEST15.replace("const pages", "const report = await agent(`Write site/VERIFICATION_REPORT.md`);\nconst pages")
        (self.cwd / ".pi/tmp/site.mjs").write_text(writes)
        script = ("import { pathToFileURL } from 'node:url';"
                  "const p = await import(pathToFileURL(process.argv[1]).href);"
                  "const r = await import(pathToFileURL(process.argv[2]).href);"
                  "const input = { script: '.pi/tmp/site.mjs' };"
                  "console.log(JSON.stringify([p.workflowRefusal('manual', input, {}, process.argv[3]) ?? null,"
                  " r.delegatedReports('workflow', input, process.argv[3])]));")
        refusal, reports = self.node(script, str(EXT / "report-guard.ts"), str(self.cwd), source=EXT / "permission-mode.ts")
        self.assertIn("Not started: this session is in manual mode", refusal)
        self.assertEqual(["VERIFICATION_REPORT.md"], reports)

    def test_the_prompts_say_to_pass_the_path(self):
        agents = " ".join((ROOT / "templates/AGENTS.md").read_text().split())
        skill = " ".join((ROOT / "templates/skills/elm-dynamic-workflows/SKILL.md").read_text().split())
        check = (ROOT / "scripts/workflow-check.mjs").read_text()
        self.assertIn("once it prints `ok` pass that path, not the text, as `script`", agents)
        self.assertIn('call `workflow({ script: ".pi/tmp/<name>.mjs" })` - the path, not the text', skill)
        self.assertIn("**An agent gets only its prompt.**", skill)
        self.assertIn('Run it with workflow({ script: "${file}" }) - the path, not the text', check)


if __name__ == "__main__":
    unittest.main()
