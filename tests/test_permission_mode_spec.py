"""The launcher's permission mode and pi's subcommands, against a specification.

The launcher's rules (pi, "# --- permission mode") are restated here as a small
Python model, from the documentation rather than from the shell:

  1. a flag (--manual/--auto/--yolo) sets the mode for that run;
  2. else a sub-agent (PI_ELM_CHILD) runs in the mode of the session that
     started it (PI_ELM_PERMISSION_MODE): yolo is handed on as auto, and
     anything that is not a mode as manual;
  3. else this install's default: agent/permission-mode when it says manual
     or auto, else the shipped default when that is manual or auto, else manual;
  4. started from a shell (not a sub-agent), a PI_ELM_PERMISSION_MODE already in
     the environment can only tighten the run (manual > auto > yolo; anything
     else counts as manual), with a note when it keeps a flag from loosening the
     run, or cannot loosen it itself;
  5. a mode other than auto needs a patched gate: asked for by flag it is
     refused (exit 2); otherwise the run, and its default, become auto, with a
     note for a session started from a shell;
  6. notes, for a session started from a shell only: yolo says it is for this
     session only; a mode that is not the default says new sessions start in
     the default; manual with -p says nothing can be asked.

Every combination of flag, saved default, shipped default, inherited mode,
sub-agent and gate is run through the launcher's own block and compared with
the model: the mode exported, the default exported, the exit status and which
notes were printed. A second table checks that each of pi's subcommands is
refused by name however it is preceded, and never when it is prompt text.
"""

import itertools
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launcher_cases import (BatchTest, C, Case, GATE_REL, LAUNCHER, block, exports, q, setargs,
                                 touch)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
NO_PROMPT = ",".join(CONFIG["permissionModes"]["manualNoPrompt"])
RANK = {"manual": 2, "auto": 1, "yolo": 0}
MODES = ("manual", "auto", "yolo")


def expected(flag, saved, shipped, inherited, child, gate, printing):
    """The documented rules: (rc, mode, default, notes)."""
    default = shipped if shipped in ("manual", "auto") else "manual"
    if saved in ("manual", "auto"):
        default = saved
    notes = set()
    if flag:
        mode = flag
    elif child and inherited:
        mode = inherited if inherited in ("manual", "auto") else ("auto" if inherited == "yolo" else "manual")
    else:
        mode = default
    if not child and inherited:
        held = inherited if inherited in RANK else "manual"
        if RANK[held] > RANK[mode]:
            if flag:
                notes.add("keeps")
            mode = held
        elif held != mode:
            notes.add("cannot-loosen")
    if mode != "auto" and gate != "patched":
        if flag:
            return 2, None, None, notes
        if not child:
            notes.add("gate")
        mode = default = "auto"
    if not child:
        if mode == "yolo":
            notes.add("yolo")
        elif mode != default:
            notes.add("session")
        if mode == "manual" and printing:
            notes.add("print")
    return 0, mode, default, notes


NOTE_TEXT = {
    "keeps": "in the environment keeps this run",
    "cannot-loosen": "cannot loosen a run",
    "gate": "so it runs in auto mode",
    "yolo": "yolo for this session only",
    "session": "for this session; new sessions start in",
    "print": "manual mode with -p: there is no one to ask",
}


def label(value, unset):
    """A value as it appears in a test name: "Auto" is not "auto"."""
    if value is None:
        return unset
    return value if value.islower() else "capitalised_" + value.lower()


def spec_case(flag, saved, shipped, inherited, child, gate, printing=False):
    name = (f"flag_{label(flag, 'none')}_saved_{label(saved, 'none')}_shipped_{label(shipped, 'unset')}"
            f"_env_{label(inherited, 'unset')}_{'child' if child else 'shell'}_{gate}{'_print' if printing else ''}")
    return Case(name, ["-p", "x"] if printing else [], flag=flag, saved=saved, shipped=shipped,
                inherited=inherited, child=child, gate=gate,
                want=expected(flag, saved, shipped, inherited, child, gate, printing))


FLAGS = (None, "manual", "auto", "yolo")
SAVED = (None, "manual", "auto", "yolo", "Auto")
INHERITED = (None, "manual", "auto", "yolo", "junk")

CASES = [
    # the heart of it: flag x saved default x inherited mode x sub-agent, patched gate
    *(spec_case(f, s, "manual", i, c, "patched")
      for f, s, i, c in itertools.product(FLAGS, SAVED, INHERITED, (False, True))),
    # the shipped default, alone and under a saved one
    *(spec_case(f, s, shipped, None, c, "patched")
      for f, s, shipped, c in itertools.product(FLAGS, (None, "auto"), ("auto", "yolo", "junk", None), (False, True))),
    # an install whose gate cannot apply a mode
    *(spec_case(f, s, "manual", i, c, gate)
      for f, s, i, c, gate in itertools.product(FLAGS, (None, "auto"), (None, "manual"), (False, True),
                                                ("unpatched", "halfpatched", "nogate"))),
    # one-shot runs
    *(spec_case(f, s, "manual", i, False, "patched", printing=True)
      for f, s, i in itertools.product(FLAGS, (None, "auto"), (None, "manual", "yolo"))),
]


class PermissionModeSpecTests(BatchTest):
    """The launcher's mode block, every combination, against the documented rules."""

    CASES = CASES
    BLOCK = block(LAUNCHER, "# --- permission mode ----", "# --- keep .pi out of the repository")

    @classmethod
    def prepare(cls):
        manager = 'const fullRules = x; // PI_ELM_PERMISSION_MODE === "manual"\n'
        index = 'const isYoloEnabled = () => PI_ELM_PERMISSION_MODE === "yolo";\n'
        for gate, files in {"patched": (manager, index), "unpatched": ("plain\n", "plain\n"),
                            "halfpatched": ("plain\n", index)}.items():
            touch(cls.tmp / "gates" / gate / GATE_REL / "src/policy/permission-manager.ts", files[0])
            touch(cls.tmp / "gates" / gate / GATE_REL / "src/index.ts", files[1])
        (cls.tmp / "gates/nogate").mkdir(parents=True)

    @classmethod
    def prelude(cls):
        # Once, as a function: a copy per case would pass the shell more than
        # the system's argument limit.
        return f"mode_block() {{\n{cls.BLOCK}\n}}"

    @classmethod
    def body(cls, case):
        kw = case.kw
        here = cls.tmp / "installs" / re.sub(r"\W+", "_", case.name)
        env = {"ELM_PERMISSION_MODE_DEFAULT": kw["shipped"], "ELM_MANUAL_NO_PROMPT": NO_PROMPT,
               "PI_ELM_PERMISSION_MODE": kw["inherited"], "PI_ELM_CHILD": "1" if kw["child"] else None,
               "PI_ELM_MANUAL_ALLOW": "bash"}
        lines = ["set -euo pipefail", f"mkdir -p {q(here / 'agent')}"]
        if kw["saved"] is not None:
            lines.append(f"printf '%s\\n' {q(kw['saved'])} > {q(here / 'agent/permission-mode')}")
        return "\n".join(lines + [
            f"HERE={q(here)}", f"GATE_PKG={q(cls.tmp / 'gates' / kw['gate'] / GATE_REL)}",
            f"MODE_FLAG={q(kw['flag'] or '')}", exports(env), setargs(case.args), 'mode_block "$@"',
            "printf '@@MODE=%s\\n' \"$(printenv PI_ELM_PERMISSION_MODE || true)\"",
            "printf '@@DEFAULT=%s\\n' \"$(printenv PI_ELM_PERMISSION_DEFAULT || true)\"",
            "printf '@@ALLOW=%s\\n' \"$(printenv PI_ELM_MANUAL_ALLOW || true)\""])

    def check(self, case, r):
        rc, mode, default, notes = case.kw["want"]
        self.assertEqual(rc, r.rc, f"stderr:\n{r.err}")
        if rc:
            self.assertIn("cannot run in", r.err)
            return
        self.assertEqual((mode, default), (r.vars.get("MODE"), r.vars.get("DEFAULT")), r.err)
        self.assertEqual(NO_PROMPT, r.vars.get("ALLOW"))
        printed = {note for note, text in NOTE_TEXT.items() if text in r.err}
        self.assertEqual(notes, printed, r.err)


def _generate(cls):
    for case in cls.CASES:
        name = "test_" + case.name.lower()
        if hasattr(cls, name):
            raise ValueError(f"duplicate case {name} in {cls.__name__}")

        def test(self, case=case):
            self.check(case, type(self).results[case.name])
        test.__name__ = name
        setattr(cls, name, test)
    return cls


_generate(PermissionModeSpecTests)


# --- pi's subcommands, however they are preceded ---------------------------------

SUBCOMMANDS = {
    "auth": ".env", "mcp": "-builtin:mcp", "config": "templates/settings.json",
    "list": "agent/installed-versions.json", "install": "templates/packages.json",
    "remove": "templates/packages.json", "uninstall": "templates/packages.json",
}
LAUNCHER_FLAGS = ("--fast", "--llama", "--mistral", "--remote", "--workflows", "--no-workflows", "--manual", "--auto", "--yolo")


def sub_case(name, args, refused, sub=None):
    return Case(name, args, refused=refused, sub=sub)


SUB_CASES = []
for sub, pointer in SUBCOMMANDS.items():
    SUB_CASES += [
        sub_case(f"{sub}_alone", [sub], True, sub),
        sub_case(f"{sub}_with_arguments", [sub, "x", "--y"], True, sub),
        sub_case(f"{sub}_with_help", [sub, "--help"], True, sub),
        *(sub_case(f"{sub}_after_{flag[2:]}", [flag, sub], True, sub) for flag in LAUNCHER_FLAGS),
        sub_case(f"{sub}_after_two_launcher_flags", ["--fast", "--manual", sub, "y"], True, sub),
        # prompt text, an option's value, or another word: never refused
        sub_case(f"{sub}_as_print_text", ["-p", sub], False),
        sub_case(f"{sub}_after_double_dash", ["--", sub], False),
        sub_case(f"{sub}_as_an_option_value", ["--name", sub], False),
        sub_case(f"{sub}_capitalised", [sub.capitalize()], False),
        sub_case(f"{sub}_upper_case", [sub.upper()], False),
        sub_case(f"{sub}_with_a_suffix", [sub + "s"], False),
        sub_case(f"{sub}_with_a_leading_space", [" " + sub], False),
        sub_case(f"{sub}_inside_a_sentence", [f"{sub} the thing"], False),
    ]


class SubcommandRefusalTests(BatchTest):
    """Each of pi's subcommands is refused by name, wherever the launcher's own
    flags put it, with a pointer to what to use instead; as prompt text it is not."""

    CASES = SUB_CASES
    PARSE = block(LAUNCHER, "FAST=0; LLAMA=0; REMOTE=0;", "# --- ELM-only policy")

    @classmethod
    def prelude(cls):
        return f'. {q(ROOT / "lib/policy.sh")}'

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", f"HERE={q(cls.tmp)}", setargs(case.args), cls.PARSE,
                          'printf "@@REACHED\\n"'])

    def check(self, case, r):
        sub = case.kw["sub"]
        if case.kw["refused"]:
            self.assertEqual(2, r.rc, r.err)
            self.assertIn(f"`pi {sub}` is not available in this install.", r.err)
            self.assertIn(SUBCOMMANDS[sub], r.err)
            self.assertNotIn("@@REACHED", r.out)
        else:
            self.assertEqual(0, r.rc, r.err)
            self.assertIn("@@REACHED", r.out)
            self.assertNotIn("is not available in this install", r.err)


_generate(SubcommandRefusalTests)


if __name__ == "__main__":
    unittest.main()
