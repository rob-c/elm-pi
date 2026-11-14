"""owner-guard.ts, run under node with a stub pi: a file named in a running child's task is that child's.

The branches here have the shape of test6's (2026-11-12): a parent that started five
qwen children with the parallel workflow, one page of a website each, and a child
forked from it - the user's request, the parent's call and its launch result, then
the child's own task behind pi-subagents' fork preamble. In test6 two children
rewrote their siblings' pages and the stylesheet, and the parent edited a page whose
child was still running.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "templates/extensions/owner-guard.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
SITE = "/work/site"
RUN = "3eab4ab2-e55b-4a4e-8df3-edfb7fad6fa0"
PAGES = ["index", "species", "habitat", "lifecycle", "conservation"]
PREAMBLE = ("You are a delegated subagent running from a fork of the parent session. Treat the inherited "
            "conversation as reference-only context, not a live thread to continue. Do not continue or answer "
            "prior messages as if they are waiting for a reply. Your sole job is to execute the task below and "
            "return a focused result for that task using your tools.")


def task(page, site=SITE):
    return (f"Create the {page.title()} page ({page}.html) for a frog website. Include: navigation menu (same as "
            f"all pages), header, content. Use the same CSS classes and structure as other pages for consistency. "
            f"Save to {site}/{page}.html. Report the file path.")


# test7: each task lists every page for the navigation bar, and names the shared stylesheet
SITE7 = ["index", "about", "care", "gallery", "contact"]


def task7(page, site=SITE):
    return (f"Create {page}.html ({page.title()} page) for an alpaca website. Use the shared styles.css file already "
            f"created at {site}/styles.css. Include:\n\n1. IDENTICAL navigation bar to all other pages with links to: "
            f"index.html, about.html, care.html, gallery.html, contact.html\n2. Page title\n\nUse these exact colors "
            f"from styles.css.\nLink to styles.css with: <link rel=\"stylesheet\" href=\"styles.css\">\n\n"
            f"Write the complete HTML file to {site}/{page}.html. Read-only on styles.css.")


def stamp(minutes):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - minutes * 60))


def msg(role, content, **extra):
    return {"type": "message", "timestamp": stamp(extra.pop("ago", 1)), "message": {"role": role, "content": content, **extra}}


def parent_branch(site=SITE, ago=1, tasks=None):
    """The user's request, the parallel call, and its launch result."""
    tasks = tasks or [task(p, site) for p in PAGES]
    call = {"type": "toolCall", "id": "call-1", "name": "subagent",
            "arguments": {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": t} for t in tasks]}}}
    return [
        msg("user", [{"type": "text", "text": "use 5 agents make me a website about frogs"}], ago=ago),
        msg("assistant", [{"type": "text", "text": "Launching 5 agents."}, call], ago=ago),
        msg("toolResult", [{"type": "text", "text": f"Run fan-out: 0/64 used\nAsync workflow [{RUN}]\n\nDetached. Return control now"}],
            toolCallId="call-1", toolName="subagent", isError=False, ago=ago),
    ]


def child_branch(page, site=SITE, make=task):
    pages = SITE7 if make is task7 else PAGES
    return (parent_branch(site, tasks=[make(p, site) for p in pages])
            + [msg("user", [{"type": "text", "text": f"{PREAMBLE}\n\nTask:\n{make(page, site)}"}])])


def child_start(page, site=SITE, make=task):
    """pi's order: before_agent_start sees the task only as its prompt; the branch gets it after."""
    branch = child_branch(page, site, make)
    return [{"branch": branch[:-1]}, {"start": True, "prompt": branch[-1]["message"]["content"][0]["text"]},
            {"add": [branch[-1]]}]


def child_done(key):
    return {"type": "custom_message", "customType": "subagent-incremental-child-notify", "timestamp": stamp(0),
            "content": f"Workflow child completed: **{key}**\nWorkflow run: {RUN}\nChild run: 563d6778-8ec2-4a2b-b663-5024064cd9ae\n"
                       "Status: workflow still running"}


RUN_DONE = {"type": "custom_message", "customType": "subagent-notify", "timestamp": stamp(0),
            "content": f"Background task completed: **workflow**\nWorkflow receipt: /tmp/runs/{RUN}/workflow-receipt.json"}
NEEDS_ATTENTION = {"type": "custom_message", "customType": "subagent_control_notice", "timestamp": stamp(0),
                   "content": f"Subagent needs attention: qwen\nRun: {RUN} step 1\nSignal: no observed activity for 175s"}

# A stub pi and session; SCENARIO (a JSON list of steps) drives the handlers and prints each answer.
DRIVER = r"""
import { pathToFileURL } from "node:url";
import { writeFileSync, utimesSync } from "node:fs";
const m = await import(pathToFileURL(process.argv[1]).href);
const steps = JSON.parse(process.argv[2]);
const h = {};
m.default({ on: (event, f) => { h[event] = f; }, getActiveTools: () => (process.env.ACTIVE_TOOLS ?? "read,bash,write,subagent").split(",") });
let branch = [];
const ctx = () => ({ cwd: process.env.SITE, hasUI: true, sessionManager: { getBranch: () => branch } });
const out = [];
let n = 0;
for (const s of steps) {
  if (s.branch) branch = s.branch;
  if (s.add) branch = [...branch, ...s.add];
  if (s.touch) { writeFileSync(s.touch, "x"); if (s.age) utimesSync(s.touch, new Date(Date.now() - s.age), new Date(Date.now() - s.age)); }
  if (s.wait) await new Promise((r) => setTimeout(r, s.wait));
  if (s.start) {
    // pi's order: a turn a custom message starts sees it as event.message; the branch gets it after.
    const message = s.message ? { role: "custom", customType: s.message.customType, content: s.message.content, display: true } : undefined;
    const r = await h.before_agent_start({ type: "before_agent_start", messageType: s.start === "custom" ? "custom" : "user", prompt: s.prompt ?? "x", message }, ctx());
    out.push(r?.message ?? null);
    if (s.message) branch = [...branch, s.message];
    if (r?.message) branch = [...branch, { type: "custom_message", customType: r.message.customType, content: r.message.content }];
  }
  if (s.launch) {
    const r = await h.tool_call({ type: "tool_call", toolCallId: `l${n++}`, toolName: "subagent", input: s.launch }, ctx());
    out.push(r?.block ? r.reason : null);
  }
  if (s.tool) {
    const id = `t${n++}`;
    const r = await h.tool_call({ type: "tool_call", toolCallId: id, toolName: s.tool, input: s.input }, ctx());
    if (s.during) writeFileSync(s.during, "made by my own command");
    const res = await h.tool_result({ type: "tool_result", toolCallId: id, toolName: s.tool, input: s.input,
      content: s.output ? [{ type: "text", text: s.output }] : [], isError: !!r?.block }, ctx());
    out.push(r?.block ? r.reason : res?.content ? res.content[res.content.length - 1].text : null);
  }
}
console.log(JSON.stringify(out));
"""


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


class OwnerGuardTests(unittest.TestCase):
    def run_node(self, script, *args, env=None):
        binary = node()
        if not binary:
            self.skipTest("needs node")
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, *map(str, args)],
                             capture_output=True, text=True, timeout=60, cwd=ROOT, env={**os.environ, **(env or {})})
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        return json.loads(run.stdout)

    def scenario(self, steps, site, child, ledger=None, tools=None):
        env = {"SITE": site, "PI_SUBAGENT_CHILD": "1" if child else "", "ELM_PI_LEDGER_DIR": ledger or f"{site}/.ledger"}
        if tools:
            env["ACTIVE_TOOLS"] = ",".join(tools)
        return self.run_node(DRIVER, GUARD, json.dumps(steps), env=env)

    def call(self, fn, *args):
        script = ("import { pathToFileURL } from 'node:url';"
                  "const m = await import(pathToFileURL(process.argv[1]).href);"
                  f"const r = m.{fn}(...JSON.parse(process.argv[2]));"
                  "console.log(JSON.stringify(r instanceof Map ? Object.fromEntries(r) : r, "
                  "(k, v) => v instanceof Set ? [...v] : v instanceof Map ? Object.fromEntries(v) : v));")
        return self.run_node(script, GUARD, json.dumps(args))

    # -- what a task names

    def test_the_files_a_task_names(self):
        cases = {
            task("species"): [f"{SITE}/species.html"],
            "Write plots/fit.png and ./report.md from data.csv": [f"{SITE}/plots/fit.png", f"{SITE}/report.md", f"{SITE}/data.csv"],
            "Fix ~/proj/a.py; see https://example.org/docs/page.html": ["/home/u/proj/a.py"],
            "Explain what changed in version 1.2 and why.": [],
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(want, self.call("namedPaths", text, SITE, "/home/u"))

    def test_a_task_owns_what_it_says_to_make_not_what_it_mentions(self):
        cases = {
            task7("gallery"): [f"{SITE}/gallery.html"],                     # not the four pages its nav links to
            task("species"): [f"{SITE}/species.html"],
            "Write plots/fit.png and ./report.md from data.csv": [f"{SITE}/plots/fit.png", f"{SITE}/report.md"],
            "Fix the bug where parser.py crashes when reading data.csv": [f"{SITE}/parser.py"],
            "Create about.html with the same navigation as index.html": [f"{SITE}/about.html"],
            "Review src/app.py and report what is wrong.": [],
        }
        for text, want in cases.items():
            with self.subTest(text=text[:50]):
                self.assertEqual(want, self.call("outputPaths", text, SITE, "/home/u"))
        # with no output to tell apart, every path the task names is its own
        self.assertEqual([f"{SITE}/src/app.py"], self.call("ownedPaths", {"key": "", "text": "Review src/app.py.", "cwd": SITE}, "/home/u"))

    def test_test7_child_cannot_take_a_sibling_page_its_nav_links_to(self):
        """test7: every task listed all five pages; task 4 rewrote task 2's about.html and edited two more."""
        with tempfile.TemporaryDirectory() as site:
            out = self.scenario([
                *child_start("gallery", site, make=task7),
                {"tool": "write", "input": {"path": f"{site}/about.html", "content": "x"}},
                {"tool": "replace_match", "input": {"path": f"{site}/contact.html", "match": "a", "replacement": "b"}},
                {"tool": "write", "input": {"path": f"{site}/gallery.html", "content": "x"}},
            ], site, child=True)
            ledger = [json.loads(l) for l in Path(f"{site}/.ledger/{RUN}.jsonl").read_text().splitlines()]
        note, about, contact, gallery = out
        self.assertIn("Yours is task-4", note["content"])
        self.assertIn("task-2: about.html", note["content"])
        self.assertIn("do not wait for it, poll for it or write it", note["content"])
        self.assertIn("about.html is task-2's file", about)
        self.assertIn("contact.html is task-5's file", contact)
        self.assertIsNone(gallery)
        self.assertEqual([("about.html", "task-2's"), ("contact.html", "task-5's"), ("gallery.html", None)],
                         [(Path(l["path"]).name, l.get("refused")) for l in ledger])
        self.assertEqual({"task-4"}, {l["key"] for l in ledger})

    def test_the_parent_hears_who_wrote_what_when_the_run_ends(self):
        with tempfile.TemporaryDirectory() as site:
            ledger = Path(f"{site}/.ledger"); ledger.mkdir()
            lines = [{"key": "task-1", "path": f"{site}/index.html", "tool": "write"},
                     {"key": "task-4", "path": f"{site}/gallery.html", "tool": "write"},
                     {"key": "task-4", "path": f"{site}/README.md", "tool": "write"},
                     {"key": "task-4", "path": f"{site}/about.html", "tool": "write", "refused": "task-2's"}]
            (ledger / f"{RUN}.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines))
            branch = parent_branch(site, tasks=[task7(p, site) for p in SITE7])
            # test8/test9: the run's final notice starts the turn, and pi adds it to the branch only after
            # before_agent_start - an earlier version looked for it there and never told the parent.
            out = self.scenario([{"branch": branch}, {"start": "custom", "message": child_done("task-1")},   # still running
                                 {"start": "custom", "message": RUN_DONE},
                                 {"start": "user"}],                              # told once
                                site, child=False)
        running, done, again = out
        self.assertIsNone(running)
        self.assertIsNone(again)
        text = done["content"]
        self.assertIn("# What the children of run 3eab4ab2 wrote", text)
        self.assertIn("- task-1: index.html", text)
        self.assertIn("- task-4: gallery.html; also README.md, which its task does not name; refused: about.html (task-2's)", text)
        self.assertIn("- task-3: none of its own files", text)

    def test_in_print_mode_the_parent_hears_it_with_bg_wait(self):
        # live 2026-11-12: under `pi -p` the parent waits in its turn; bg_wait names the runs it saw end
        with tempfile.TemporaryDirectory() as site:
            ledger = Path(f"{site}/.ledger"); ledger.mkdir()
            (ledger / f"{RUN}.jsonl").write_text(json.dumps({"key": "task-2", "path": f"{site}/about.html", "tool": "write"}) + "\n")
            waited = (f"Waited 23.3s for 1 async run(s); done. Outcome: 1 complete.\n"
                      f"Workflow receipt [{RUN}]: /tmp/runs/{RUN}/workflow-receipt.json")
            out = self.scenario([{"branch": parent_branch(site, tasks=[task7(p, site) for p in SITE7])},
                                 {"tool": "bg_wait", "input": {"all": True}, "output": "Waited 1s; 1 still running."},
                                 {"tool": "bg_wait", "input": {"all": True}, "output": waited}], site, child=False)
        self.assertIsNone(out[0])
        self.assertIn("# What the children of run 3eab4ab2 wrote", out[1])
        self.assertIn("- task-2: about.html", out[1])

    # -- what children started side by side share

    def gaps(self, site, launch):
        return self.scenario([{"branch": []}, {"launch": launch}], site, child=False)[0]

    @staticmethod
    def parallel(tasks):
        return {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": t} for t in tasks]}}

    def test_test8_children_told_to_share_a_stylesheet_nobody_had_written_are_not_started(self):
        with tempfile.TemporaryDirectory() as site:
            pages = ["index", "species", "habitat"]
            tasks = [f"Create the {p} page ({p}.html) for a Scottish deer website. Use consistent navigation and "
                     f"footer. Link to shared CSS. Save to {site}/{p}.html" for p in pages]
            reason = self.gaps(site, self.parallel(tasks))
        self.assertIn("Not launched: children started side by side cannot see each other's files", reason)
        self.assertIn('- task-1, task-2 and task-3 are told to share "consistent navigation", "shared css", '
                      "but name no existing file to take it from.", reason)
        self.assertIn("Write those first - the stylesheet, and one finished page or a template", reason)

    def test_test9_a_stylesheet_one_child_writes_while_the_others_build_on_it(self):
        with tempfile.TemporaryDirectory() as site:
            tasks = [f"Create {p}.html. All pages share css/style.css. Write to {site}/{p}.html only." for p in ("index", "about")]
            tasks.append(f"Create two files: contact.html and css/style.css. Write to {site}/contact.html and {site}/css/style.css only.")
            reason = self.gaps(site, self.parallel(tasks))
        self.assertIn("- css/style.css: named by task-1, task-2 and task-3, and not there yet "
                      "(task-3 is to write it, while the others build on it).", reason)

    def test_test7_children_given_the_stylesheet_already_written_are_started(self):
        with tempfile.TemporaryDirectory() as site:
            Path(f"{site}/styles.css").write_text("body {}")
            self.assertIsNone(self.gaps(site, self.parallel([task7(p, site) for p in SITE7])))

    def test_a_file_named_bare_is_found_in_the_folder_named_for_it(self):
        """A live run (2026-11-12) was refused for "images/ (contains red-squirrel-1.jpg and red-squirrel-2.jpg)"."""
        with tempfile.TemporaryDirectory() as site:
            Path(f"{site}/images").mkdir()
            for name in ("red-squirrel-1.jpg", "red-squirrel-2.jpg"):
                Path(f"{site}/images/{name}").write_bytes(b"\xff\xd8\xff")
            Path(f"{site}/styles.css").write_text("body {}")
            tasks = [f"Create {p}.html. Shared stylesheet: styles.css (already created). Images folder: images/ "
                     f"(contains red-squirrel-1.jpg and red-squirrel-2.jpg). Save to {site}/{p}.html" for p in ("index", "habitat")]
            self.assertIsNone(self.gaps(site, self.parallel(tasks)))
            tasks[1] = tasks[1].replace("red-squirrel-2.jpg", "red-squirrel-3.jpg")
            tasks[0] = tasks[0].replace("red-squirrel-2.jpg", "red-squirrel-3.jpg")
            self.assertIn("- red-squirrel-3.jpg: named by task-1 and task-2, and not there yet.", self.gaps(site, self.parallel(tasks)))

    def test_what_needs_no_shared_file_is_started(self):
        with tempfile.TemporaryDirectory() as site:
            Path(f"{site}/data.csv").write_text("x\n1\n")
            launches = [
                self.parallel([f"Create a.html, linking to b.html. Save to {site}/a.html",      # links need no file yet
                               f"Create b.html, linking to a.html. Save to {site}/b.html"]),
                self.parallel(["Fit a line to data.csv and save fit.png", "Histogram data.csv into hist.png"]),
                self.parallel(["Plot the fit to fit.png in the same plotting style as the others",   # figures, not pages
                               "Plot the residuals to resid.png in the same plotting style as the others"]),
                {"agent": "qwen", "task": "Use the shared styles.css. Create index.html."},  # one child alone
                {"chain": [{"agent": "qwen", "task": "Write css/style.css"},                # a chain: in order
                           {"agent": "qwen", "task": "Create index.html using css/style.css"}]},
                {"action": "status", "id": RUN},
            ]
            for launch in launches:
                with self.subTest(launch=launch):
                    self.assertIsNone(self.gaps(site, launch))

    def test_tasks_are_keyed_as_pi_subagents_keys_them(self):
        parallel = {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": "a"}, {"agent": "qwen", "task": "b", "cwd": "sub"}]}}
        chain = {"chain": [{"agent": "qwen", "task": "a"}, {"parallel": [{"agent": "qwen", "task": "b"}, {"agent": "qwen", "task": "c"}]}]}
        self.assertEqual([{"key": "task-1", "text": "a", "cwd": SITE}, {"key": "task-2", "text": "b", "cwd": f"{SITE}/sub"}],
                         self.call("tasksOf", parallel, SITE))
        self.assertEqual(["step-1", "step-2-1", "step-2-2"], [t["key"] for t in self.call("tasksOf", chain, SITE)])
        self.assertEqual(["task-1"], [t["key"] for t in self.call("tasksOf", {"tasks": [{"agent": "qwen", "task": "a"}]}, SITE)])
        self.assertEqual([""], [t["key"] for t in self.call("tasksOf", {"agent": "qwen", "task": "a"}, SITE)])
        self.assertEqual([], self.call("tasksOf", {"workflow": ".pi/tmp/flow.mjs"}, SITE))   # a script's tasks are code

    # -- a child

    def test_a_forked_child_knows_its_own_files_and_its_siblings(self):
        scope = self.call("childScope", child_branch("index"), SITE, "/home/u")
        self.assertEqual("task-1", scope["key"])
        self.assertEqual(5, scope["total"])
        self.assertEqual([f"{SITE}/index.html".lower() if os.uname().sysname == "Darwin" else f"{SITE}/index.html"], scope["own"])
        self.assertEqual({"task-2", "task-3", "task-4", "task-5"}, {o["key"] for o in scope["siblings"].values()})

    def test_a_fresh_child_finds_its_launch_and_siblings_in_the_parents_session(self):
        """qwen children start fresh (2026-11-13): no launch in their own branch, so the parent's session has it."""
        fresh = [msg("user", [{"type": "text", "text": task("species")}])]
        scope = self.call("childScope", fresh, SITE, "/home/u", parent_branch())
        self.assertEqual("task-2", scope["key"])
        self.assertEqual(RUN, scope["runId"])
        self.assertEqual({"task-1", "task-3", "task-4", "task-5"}, {o["key"] for o in scope["siblings"].values()})
        alone = self.call("childScope", fresh, SITE, "/home/u")
        self.assertEqual({}, alone["siblings"])
        # a later launch in the parent that is not this child's is not taken for its own
        other = parent_branch(tasks=[task(p, "/work/other") for p in ("a", "b")])
        later = parent_branch() + [{**e, "message": {**e["message"], "toolCallId": "call-2"}} if e["message"].get("role") == "toolResult"
                                   else e for e in other[1:]]
        self.assertEqual("task-2", self.call("childScope", fresh, SITE, "/home/u", later)["key"])

    def test_test6_child_cannot_rewrite_its_siblings_pages(self):
        with tempfile.TemporaryDirectory() as site:
            out = self.scenario([
                *child_start("index", site),
                {"start": True},                                                                         # once only
                {"tool": "write", "input": {"path": f"{site}/index.html", "content": "x"}},               # its own page
                {"tool": "write", "input": {"path": f"{site}/species.html", "content": "x"}},             # test6: "Species.html is missing"
                {"tool": "replace", "input": {"path": "lifecycle.html", "replace_from": "a", "text": "x"}},
                # test6: task 1 wrote the stylesheet nobody's task named, then restyled its siblings' pages
                {"tool": "write", "input": {"path": f"{site}/styles.css", "content": "x"}},
            ], site, child=True)
        note, again, own, species, lifecycle, css = out
        self.assertIn("task-1", note["content"])
        self.assertIn("species.html", note["content"])
        self.assertNotIn("index.html", note["content"].split("These files")[1])
        self.assertIsNone(again)
        self.assertIsNone(own)
        self.assertIn("species.html is task-2's file", species)
        self.assertIn("lifecycle.html is task-4's file", lifecycle)
        self.assertIn("styles.css is not in your task, which is index.html", css)

    def test_a_child_does_not_replace_a_file_someone_else_changed_unseen(self):
        """test6: task 4 replaced the stylesheet task 1 had written after task 4 started."""
        with tempfile.TemporaryDirectory() as site:
            css, notes, old = f"{site}/styles.css", f"{site}/notes.md", f"{site}/old.txt"
            out = self.scenario([
                {"touch": old, "age": 3_600_000},                                       # there before the child started
                {"branch": child_branch("lifecycle", site), "wait": 1700},
                {"touch": css},                                                         # a sibling writes it, later
                {"tool": "write", "input": {"path": css, "content": "x"}},
                {"tool": "read", "input": {"path": css}},
                {"tool": "write", "input": {"path": css, "content": "x"}},              # read since: an informed choice
                {"tool": "bash", "input": {"command": "python3 summarise.py > notes.md"}, "during": notes},  # its own command made it
                {"tool": "write", "input": {"path": notes, "content": "x"}},
                {"tool": "write", "input": {"path": old, "content": "x"}},
            ], site, child=True)
        self.assertIn("styles.css changed after you started", out[0])
        self.assertEqual([None, None, None, None, None], out[1:])

    def test_test10_a_page_child_makes_its_page_not_the_rest_of_the_request(self):
        """test10: children building anatomy.html and species.html wrote worm1-6.svg into images/,
        which only the gallery's task named, taking on the user's "download images" themselves."""
        def task10(page, site=SITE):
            if page == "gallery":
                return (f"Create the gallery page at {site}/gallery.html. Each gallery-item has an img tag "
                        "(placeholder paths like images/worm1.jpg through images/worm6.jpg).")
            return f"Create the {page} page at {site}/{page}.html. Copy navigation and footer EXACTLY from template.html."
        pages = ["index", "anatomy", "species", "gallery"]
        def branch_for(page, site):
            return (parent_branch(site, tasks=[task10(p, site) for p in pages])
                    + [msg("user", [{"type": "text", "text": f"{PREAMBLE}\n\nTask:\n{task10(page, site)}"}])])
        with tempfile.TemporaryDirectory() as site:
            Path(f"{site}/images").mkdir()
            write = lambda path: {"tool": "write", "input": {"path": path, "content": "x"}}
            species = self.scenario([{"branch": branch_for("species", site)},
                                     write(f"{site}/images/worm1.svg"),            # the user's images: not its task
                                     write(f"{site}/extra.html"),                  # a page nobody asked for
                                     write(f"{site}/species.html"),                # its own page
                                     write(f"/tmp/elm-pi-test-scratch.py"),         # scratch
                                     write(f"{site}/.pi/notes.md")], site, child=True)
            gallery = self.scenario([{"branch": branch_for("gallery", site)},
                                     write(f"{site}/images/worm1.jpg")], site, child=True)   # its task names images/
            ledger = [json.loads(l) for l in Path(f"{site}/.ledger/{RUN}.jsonl").read_text().splitlines()]
        self.assertIn("images/worm1.svg is not in your task, which is species.html", species[0])
        self.assertIn("The rest of the user's request went to the parent and your siblings", species[0])
        self.assertIn("an inline <svg>", species[0])
        self.assertIn("extra.html is not in your task", species[1])
        self.assertEqual([None, None, None], species[2:])
        self.assertEqual([None], gallery)
        self.assertIn({"key": "task-3", "path": f"{site}/images/worm1.svg", "tool": "write", "refused": "not in its task"},
                      [{**l, "path": l["path"]} for l in ledger])

    def test_a_child_that_writes_code_may_add_files(self):
        """Not pages: a child fixing parser.py may add tests/test_parser.py its task does not name."""
        with tempfile.TemporaryDirectory() as site:
            tasks = [f"Fix the bug in {site}/parser.py and add a test.", f"Speed up {site}/loader.py."]
            branch = (parent_branch(site, tasks=tasks)
                      + [msg("user", [{"type": "text", "text": f"{PREAMBLE}\n\nTask:\n{tasks[0]}"}])])
            out = self.scenario([{"branch": branch}, {"tool": "write", "input": {"path": f"{site}/tests/test_parser.py", "content": "x"}}],
                                site, child=True)
        self.assertEqual([None], out)

    def test_a_workflow_agent_does_not_replace_a_file_another_changed_unseen(self):
        """Workflow agents run in this process with no task the guard can read; the rule that needs
        none still keeps two of them off each other's work. Told apart by the run's store tools."""
        workflow_tools = ["read", "bash", "edit", "write", "view", "store_put", "store_get"]
        with tempfile.TemporaryDirectory() as site:
            page, notes, old = f"{site}/index.html", f"{site}/notes.md", f"{site}/old.txt"
            steps = [
                {"touch": old, "age": 3_600_000},                                       # there before it started
                {"branch": [], "wait": 1700},
                {"touch": page},                                                        # another agent writes it, later
                {"tool": "write", "input": {"path": page, "content": "x"}},
                {"tool": "read", "input": {"path": page}},
                {"tool": "write", "input": {"path": page, "content": "x"}},             # read since: an informed choice
                {"tool": "bash", "input": {"command": "python3 summarise.py > notes.md"}, "during": notes},   # its own command made it
                {"tool": "write", "input": {"path": notes, "content": "x"}},
                {"tool": "write", "input": {"path": old, "content": "x"}},
            ]
            agent = self.scenario(steps, site, child=False, tools=workflow_tools)
            yours = self.scenario(steps, site, child=False)                            # the main session: no store tools
        self.assertIn("index.html changed after you started", agent[0])
        self.assertEqual([None, None, None, None, None], agent[1:])
        self.assertEqual([None] * 6, yours)

    def test_a_file_another_wrote_during_my_own_command_is_not_mine(self):
        """Live probe (2026-11-13): agent B ran `sleep 8`; agent A wrote shared.txt meanwhile; B then
        replaced it unread, the change counted as B's own because it fell inside B's command."""
        workflow_tools = ["read", "bash", "edit", "write", "store_put", "store_get"]
        with tempfile.TemporaryDirectory() as site:
            shared = f"{site}/shared.txt"
            out = self.scenario([
                {"branch": [], "wait": 1700},
                {"tool": "bash", "input": {"command": "sleep 8"}, "during": shared},   # another agent's write, meanwhile
                {"tool": "write", "input": {"path": shared, "content": "B"}},
            ], site, child=False, tools=workflow_tools)
        self.assertIsNone(out[0])
        self.assertIn("shared.txt changed after you started", out[1])

    def test_a_child_with_no_siblings_is_left_alone(self):
        with tempfile.TemporaryDirectory() as site:
            branch = [msg("user", [{"type": "text", "text": f"{PREAMBLE}\n\nTask:\nFix {site}/a.py"}])]
            out = self.scenario([{"branch": branch}, {"start": True},
                                 {"tool": "write", "input": {"path": f"{site}/b.py", "content": "x"}}], site, child=True)
        self.assertEqual([None, None], out)

    # -- the parent

    def test_the_parent_waits_for_a_childs_notice_before_changing_its_file(self):
        """test6: the parent edited lifecycle.html while task 4 was still running."""
        with tempfile.TemporaryDirectory() as site:
            edit = {"tool": "replace_match", "input": {"path": f"{site}/lifecycle.html", "match": "hero", "replacement": "page-header"}}
            out = self.scenario([
                {"branch": parent_branch(site)},
                edit,
                {"add": [NEEDS_ATTENTION]}, edit,                       # not an ending
                {"add": [child_done("task-5")]}, edit,                   # another child's ending
                {"tool": "write", "input": {"path": f"{site}/conservation.html", "content": "x"}},
                {"tool": "write", "input": {"path": f"{site}/README.md", "content": "x"}},
                {"add": [child_done("task-4")]}, edit,
            ], site, child=False)
        self.assertIn("lifecycle.html is named in the task of task-4 of run 3eab4ab2", out[0])
        self.assertIn('"Workflow child completed: **task-4**"', out[0])
        self.assertIsNotNone(out[1])
        self.assertIsNotNone(out[2])
        self.assertEqual([None, None, None], out[3:])

    def test_a_run_that_ended_releases_its_files(self):
        with tempfile.TemporaryDirectory() as site:
            edit = {"tool": "write", "input": {"path": f"{site}/index.html", "content": "x"}}
            status = msg("toolResult", [{"type": "text", "text": f"Run: {RUN}\nState: complete\n"}],
                         toolCallId="call-2", toolName="subagent", isError=False)
            ended = self.scenario([{"branch": parent_branch(site)}, edit, {"add": [RUN_DONE]}, edit], site, child=False)
            checked = self.scenario([{"branch": parent_branch(site) + [status]}, edit], site, child=False)
            stale = self.scenario([{"branch": parent_branch(site, ago=36)}, edit], site, child=False)
        self.assertIsNotNone(ended[0])
        self.assertEqual([None], ended[1:])
        self.assertEqual([None], checked)       # `subagent` status says it is over
        self.assertEqual([None], stale)         # pi-subagents gives up on a run after 30 minutes

    def test_it_is_loaded(self):
        self.assertIn("owner-guard.ts", CONFIG["requiredExtensions"])


if __name__ == "__main__":
    unittest.main()
