"""read-only-auto: the permission mode between manual and auto (asked for on 2026-11-14).

The gate runs manual's floor - every call is an ask - and a reviewer in command-guard.ts, named in the
gate's authorizerChain, allows an ask before it reaches the user when it is for a shell command that can
only read, and only inside the project. Measured with that reviewer over eight manual sessions: 38 of 172
dialogs were for reading in seven of them, and 100 of 112 in one that polled with `ls`. (A first count,
"50 of 104", went by each command's first word and took `cd images && curl -o ...` for reading.)

A wrong "this only reads" is a hole in the mode, so the second table matters more than the first.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "templates/extensions/command-guard.ts"
PROJECT = "/p/site"

# Run without asking: each can do nothing but read, inside the project.
READS = [
    "ls", "ls -la", "pwd", "cd /p/site && ls -lh *.html",            # the commonest ask of all, in every manual session
    "cd /p/site/images && ls", "cd images && ls -la",
    "cat index.html | head -20", "grep -rn nav . 2>/dev/null | wc -l", 'find . -name "*.html"', "wc -l *.html",
    "file images/a.jpg", "diff a.html b.html", "ls > /dev/null 2>&1", "head -5 /p/site/a.css", "echo done",
    "stat a", "du -sh images", "sort names.txt | uniq -c", "tail -n 20 log.txt", "ls; ls images", "ls & ls images",
    "grep -c '<nav' *.html", "ls -la /p/site/", "test -f index.html", "tree -L 2",
    'grep -n "<footer>" index.html', "grep -c 'a > b' notes.txt", "grep -rn 'cost: $5' .",   # quoted: text, not shell
    # batch 6 (2026-11-14): these were asked about in read-only-auto, for a backslash each
    'grep -n "navbar\\|nav-links\\|footer" *.html | head -40', "grep -c 'a\\.b' *.html",
    'echo "=== nav ===" && \\\n  grep -h "nav-container" *.html | sort -u | wc -l',
    'grep -h "Tursiops truncatus\\|Orcinus orca" *.html | head -10',
]
# Left to the user, exactly as in manual: (command, why).
ASKS = [
    ("rm a", "not a reading command"), ("touch a", ""), ("mkdir d", ""), ("cp a b", ""), ("git status", "not on the list"),
    ("python3 -c 1", ""), ("curl https://x", ""), ("sed -i s/a/b/ f", ""), ("cat a | tee b", "tee writes"),
    ("ls > out.txt", "a redirection to a file"), ("cat a >> b", ""), ("echo hi > a", ""), ("ls 2>&1 > out", ""),
    ("cat a 2>/dev/null > b", "the harmless redirection does not excuse the other"), ("ls 3>/dev/null", ""),
    ("ls >/dev/nullx", "not /dev/null"), ("ls <(cat x)", "process substitution"), ("cat <<EOF\nx\nEOF", "a here-document"),
    ("cd /p/site && rm x", "the whole line, not its cd"), ("ls; rm x", ""), ("ls && touch x", ""), ("ls | xargs rm", ""),
    ("cd /tmp && ls", "outside the project"), ("cd && ls", "cd alone goes home"), ("cd - && ls", ""),
    ("cat ~/.ssh/id_rsa", "home"), ("cat ../other/x", "through .."), ("cat /etc/passwd", ""), ("ls /p/sitex", "a sibling"),
    ("cd images/../.. && ls", ""), ("ls $(rm x)", "a substitution"), ("ls `rm x`", ""), ("ls $HOME", "a variable"),
    ("cat $f", ""), ("find . -delete", "a flag that writes"), ("find . -exec rm {} \;", ""), ("find . -fprint out", ""),
    ("rg --pre cat x", "a flag that runs a program"), ("tail -f log", "never returns"), ("tail -nf log", ""),
    ("sort -o out a", ""), ("sort --output=out a", ""), ("uniq a b", "its second operand is written"),
    ("tree -o out", ""), ("file -C", "compiles a magic file"), ("FOO=1 ls", "an assignment"), ("/tmp/ls", "not a bare name"),
    ("./ls", ""), ("sudo ls", ""), ("env ls", ""), ("command ls", ""), ("xargs ls", ""),
    ("for f in *; do cat $f; done", "a loop"), ("", "nothing to read"),
    # quotes: what is inside single quotes is text, and nothing else is taken on trust
    ("echo \"'\" > x \"'\"", "the quotes a pattern sees are not the shell's"), ("echo \\' > x \\'", "a backslash"),
    ("grep \"$(rm x)\" a", "double quotes still expand"), ('cat "$HOME/.ssh/id_rsa"', ""), ("cat \"`whoami`\"", ""),
    ("grep 'a' b > c", "outside the quotes"), ("ls 'unclosed", "an unclosed quote"), ("ls a\\ b", "a backslash"),
    ('grep "a\\" > x "b"', "an escaped quote does not close the string"), ('cat "a\\\\" > x', "nor does an escaped backslash hide what follows"),
    ('echo "$(rm x)\\|a"', "expansion inside double quotes"), ("ls \\\n> out", "a continuation into a redirection"),
]

RUNNER = r"""
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[1]).href);
const { reads, asks, project } = JSON.parse(process.argv[2]);
const on = { PI_ELM_READ_AUTO: "1", PI_ELM_PERMISSION_MODE: "manual" };
const verdict = (details, env = on, calls = new Map()) => m.readAutoVerdict(details, calls, project, env).kind;
const bash = (command, extra = {}) => ({ payload: { kind: "bash" }, command, ...extra });

// registration: the gate's process-wide service map, and its "ready" announcement
const handlers = {}, bus = {};
const registered = [];
const service = { registerAuthorizer: (name, authorize) => { registered.push([name, authorize]); return () => registered.push(["disposed", name]); } };
globalThis[Symbol.for("@gotgenes/pi-permission-system:session-services")] = new Map([["s1", service]]);
m.default({ on: (e, f) => { (handlers[e] ??= []).push(f); }, events: { on: (e, f) => { bus[e] = f; } } });
bus["permissions:ready"]({ sessionId: null });
bus["permissions:ready"]({ sessionId: "s1" });
bus["permissions:ready"]({ sessionId: "s1" });           // ready may repeat: one registration
const names = registered.map(([name]) => name);
for (const f of handlers.session_start) await f({}, { cwd: project });
// a call's whole command is known by its id, from the tool_call the guard sees
for (const f of handlers.tool_call) await f({ toolName: "bash", toolCallId: "c9", input: { command: "cd /p/site && rm -rf images" } }, { cwd: project, hasUI: true, ui: { notify() {} } });
process.env.PI_ELM_READ_AUTO = "1"; process.env.PI_ELM_PERMISSION_MODE = "manual";
const live = registered[0][1];
const byId = (await live(bash("cd /p/site", { toolCallId: "c9" }))).kind;
const plain = (await live(bash("ls -la"))).kind;
for (const f of handlers.session_shutdown) await f({}, {});

console.log(JSON.stringify({
  reads: reads.filter((c) => !m.readOnlyCommand(c, project)),
  asks: asks.filter((c) => m.readOnlyCommand(c, project)),
  link: m.READ_AUTO_LINK, names, byId, plain, disposed: registered.at(-1),
  verdicts: {
    on: verdict(bash("ls")),
    manualWithoutTheSwitch: verdict(bash("ls"), { PI_ELM_PERMISSION_MODE: "manual" }),
    theSwitchBesideAuto: verdict(bash("ls"), { PI_ELM_PERMISSION_MODE: "auto", PI_ELM_READ_AUTO: "1" }),
    notReading: verdict(bash("rm x")),
    aChainNamedByItsCd: verdict({ payload: { kind: "bash", evidence: [{ label: "full command", text: "cd /p/site && rm x" }] }, command: "cd /p/site" }),
    aReadingChain: verdict({ payload: { kind: "bash", evidence: [{ label: "full command", text: "cd /p/site && ls" }] }, command: "cd /p/site" }),
    aPathOutsideTheProject: verdict({ payload: { kind: "bash_external_directory" }, command: "ls" }),
    aSubAgentsAsk: verdict(bash("ls", { forwarding: { from: "child" } })),
    anotherTool: verdict({ payload: { kind: "tool" }, command: "ls" }),
    aWrite: verdict({ payload: { kind: "tool" }, toolName: "write" }),
  },
}));
"""


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


class ReadOnlyAutoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = node()
        if not binary:
            raise unittest.SkipTest("needs node")
        payload = json.dumps({"reads": READS, "asks": [c for c, _ in ASKS], "project": PROJECT})
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", RUNNER, str(GUARD), payload],
                             capture_output=True, text=True, timeout=120, env={"PATH": "/usr/bin:/bin"})
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            raise unittest.SkipTest("this node cannot load TypeScript")
        assert run.returncode == 0, run.stderr[-3000:]
        cls.out = json.loads(run.stdout.strip().splitlines()[-1])

    def test_commands_that_only_read_inside_the_project_run(self):
        self.assertEqual([], self.out["reads"])

    def test_everything_else_is_left_to_the_user(self):
        self.assertEqual([], self.out["asks"])

    def test_it_allows_only_in_the_mode_and_only_a_bash_ask_of_this_session(self):
        v = self.out["verdicts"]
        self.assertEqual("allow", v.pop("on"))
        self.assertEqual("allow", v.pop("aReadingChain"))
        self.assertEqual({}, {name: kind for name, kind in v.items() if kind != "defer"})   # the rest: the user's

    def test_a_chain_is_judged_whole_never_by_the_piece_the_ask_names(self):
        """The gate's ask for `cd site && rm -rf images` names `cd site`; allowing that would run the rm."""
        self.assertEqual("defer", self.out["byId"])
        self.assertEqual("defer", self.out["verdicts"]["aChainNamedByItsCd"])
        self.assertEqual("allow", self.out["plain"])

    def test_it_registers_once_under_the_name_the_gate_is_told(self):
        self.assertEqual("elm-read-only-auto", self.out["link"])
        self.assertEqual(["elm-read-only-auto"], self.out["names"])
        self.assertEqual(["disposed", "elm-read-only-auto"], self.out["disposed"])
        config = json.loads((ROOT / "templates/extensions/pi-permission-system/config.json").read_text())
        self.assertEqual(["elm-read-only-auto"], config["authorizerChain"])     # a link decides nothing until named

    def test_the_reviewer_never_denies_and_manual_is_untouched(self):
        source = GUARD.read_text()
        verdict = source[source.index("export function readAutoVerdict"):source.index("export default function")]
        self.assertNotIn('"deny"', verdict)                       # allow or leave it to the user: nothing else
        self.assertIn('env.PI_ELM_READ_AUTO !== "1" || env.PI_ELM_PERMISSION_MODE !== "manual"', verdict)
        patch = (ROOT / "patch-pi.py").read_text()
        self.assertNotIn("READ_AUTO", patch)                      # the gate's manual floor is as it was

    def test_the_docs_say_what_passes(self):
        lockdown = " ".join((ROOT / "LOCKDOWN.md").read_text().split())
        self.assertIn("**read-only-auto** is manual with one thing let through.", lockdown)
        for word in ("`find -exec`", "`sort -o`", "`rg --pre`", "`tail -f`", "`PI_ELM_READ_AUTO=1`", "`authorizerChain`"):
            self.assertIn(word, lockdown)
        self.assertIn("--read-only-auto", (ROOT / "pi.bash").read_text())


if __name__ == "__main__":
    unittest.main()
