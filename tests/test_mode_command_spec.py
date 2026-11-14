"""/mode (templates/extensions/permission-mode.ts), every path, against a specification.

The documented behaviour, restated as a Python model:

  - an argument that is not a mode (after trimming and lower-casing) is refused
    with an error, and nothing changes; so does any /mode on an install whose
    gate does not apply the modes;
  - no argument opens the first menu - one line per mode, marked "now" and
    "default" - and Escape there changes nothing;
  - yolo: already yolo says so; otherwise one answer, "Change for this session
    only", which switches this session and never saves a default;
  - manual or auto: when it is already both this session's mode and the default,
    it says so; otherwise "Change for this session" (switch) or "Change default
    mode" (switch, and save agent/permission-mode); Escape changes nothing;
  - a default that cannot be saved still switches the session, and says so.

Each case runs the real extension under node with a stub pi, and the result -
mode, default, the saved file, the menus offered and the last message's level -
is compared with the model.
"""

import itertools
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "templates/extensions/permission-mode.ts"
MODES = ("manual", "auto", "yolo")
SESSION, DEFAULT, YOLO_SESSION = "Change for this session", "Change default mode", "Change for this session only"
SHORT = {"manual": "asks before every command and edit", "auto": "the risky commands ask, the rest run",
         "yolo": "answers every ask yes, this session only"}


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def menu_line(mode, current, fallback):
    marks = [m for m, on in (("now", mode == current), ("default", mode == fallback)) if on]
    return f"{mode} - {SHORT[mode]}" + (f" ({', '.join(marks)})" if marks else "")


def expected(current, fallback, typed, answers, patched, writable):
    """(mode, default, saved, menus offered, last message level)."""
    menus = []
    answers = list(answers)
    unchanged = (current, fallback, None)
    wanted = typed.strip().lower()

    def ask(options):
        menus.append(options)
        pick = answers.pop(0) if answers else None
        return options[pick] if pick is not None and pick < len(options) else None

    if wanted and wanted not in MODES:
        return (*unchanged, menus, "error")
    if not patched:
        return (*unchanged, menus, "error")
    if not wanted:
        choice = ask([menu_line(m, current, fallback) for m in MODES])
        if choice is None:
            return (*unchanged, menus, None)
        wanted = choice.split(" - ")[0]
    if wanted == "yolo":
        if current == "yolo":
            return (*unchanged, menus, "info")
        if ask([YOLO_SESSION]) != YOLO_SESSION:
            return (*unchanged, menus, None)
        return ("yolo", fallback, None, menus, "warning")
    if wanted == current == fallback:
        return (*unchanged, menus, "info")
    choice = ask([SESSION, DEFAULT])
    if choice is None:
        return (*unchanged, menus, None)
    if choice == DEFAULT:
        if not writable:
            return (wanted, fallback, None, menus, "error")
        return (wanted, wanted, f"{wanted}\n", menus, "info")
    return (wanted, fallback, None, menus, "info")


# what is typed after /mode -> how it appears in a test name
TYPED = {"": "nothing", "manual": "manual", "auto": "auto", "yolo": "yolo", "  Auto ": "padded_capital_auto",
         "YOLO": "upper_case_yolo", "turbo": "not_a_mode"}


def answer_sets(typed):
    """Every distinct way through the menus the typed command leads to."""
    if typed.strip().lower() not in ("", *MODES):
        return [()]
    if not typed.strip():
        return [(None,)] + [(first, second) for first in (0, 1, 2) for second in (0, 1, None)]
    return [(0,), (1,), (None,)]


CASES = []
for current, fallback, typed in itertools.product(MODES, ("manual", "auto"), TYPED):
    for answers in answer_sets(typed):
        CASES.append({"name": f"{current}_now_{fallback}_default_typed_{TYPED[typed]}_answers_"
                              + "_".join("esc" if a is None else str(a) for a in answers),
                      "current": current, "def": fallback, "typed": typed, "answers": list(answers),
                      "patched": True, "writable": True})
for current, fallback, typed in itertools.product(MODES, ("manual", "auto"), ("", "auto", "yolo")):
    CASES.append({"name": f"unpatched_{current}_now_{fallback}_default_typed_{TYPED[typed]}",
                  "current": current, "def": fallback, "typed": typed, "answers": [1, 1],
                  "patched": False, "writable": True})
for current, wanted in (("manual", "auto"), ("auto", "manual"), ("yolo", "auto"), ("yolo", "manual")):
    CASES.append({"name": f"unwritable_{current}_now_making_{wanted}_the_default",
                  "current": current, "def": "manual" if wanted == "auto" else "auto", "typed": wanted,
                  "answers": [1], "patched": True, "writable": False})


RUNNER = r"""
import { pathToFileURL } from "node:url";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const [file, casesPath, base] = process.argv.slice(1);
const mod = await import(pathToFileURL(file).href);
const out = {};
for (const c of JSON.parse(readFileSync(casesPath, "utf8"))) {
  const agentDir = join(base, c.name);
  const src = join(agentDir, "npm/node_modules/@gotgenes/pi-permission-system/src");
  mkdirSync(join(src, "policy"), { recursive: true });
  writeFileSync(join(src, "index.ts"), c.patched ? '// PI_ELM_PERMISSION_MODE === "yolo"' : "plain");
  writeFileSync(join(src, "policy/permission-manager.ts"), c.patched ? '// PI_ELM_PERMISSION_MODE === "manual"' : "plain");
  if (!c.writable) chmodSync(agentDir, 0o500);
  process.env.PI_CODING_AGENT_DIR = agentDir;
  process.env.PI_ELM_PERMISSION_MODE = c.current;
  process.env.PI_ELM_PERMISSION_DEFAULT = c.def;
  const commands = {};
  mod.default({ on: () => {}, registerCommand: (n, d) => { commands[n] = d; } });
  const menus = [], notes = [];
  const answers = [...c.answers];
  const ctx = { hasUI: true, ui: {
    notify: (m, level) => notes.push([m, level]),
    setStatus: () => {},
    select: async (_title, options) => { menus.push(options); const i = answers.shift(); return i === null || i === undefined ? undefined : options[i]; },
    confirm: async () => { throw new Error("no confirm dialog is expected"); },
  } };
  let thrown = null;
  try { await commands.mode.handler(c.typed, ctx); } catch (e) { thrown = String(e); }
  if (!c.writable) chmodSync(agentDir, 0o700);
  const saved = join(agentDir, "permission-mode");
  out[c.name] = {
    mode: process.env.PI_ELM_PERMISSION_MODE, def: process.env.PI_ELM_PERMISSION_DEFAULT,
    saved: existsSync(saved) ? readFileSync(saved, "utf8") : null,
    menus, level: notes.length ? notes[notes.length - 1][1] : null, thrown,
  };
}
console.log(JSON.stringify(out));
"""


class ModeCommandSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = node()
        if not binary:
            raise unittest.SkipTest("needs node")
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            shutil.copy(EXTENSION, cls.tmp / "permission-mode.ts")
            (cls.tmp / "cases.json").write_text(json.dumps(CASES))
            (cls.tmp / "agents").mkdir()
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                                  str(cls.tmp / "permission-mode.ts"), str(cls.tmp / "cases.json"), str(cls.tmp / "agents")],
                                 capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp)},
                                 cwd=cls.tmp, timeout=300)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                raise unittest.SkipTest("this node cannot load TypeScript")
            if run.returncode != 0:
                raise AssertionError(run.stderr[-3000:])
            cls.results = json.loads(run.stdout)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check(self, case):
        got = self.results[case["name"]]
        self.assertIsNone(got["thrown"])
        mode, fallback, saved, menus, level = expected(case["current"], case["def"], case["typed"], case["answers"],
                                                       case["patched"], case["writable"])
        self.assertEqual({"mode": mode, "def": fallback, "saved": saved, "menus": menus, "level": level},
                         {k: got[k] for k in ("mode", "def", "saved", "menus", "level")})


for _case in CASES:
    _name = "test_" + _case["name"]
    assert not hasattr(ModeCommandSpecTests, _name), _name
    setattr(ModeCommandSpecTests, _name, lambda self, c=_case: self.check(c))


if __name__ == "__main__":
    unittest.main()
