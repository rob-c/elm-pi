"""Every fact the docs and the model's prompts state, where code or config can
check it, matches that code or config.

README.md, INSTALL.md, LOCKDOWN.md, CONTRIBUTING.md and docs/index.html tell
people what this install does; templates/AGENTS.md, APPEND_SYSTEM.md, the agent
definitions, the reference files and the skills tell the model. Between them
they quote numbers (concurrency, retries, compaction, context window, provider
and skill counts), names (extensions, packages, tools, commands, skills, hosts,
folders), the flags of `pi`, install.sh and bootstrap.sh, the environment
variables each reads, and the commands the permission gate denies or asks
about. All of those live somewhere else - config/, templates/, the launcher and
installer scripts, templates/extensions/*.ts and, where they are installed in
this checkout, pi and its packages - and a stale copy misleads a user or sends
the model after something that is not there.

So each claim or list entry is one test, in both directions where a list can
drift either way (a flag documented but not parsed, and parsed but not
documented). Tests are generated at import, so a failure names the claim. A
mismatch found when this file was written is kept as an expected failure with
a comment naming it. Nothing here runs pi, the installer or the network; the
checks against installed packages skip on a checkout that was never
bootstrapped.
"""

import html
import json
import re
import shlex
import unittest
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
NPM = ROOT / "agent/npm/node_modules"
PI_DIST = ROOT / "node_modules/@earendil-works/pi-coding-agent/dist"


def read(rel):
    return (ROOT / rel).read_text()


def flat(text):
    """Whitespace collapsed, so a phrase wrapped across lines still matches."""
    return " ".join(text.split())


def html_text(source):
    source = re.sub(r"<(script|style)\b.*?</\1>", " ", source, flags=re.S | re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", source))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def generate(cls, cases, check, expected_failures=()):
    """One test method per case: (name, *args). Names in expected_failures are
    known mismatches, kept so the day they are fixed is noticed."""
    unknown = set(expected_failures) - {c[0] for c in cases}
    assert not unknown, f"expected failures with no case: {sorted(unknown)}"
    for name, *args in cases:
        method_name = f"test_{name}"
        assert not hasattr(cls, method_name), method_name
        def method(self, _args=tuple(args)):
            check(self, *_args)
        method.__name__ = method_name
        if name in expected_failures:
            method = unittest.expectedFailure(method)
        setattr(cls, method_name, method)


CONFIG = json.loads(read("config/elm-pi.json"))
VERSIONS = json.loads(read("config/versions.json"))
SETTINGS = json.loads(read("templates/settings.json"))
SUBAGENT = json.loads(read("templates/extensions/subagent/config.json"))
PERMISSION = json.loads(read("templates/extensions/pi-permission-system/config.json"))["permission"]
PACKAGES = json.loads(read("templates/packages.json"))["dependencies"]
MODELS = json.loads(read("templates/models.json"))
QWEN = MODELS["providers"]["elm"]["models"][0]
WORKFLOWS = json.loads(read("templates/workflows/settings.json"))
WEB_SEARCH = json.loads(read("templates/web-search.json"))
AUTO_COMPACT = json.loads(read("templates/config/pi-auto-compact/config.json"))
SKILLS = sorted(p.parent.name for p in TEMPLATES.glob("skills/*/SKILL.md"))

LAUNCHER = read("pi")
INSTALL_SH = read("install.sh")
BOOTSTRAP = read("bootstrap.sh")
CONFIGURE = read("configure.sh")
COLOUR = read("templates/shell/colour.sh")
ELM_SHIM_TS = read("templates/extensions/elm-shim.ts")
COMMAND_GUARD = read("templates/extensions/command-guard.ts")
COMMAND_OUTPUT = read("templates/extensions/command-output.ts")
SKILL_ROUTER = read("templates/extensions/skill-router.ts")
VIEW_OUTPUTS = read("templates/extensions/view-outputs.ts")
INSTALL_NOTES = read("templates/extensions/install-notes.ts")
EGRESS = read("proxy/egress.py")

README = read("README.md")
INSTALL = read("INSTALL.md")
LOCKDOWN = read("LOCKDOWN.md")
CONTRIBUTING = read("CONTRIBUTING.md")
SITE = html_text(read("docs/index.html"))
DOCS = {"README.md": README, "INSTALL.md": INSTALL, "LOCKDOWN.md": LOCKDOWN,
        "CONTRIBUTING.md": CONTRIBUTING, "docs/index.html": SITE}
FLAT = {name: flat(text) for name, text in DOCS.items()}
PROMPT_FILES = sorted([TEMPLATES / "AGENTS.md", TEMPLATES / "APPEND_SYSTEM.md",
                       *TEMPLATES.glob("agents/*.md"), *TEMPLATES.glob("reference/*.md"),
                       *TEMPLATES.glob("skills/*/SKILL.md")])
PROMPTS = {str(p.relative_to(TEMPLATES)): p.read_text() for p in PROMPT_FILES}
PROMPT_FLAT = {name: flat(text) for name, text in PROMPTS.items()}
AGENTS_MD = PROMPTS["AGENTS.md"]
APPEND = PROMPT_FLAT["APPEND_SYSTEM.md"]

NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "nine": 9, "eleven": 11,
                "twelve": 12, "thirteen": 13, "fifteen": 15, "sixteen": 16}


def heredoc(source, after):
    start = source.index("<<'EOU'\n", source.index(after)) + len("<<'EOU'\n")
    return source[start:source.index("\nEOU\n", start)]


PI_USAGE = heredoc(LAUNCHER, "elm_usage() {")
INSTALL_USAGE = heredoc(INSTALL_SH, "usage() {")
BOOT_USAGE = heredoc(BOOTSTRAP, "usage() {")
USAGES = {"pi": PI_USAGE, "install.sh": INSTALL_USAGE, "bootstrap.sh": BOOT_USAGE}


def option_column(usage):
    """The flags a usage text lists in its option column (two-space indent)."""
    flags = []
    for line in usage.splitlines():
        match = re.match(r"^  (-[\w-]+(?:,\s*-[\w-]+)*)\s", line)
        if match:
            flags += [f.strip() for f in match.group(1).split(",")]
    return flags


def case_labels(block):
    """The option names a bash `case` block matches, continuation lines joined."""
    labels = []
    for line in block.replace("\\\n", "").splitlines():
        match = re.match(r"^\s*(-[\w-]*(?:\s*\|\s*-[\w-]*)*)\)", line)
        if match:
            labels += [f.strip() for f in match.group(1).split("|")]
    return [f for f in labels if f not in ("--", "-")]


def mentions(text, flag):
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text) is not None


# --- the launcher's, install.sh's and bootstrap.sh's own flags ----------------------

PI_PARSED = case_labels(between(LAUNCHER, 'flag_prev=""\nfor a in "$@"; do', "set -- ${ARGS"))
PI_PARSED += case_labels(between(LAUNCHER, "WANTS_HELP=0", "\ndone\n"))
PI_SETUP_BLOCK = between(LAUNCHER, 'if [ "${1:-}" = "setup" ]; then', "\nfi\n")
PI_SETUP_PARSED = case_labels(PI_SETUP_BLOCK)
PI_SETUP_MAP = dict(re.findall(r'(--[\w-]+)\) SETUP_FLAGS\+=\((--[\w-]+)\)', PI_SETUP_BLOCK))
PI_SETUP_MAP.update({f: f for f in re.findall(r'(--no-[\w-]+)(?=[|)])', PI_SETUP_BLOCK)})
PI_SETUP_HELP = re.findall(r"^  pi setup (--[\w-]+)", PI_USAGE, re.M)
PI_UPDATE_PARSED = case_labels(between(LAUNCHER, 'if [ "${1:-}" = "update" ]; then', "\nfi\n"))
PI_LAUNCHER_FLAGS = set(PI_PARSED)

HELP_FIRST = re.compile(r'case "\$arg" in (-h\|--help)\) usage; exit 0 ;; esac')
INSTALL_PARSE = between(INSTALL_SH, "    --update)  UPDATE=1", "\ndone")
INSTALL_PARSED = case_labels(INSTALL_PARSE) + HELP_FIRST.search(INSTALL_SH).group(1).split("|")
INSTALL_PASSED = case_labels(re.search(r"\n(\s*--no-packages\|[^)]*)\)\s*\n\s*PASS_ARGS\+=",
                                       INSTALL_PARSE.replace("\\\n", "")).group(1) + ")")

BOOT_PARSED = case_labels(between(BOOTSTRAP, "    --no-shim|--no-packages", "\ndone\napply_flag"))
BOOT_PARSED += HELP_FIRST.search(BOOTSTRAP).group(1).split("|")

STEP2 = between(INSTALL, "## Step 2 — Run bootstrap", "**The options are remembered.**")
INSTALL_TABLE_FLAGS = [f for line in STEP2.splitlines() if line.startswith("| `-")
                       for f in re.findall(r"`(-[\w-]+)`", line.split("|")[1])]
README_FLAG_TABLE = re.findall(r"^\| `(--[\w-]+)` \|", README, re.M)


class FlagTests(unittest.TestCase):
    """What each usage text and doc table lists is what the parser takes, and back."""

    def test_launcher_help_and_parser_are_not_empty(self):
        # guards the extraction itself: an anchor that moved would make every
        # generated case below vacuous
        self.assertGreaterEqual(len(PI_PARSED), 6)
        self.assertGreaterEqual(len(INSTALL_PARSED), 15)
        self.assertGreaterEqual(len(BOOT_PARSED), 15)
        self.assertGreaterEqual(len(INSTALL_TABLE_FLAGS), 15)
        self.assertGreaterEqual(len(INSTALL_PASSED), 10)


def _flag_in(self, flag, flags, where):
    self.assertIn(flag, flags, f"{flag}: {where}")


def both(prefix, a_name, a, b_name, b, b_text=""):
    """One case per entry of either list, checking it is in both: a list that
    drifts either way fails on the entry, naming the side it is missing from.
    `b_text` is prose where an entry of `a` may be mentioned rather than listed."""
    return [(f"{prefix}_{slug(x)}", x, a_name, list(a), b_name, list(b), b_text) for x in dict.fromkeys([*a, *b])]


def _in_both(self, x, a_name, a, b_name, b, b_text):
    missing = [a_name] if x not in a else []
    if x not in b and not (x in a and b_text and mentions(b_text, x)):
        missing.append(b_name)
    self.assertEqual([], missing, f"{x} is missing from {' and '.join(missing)}")


generate(FlagTests, [
    *both("pi_flag", "./pi's parser", PI_PARSED, "`pi --help`", option_column(PI_USAGE)),
    *both("pi_setup_flag", "`pi setup`'s parser", PI_SETUP_PARSED, "its help", PI_SETUP_HELP),
    # README's table gives the long spelling only
    *both("readme_flag_table", "README's flag table", README_FLAG_TABLE, "`pi --help`",
          [f for f in option_column(PI_USAGE) if f.startswith("--")]),
    *both("install_flag", "install.sh's parser", INSTALL_PARSED, "install.sh --help", option_column(INSTALL_USAGE)),
    *both("bootstrap_flag", "bootstrap.sh's parser", BOOT_PARSED, "bootstrap.sh --help", option_column(BOOT_USAGE),
          BOOT_USAGE),
    *both("install_md_bootstrap_flag", "bootstrap.sh's parser", BOOT_PARSED, "INSTALL.md's Step 2 table",
          INSTALL_TABLE_FLAGS),
], _in_both)
generate(FlagTests, [
    *[(f"pi_setup_{slug(f)}_maps_to_a_bootstrap_flag", PI_SETUP_MAP.get(f, "?"), BOOT_PARSED,
       f"pi setup {f} runs bootstrap.sh with a flag it does not parse") for f in PI_SETUP_PARSED],
    *[(f"install_passes_{slug(f)}_and_bootstrap_parses_it", f, BOOT_PARSED, "install.sh forwards it, bootstrap.sh rejects it")
      for f in INSTALL_PASSED],
], _flag_in)


# Every `pi ...`, `./bootstrap.sh ...` and `pi setup ...` a document or prompt
# shows uses flags that exist: the launcher's own, pi's (from the installed
# CLI's parser), or the subcommand's.
CODE_SPANS = []
for _name, _text in {**DOCS, **PROMPTS}.items():
    CODE_SPANS += re.findall(r"`([^`\n]+)`", _text)
    CODE_SPANS += [line.strip() for block in re.findall(r"```[a-z]*\n(.*?)```", _text, re.S)
                   for line in block.splitlines()]
    CODE_SPANS += [line.strip() for line in _text.splitlines() if line.startswith("    ")]


def command_flags(prefix, skip=()):
    """The options a doc's commands give `prefix`, up to a `--`; spans naming
    one of `skip` (a subcommand with its own parser) are left out."""
    found = set()
    for span in CODE_SPANS:
        if any(s in span for s in skip):
            continue
        for match in re.finditer(rf"(?:^|[\s;|&(=]){re.escape(prefix)}((?: [^#|;&]*)?)", span):
            try:
                words = shlex.split(match.group(1), comments=True)
            except ValueError:
                words = match.group(1).split()
            for word in words:
                if word == "--":
                    break
                if re.fullmatch(r"--?[a-z][a-z-]*", word):
                    found.add(word)
    return found


@lru_cache(maxsize=None)
def pi_cli_flags():
    args = PI_DIST / "cli/args.js"
    if not args.is_file():
        return None
    return set(re.findall(r'"(--?[a-z][a-z-]*)"', args.read_text()))


# `--ssh` belongs to the ssh.ts example extension LOCKDOWN.md shows being refused.
EXTENSION_FLAGS = {"--ssh"}
SUBCOMMANDS = ("pi setup", "pi update", "pi install", "pi remove")


class DocumentedCommandTests(unittest.TestCase):
    pass


def _pi_flag_exists(self, flag):
    if flag in PI_LAUNCHER_FLAGS:
        return
    flags = pi_cli_flags()
    if flags is None:
        self.skipTest("pi is not installed in this checkout")
    self.assertIn(flag, flags, f"`pi {flag}` in the docs: neither the launcher nor pi takes it")


generate(DocumentedCommandTests, [(f"documented_pi_flag_{slug(f)}_exists", f)
                                  for f in sorted(command_flags("pi", SUBCOMMANDS) - EXTENSION_FLAGS)],
         _pi_flag_exists)
generate(DocumentedCommandTests,
         [(f"documented_bootstrap_flag_{slug(f)}_is_parsed", f, BOOT_PARSED, "`bootstrap.sh` in the docs")
          for f in sorted(command_flags("bootstrap.sh"))]
         + [(f"documented_pi_setup_flag_{slug(f)}_is_parsed", f, PI_SETUP_PARSED, "`pi setup` in the docs")
            for f in sorted(command_flags("pi setup"))]
         + [(f"documented_pi_update_flag_{slug(f)}_is_intercepted", f, PI_UPDATE_PARSED, "`pi update` in the docs")
            for f in sorted(command_flags("pi update"))],
         _flag_in)


class LauncherBehaviourClaimTests(unittest.TestCase):
    """Behaviour the docs describe, read off the launcher."""

    def test_with_all_also_offers_the_workflow_tools(self):
        # AGENTS.md: the `workflow` tool exists in a session started with
        # `pi --workflows` (or `--with-all`)
        self.assertIn("(or `--with-all`)", flat(AGENTS_MD))
        self.assertIn("--with-all) WITH_ALL=1; WORKFLOWS=1 ;;", LAUNCHER)

    def test_pi_elm_workflows_turns_the_workflow_tools_on(self):
        self.assertIn("`PI_ELM_WORKFLOWS=1`", PROMPT_FLAT["skills/elm-dynamic-workflows/SKILL.md"])
        self.assertIn('WORKFLOWS="${PI_ELM_WORKFLOWS:-0}"', LAUNCHER)

    def test_pi_install_and_remove_are_refused(self):
        self.assertIn("`pi install` and `pi remove` are refused", FLAT["README.md"])
        block = between(LAUNCHER, "  install|remove|uninstall)", "esac")
        self.assertIn("exit 2", block)

    def test_the_argument_guard_refuses_with_exit_2(self):
        self.assertIn("refuses everything else with exit code 2", FLAT["LOCKDOWN.md"])
        self.assertIn("exit 2", between(LAUNCHER, "  refuse() {", "\n  }"))

    def test_an_untrusted_start_folder_is_refused_with_exit_2(self):
        self.assertIn("refused (exit 2); `PI_FORCE=1` overrides", FLAT["LOCKDOWN.md"])
        self.assertIn("exit 2", between(LAUNCHER, "elm_untrusted_folder \"$PWD\"", "\n  fi\nfi"))

    def test_print_mode_closes_a_terminal_stdin(self):
        self.assertIn("The launcher closes stdin when it is a TTY", FLAT["README.md"])
        self.assertIn('if [ "$PRINT_MODE" = "1" ] && [ -t 0 ]; then', LAUNCHER)
        self.assertIn('"$@" < /dev/null', LAUNCHER)

    def test_load_warning_is_above_one_and_a_half_times_the_cores(self):
        self.assertIn("above ~1.5x core count", FLAT["README.md"])
        self.assertIn("warns above 1.5x core count", FLAT["INSTALL.md"])
        self.assertIn("(l > c*1.5)", LAUNCHER)

    def test_strict_load_refuses_and_force_silences(self):
        self.assertIn("`PI_FORCE=1` silences the note, `PI_STRICT_LOAD=1` refuses instead", FLAT["README.md"])
        block = between(LAUNCHER, "# --- preflight: note a saturated machine", "# --- note a session started")
        self.assertIn('[ "${PI_STRICT_LOAD:-0}" = "1" ]', block)
        self.assertIn('[ "${PI_FORCE:-0}" != "1" ]', block)

    def test_children_are_marked_before_exec(self):
        self.assertIn("The launcher sets `PI_ELM_CHILD=1` before exec", FLAT["INSTALL.md"])
        self.assertLess(LAUNCHER.index("export PI_ELM_CHILD=1"), LAUNCHER.index('exec "$ORIG"'))

    def test_dot_pi_gitignore_contains_a_star(self):
        self.assertIn("the launcher writes `.pi/.gitignore` containing `*`", FLAT["INSTALL.md"])
        self.assertIn("printf '*\\n' > .pi/.gitignore", LAUNCHER)

    def test_fast_adds_todo_the_skill_router_and_remote_research(self):
        self.assertIn("plus `todo`, the skill router and, with `--remote`, the research instruction", FLAT["INSTALL.md"])
        self.assertIn("for e in todo skill-router remote-research; do", LAUNCHER)

    def test_remote_opens_the_proxy_with_a_star(self):
        self.assertIn("Open mode is a single `*` in the allowlist", FLAT["LOCKDOWN.md"])
        self.assertIn('ELM_PI_PROXY_ALLOW="${ELM_PI_PROXY_ALLOW:+$ELM_PI_PROXY_ALLOW,}*"', LAUNCHER)

    def test_remote_turns_the_web_tools_on(self):
        self.assertIn("web tools on", FLAT["INSTALL.md"])
        self.assertIn("export PI_ELM_WEB=1", between(LAUNCHER, 'if [ "$REMOTE" = "1" ]; then', "\nfi\n"))

    def test_computer_use_never_loads_in_a_child(self):
        self.assertIn("never for a sub-agent child", FLAT["LOCKDOWN.md"])
        self.assertIn('[ "$REMOTE" = "1" ] && [ -z "${PI_ELM_CHILD:-}" ] && [ -f "$CU_EXT" ]', LAUNCHER)

    def test_computer_use_helper_lives_in_agent_helpers(self):
        self.assertIn("the launcher points it at `agent/helpers/` instead and has it signed ad hoc",
                      FLAT["LOCKDOWN.md"])
        self.assertIn('PI_COMPUTER_USE_HELPER_APP_PATH="$HERE/agent/helpers/', LAUNCHER)
        self.assertIn('PI_COMPUTER_USE_CODESIGN_IDENTITY="-"', LAUNCHER)

    def test_update_and_setup_run_before_the_proxy_starts(self):
        # LOCKDOWN.md: "The proxy is started *after* the update intercept"
        self.assertIn("The proxy is started *after* the update intercept", FLAT["LOCKDOWN.md"])
        proxy = LAUNCHER.index("--port-file")
        self.assertLess(LAUNCHER.index('if [ "${1:-}" = "update" ]; then'), proxy)
        self.assertLess(LAUNCHER.index('if [ "${1:-}" = "setup" ]; then'), proxy)

    def test_version_list_models_and_update_need_no_key_and_skip_the_folder_check(self):
        self.assertIn("`--version`/`-v`, `--list-models` and `pi update` run anywhere", FLAT["LOCKDOWN.md"])
        self.assertIn("case \"${1:-}\" in update|setup|--list-models|--version|-v) NEEDS_ELM_KEY=0 ;; esac", LAUNCHER)

    def test_configure_defaults_to_qwen(self):
        self.assertIn("picks the best match for a substring (default `qwen`)", FLAT["INSTALL.md"])
        self.assertIn('MATCH="${1:-qwen}"', CONFIGURE)

    def test_configure_refuses_llama_as_install_md_says(self):
        self.assertIn("`configure.sh llama`, or any substring that matches a model that is not Qwen, "
                      "refuses with exit 2 and changes nothing", FLAT["INSTALL.md"])
        self.assertIn('*llama*) refuse_non_qwen', CONFIGURE)
        self.assertIn('*) refuse_non_qwen', CONFIGURE)
        self.assertIn("exit 2", between(CONFIGURE, "refuse_non_qwen() {", "\n}\n"))

    def test_install_sh_with_all_variable_adds_the_flag(self):
        self.assertIn("ELM_PI_WITH_ALL=1 /bin/bash -c", README)
        self.assertIn('[ "${ELM_PI_WITH_ALL:-0}" != "1" ] || PASS_ARGS+=(--with-all)', INSTALL_SH)

    def test_with_all_records_python_and_the_index(self):
        self.assertIn("(recorded as those two)", FLAT["INSTALL.md"])
        block = between(BOOTSTRAP, "    --with-all)", "done ;;")
        self.assertIn("--with-python --with-pypi-index", block)

    def test_pypi_index_implies_python(self):
        self.assertIn("implies `--with-python`", FLAT["INSTALL.md"])
        self.assertIn("--with-pypi-index) WITH_PYPI_INDEX=1; WITH_PYTHON=1 ;;", BOOTSTRAP)

    def test_pi_update_runs_install_sh_update_and_extensions_force_packages(self):
        self.assertIn("`--update` | the latest pi and extension packages", FLAT["INSTALL.md"])
        block = between(LAUNCHER, 'if [ "${1:-}" = "update" ]; then', "\nfi\n")
        self.assertIn('"$HERE/install.sh" --update', block)
        self.assertIn('"$HERE/bootstrap.sh" --force-packages', block)
        self.assertIn("(what `pi update --extensions` runs)", FLAT["INSTALL.md"])


# --- environment variables -----------------------------------------------------------

def _strip_for_reads(text):
    """Code without usage heredocs and comment lines: a name there is not a read."""
    text = re.sub(r"<<'EOU'\n.*?\nEOU\n", "", text, flags=re.S)
    return "\n".join(l for l in text.splitlines()
                     if not re.match(r"\s*(#|//|\*|/\*)", l))


CODE_FILES = ["pi", "install.sh", "bootstrap.sh", "configure.sh", "shim/shim.py", "proxy/egress.py",
              "templates/shell/colour.sh",
              *[str(p.relative_to(ROOT)) for p in sorted(ROOT.glob("lib/*")) if p.suffix in {".sh", ".mjs"}],
              *[str(p.relative_to(ROOT)) for p in sorted(TEMPLATES.glob("extensions/*.ts"))],
              *[str(p.relative_to(ROOT)) for p in sorted(ROOT.glob("scripts/*"))
                if p.is_file() and p.suffix not in {".pyc"}]]
CODE = "\n".join(_strip_for_reads(read(f)) for f in CODE_FILES)


def reads(name, code=CODE):
    n = re.escape(name)
    return re.search(rf"\$\{{?{n}\b|process\.env\.{n}\b|process\.env\[[\"']{n}|environ(?:\.get)?\(\s*[\"']{n}"
                     rf"|environ\[[\"']{n}|getenv\([\"']{n}", code) is not None


ENV_NAME = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")
DOC_ENV = sorted({n for text in [*DOCS.values(), *PROMPTS.values()] for n in ENV_NAME.findall(text)})

# What a documented name is, when it is not a knob this install reads.
NOT_ENV = {"KEY_ISSUED", "MODEL_SPAWN_REJECTED", "APPEND_SYSTEM", "AGENT_DIR", "INSTALL_DIR", "QWEN_MODEL", "LLAMA_MODEL",
           "N_A", "ID_LIKE"}
# The launcher sets these for pi, its packages or the agent; the docs say so.
EXPORTED = {"PI_OFFLINE", "PI_SUBAGENT_PI_BINARY", "PI_ELM_CHILD", "PI_RADIUS_GATEWAY", "ELM_PI_AGENT_PYTHON",
            "PIXI_HOME", "PI_CODING_AGENT_DIR", "HTTPS_PROXY"}
# Read by pi itself, not by this install: checked against the installed pi.
PI_OWN = {"PI_TIMING"}
# Measured and removed (INSTALL.md): nothing may set them.
REMOVED_ENV = {"PI_CACHE_RETENTION", "NODE_COMPILE_CACHE"}
# Commercial credentials and the container-engine variables have their own tests.
CREDENTIALS = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AWS_BEARER_TOKEN_BEDROCK", "COPILOT_GITHUB_TOKEN",
               "GITHUB_TOKEN"}
ENGINE_ENV = {"DOCKER_HOST", "CONTAINER_HOST", "DOCKER_CONTEXT", "CONTAINER_CONNECTION"}
DOC_KNOBS = [n for n in DOC_ENV if n not in NOT_ENV | EXPORTED | PI_OWN | REMOVED_ENV | CREDENTIALS | ENGINE_ENV]

# Where a reader learns a knob exists: the docs, a usage text, or the message
# the code prints when the knob is the way out.
MESSAGES = "\n".join(l for f in CODE_FILES for l in read(f).splitlines()
                     if re.search(r"\b(echo|die|warn|printf|refuse)\b|`\$\{", l))
DOCUMENTED = "\n".join([*DOCS.values(), *USAGES.values(), read("shim/README.md"), MESSAGES])
# Read with a default by the launcher and installers, but handed from one
# script to the next rather than set by anyone.
INTERNAL_ENV = {"ELM_PI_WITH_ALL_SET_UP", "ELM_PI_DISK_NOTED", "ELM_PI_USER_PATH", "ELM_PI_ROOT",
                "ELM_PI_UPSTREAM_PROXY",
                # set by bootstrap.sh / workflow-check for the node scripts they
                # run, and by ./pi for elm-shim.ts
                "ELM_PI_INSTALL_DIR", "ELM_SHIM_PATH",
                # agent/runtime.env, written from config/elm-pi.json
                "ELM_QWEN_MODEL_ID", "ELM_LLAMA_MODEL_ID"}
CODE_KNOBS = sorted(({n for f in ["pi", "install.sh", "bootstrap.sh", "configure.sh", "lib/sandbox.sh",
                                 "lib/state.sh", "lib/policy.sh"]
                     for n in re.findall(r"\$\{((?:ELM_PI|PI_ELM)_[A-Z0-9_]+):?[-=]", read(f))}
                    | {n for n in re.findall(r"process\.env\.((?:ELM|PI_ELM)_[A-Z0-9_]+)", CODE)
                       if n not in {"ELM_ALLOWED_PROVIDERS", "ELM_BUILTIN_PROVIDERS"}}
                    | {"PI_FORCE", "PI_STRICT_LOAD", "PI_CLIPBOARD_OSC52", "PI_VERSION"}) - INTERNAL_ENV)
TOOL_VERSION_VARS = list(dict.fromkeys(re.findall(r'^\s*([A-Z]+_VERSION)="\$\{\1:-', BOOTSTRAP, re.M)))


def usage_env(usage, header):
    return re.findall(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b", between(usage, header, "\n\n"))


PI_HELP_ENV = re.findall(r"^  ([A-Z][A-Z0-9_]+)=", between(PI_USAGE, "Useful environment:", "\n\n"), re.M)
INSTALL_KNOBS = re.findall(r"^\| `(ELM_PI_[A-Z_]+)` \| (.*?) \|$", between(INSTALL, "Installer knobs", "To remove"), re.M)


class EnvironmentTests(unittest.TestCase):
    def test_the_extractions_found_something(self):
        self.assertGreater(len(DOC_KNOBS), 20)
        self.assertGreater(len(CODE_KNOBS), 20)
        self.assertGreaterEqual(len(PI_HELP_ENV), 8)
        self.assertEqual(5, len(INSTALL_KNOBS))


def _knob(self, name):
    """A knob is read by the install and named where a user would look."""
    problems = []
    if not reads(name):
        problems.append("documented but nothing in the install reads it")
    if not re.search(rf"\b{name}\b", DOCUMENTED):
        problems.append("read, but no doc, usage text or message names it")
    self.assertEqual([], problems, name)


def _exported(self, name):
    self.assertRegex(LAUNCHER, rf"(?m)^\s*export {name}=", f"the docs say the launcher sets {name}")


def _removed(self, name):
    for f in CODE_FILES:
        self.assertNotRegex(_strip_for_reads(read(f)), rf"\b{name}\b", f)
    for p in TEMPLATES.rglob("*.json"):
        self.assertNotIn(name, p.read_text(), p)


# Every knob a doc or usage text names, and every one the code reads: one case
# each, both ways.
USAGE_ENV = (PI_HELP_ENV + usage_env(INSTALL_USAGE, "Environment:") + usage_env(BOOT_USAGE, "Environment:")
             + [n for n, _ in INSTALL_KNOBS])
KNOBS = sorted(set(DOC_KNOBS) | set(USAGE_ENV) | set(CODE_KNOBS) | set(TOOL_VERSION_VARS))
generate(EnvironmentTests, [(f"env_{slug(n)}", n) for n in KNOBS], _knob)
generate(EnvironmentTests, [(f"documented_{slug(n)}_is_exported_by_the_launcher", n) for n in sorted(EXPORTED)
                            if n in DOC_ENV], _exported)
generate(EnvironmentTests, [(f"removed_{slug(n)}_is_set_nowhere", n) for n in sorted(REMOVED_ENV)], _removed)

# The default INSTALL.md gives each installer knob, against install.sh's own.
KNOB_DEFAULTS = {
    "ELM_PI_PREFIX": ("`~/.local/share/elm-pi`", 'PREFIX="${ELM_PI_PREFIX:-$HOME/.local/share/elm-pi}"'),
    "ELM_PI_BINDIR": ("`~/.local/bin`", 'BINDIR="${ELM_PI_BINDIR:-$HOME/.local/bin}"'),
    "ELM_PI_BRANCH": ("else `main`", 'BRANCH="${BRANCH:-main}"'),
    "ELM_PI_REPO": ("else `rob-c/elm-pi` on GitHub", 'REPO="${REPO:-https://github.com/rob-c/elm-pi.git}"'),
    "ELM_PI_UPDATE": ("`0`", 'UPDATE="${ELM_PI_UPDATE:-0}"'),
}


def _knob_default(self, name, doc_default, code):
    row = dict(INSTALL_KNOBS)[name]
    self.assertIn(doc_default, row)
    self.assertIn(code, INSTALL_SH)


generate(EnvironmentTests, [(f"install_md_default_of_{slug(n)}_matches_install_sh", n, *v)
                            for n, v in KNOB_DEFAULTS.items()], _knob_default)


# A package whose tools are defined in a library it depends on.
PACKAGE_LIBRARIES = {"@xl0/pi-lovely-notebook": ["@xl0/lovely-notebook"]}


@lru_cache(maxsize=None)
def package_source(name):
    """Every source file of an installed package (or pi's dist), concatenated."""
    base = PI_DIST if name == "pi" else NPM / name
    if not base.is_dir():
        return None
    parts = [package_source(lib) or "" for lib in PACKAGE_LIBRARIES.get(name, [])]
    for path in sorted(base.rglob("*")):
        if path.suffix in {".ts", ".js", ".mjs", ".cjs"} and path.is_file() \
                and "node_modules" not in path.relative_to(base).parts and not path.name.endswith(".map"):
            parts.append(path.read_text(errors="replace"))
    return "\n".join(parts)


# Variables the docs say pi or a package honours, and who reads them.
CONSUMED = {
    "PI_OFFLINE": "pi",                    # INSTALL.md: pi's own `--offline`
    "PI_RADIUS_GATEWAY": "pi",             # LOCKDOWN.md: a supported pi environment variable
    "PI_TIMING": "pi",                     # INSTALL.md: measured with PI_TIMING=1
    "PI_CLIPBOARD_OSC52": "pi",            # INSTALL.md: PI_CLIPBOARD_OSC52=0 turns the copy off
    "PI_SKIP_VERSION_CHECK": "pi",
    "PI_TELEMETRY": "pi",
    "PI_SUBAGENT_PI_BINARY": "pi-subagents",   # INSTALL.md: the documented override
    "PI_HASHLINE_DIR": "pi-hashline-edit-pro",
    "PI_COMPUTER_USE_HELPER_APP_PATH": "@injaneity/pi-computer-use",
}


def _consumed(self, name, package):
    # that the launcher sets it is the EXPORTED cases' to check
    if name not in PI_OWN | EXPORTED:
        self.assertRegex(LAUNCHER, rf"export {name}=", f"the launcher never sets {name}")
    source = package_source(package)
    if source is None:
        self.skipTest(f"{package} is not installed in this checkout")
    self.assertIn(name, source, f"{package} no longer reads {name}")


generate(EnvironmentTests, [(f"{slug(n)}_set_by_the_launcher_is_read_by_{slug(p)}", n, p) for n, p in CONSUMED.items()],
         _consumed)


class SessionDirTests(unittest.TestCase):
    def test_session_dir_precedence_names_pis_variable(self):
        self.assertIn("Precedence is `--session-dir` > `PI_CODING_AGENT_SESSION_DIR` > `sessionDir`", FLAT["INSTALL.md"])
        config = PI_DIST / "config.js"
        if not config.is_file():
            self.skipTest("pi is not installed in this checkout")
        self.assertIn("_CODING_AGENT_SESSION_DIR", config.read_text())

    def test_session_dir_is_relative_dot_pi_sessions(self):
        self.assertIn('`sessionDir: ".pi/sessions"` is **relative**', FLAT["INSTALL.md"])
        self.assertEqual(".pi/sessions", SETTINGS["sessionDir"])


# --- numbers --------------------------------------------------------------------------

RETRY = SETTINGS["retry"]
BACKOFF = [RETRY["baseDelayMs"] * 2 ** k // 1000 for k in range(RETRY["maxRetries"])]
TOOLSET = re.search(r'TOOLSET="\$\{ELM_PI_TOOLS:-([^}]+)\}"', BOOTSTRAP).group(1).split(",")
POLICY_EXTENSIONS = re.search(r'POLICY_EXTENSIONS="([^"]+)"', LAUNCHER).group(1).split()


class NumberTests(unittest.TestCase):
    """Each number a document or prompt quotes, against where it is set."""


STATE_MODES = {int(m) for m in re.findall(r"chmod (\d{3})", read("lib/state.sh"))}
DOTENV_MODES = {int(m) for m in re.findall(r"> \.env; chmod (\d{3}) \.env", BOOTSTRAP)}
PY_MIN = ".".join(re.search(rf"ELM_PY_MIN_{k}=(\d+)", read("lib/sandbox.sh")).group(1) for k in ("MAJOR", "MINOR"))
ROUTER = {k: int(re.search(rf"{k} = (\d+)", SKILL_ROUTER).group(1)) for k in ("MAX_ROUTED", "MAX_INLINED")}

# (name, doc, the claim with its number as {N} - digits, "262,144" or a word -
# {L} for a list of numbers or {V} for a version, what the code or config says)
NUMBER_CLAIMS = [
    ("readme_fan_out_budget_is_the_spawn_limit", "README.md", "{N}-child fan-out budget",
     SUBAGENT["maxSubagentSpawnsPerRun"]),
    ("site_sub_agents_on_tap_is_the_spawn_limit", "docs/index.html", "with {N} sub-agents on tap",
     SUBAGENT["maxSubagentSpawnsPerRun"]),
    ("delegation_budget_is_the_spawn_limit", "skills/elm-delegation/SKILL.md",
     "Budget: {N} child launches per run (`maxSubagentSpawnsPerRun`)", SUBAGENT["maxSubagentSpawnsPerRun"]),
    ("readme_children_at_once_is_the_concurrency_limit", "README.md", "up to {N} children run at once",
     SUBAGENT["globalConcurrencyLimit"]),
    ("delegation_twelve_is_the_concurrency_limit", "skills/elm-delegation/SKILL.md",
     "the rest queue. {N} is where the gateway was measured", SUBAGENT["globalConcurrencyLimit"]),
    ("readme_max_retries", "README.md", "`retry.maxRetries` is {N}", RETRY["maxRetries"]),
    ("readme_provider_max_retries", "README.md", "`retry.provider.maxRetries` is {N}", RETRY["provider"]["maxRetries"]),
    ("readme_retries_from_the_base_delay", "README.md", "{N} from a 1s base delay", RETRY["maxRetries"]),
    ("readme_base_delay_one_second", "README.md", "from a {N}s base delay", RETRY["baseDelayMs"] // 1000),
    ("readme_retry_tolerance", "README.md", "gives ~{N}s of tolerance", sum(BACKOFF)),
    ("install_md_base_delay", "INSTALL.md", "So `baseDelayMs` is **{N}**", RETRY["baseDelayMs"]),
    ("install_md_max_retries", "INSTALL.md", "`maxRetries` **{N}**", RETRY["maxRetries"]),
    ("install_md_backoff_series", "INSTALL.md", "`maxRetries` **6**: {L}s - a short refusal", BACKOFF),
    ("install_md_storm_tolerance", "INSTALL.md", "a long storm still gets ~{N}s", sum(BACKOFF)),
    ("install_md_provider_retries_stay_zero", "INSTALL.md", "`retry.provider.maxRetries` stays at **{N}**",
     RETRY["provider"]["maxRetries"]),
    ("readme_compaction_threshold", "README.md", "compaction owned by `pi-auto-compact` at {N}% of the context window",
     AUTO_COMPACT["autoCompactThreshold"]),
    ("install_md_compaction_threshold", "INSTALL.md", "Compaction (`pi-auto-compact`) starts at **{N}%**",
     AUTO_COMPACT["autoCompactThreshold"]),
    ("append_system_compaction_threshold", "APPEND_SYSTEM.md", "the session is compacted at {N}%",
     AUTO_COMPACT["autoCompactThreshold"]),
    ("append_system_context_window", "APPEND_SYSTEM.md", "The one real limit is the context window ({N} tokens",
     QWEN["contextWindow"]),
    ("readme_context_window", "README.md", "`Qwen/Qwen3.5-397B-A17B-FP8` — {N}K context", QWEN["contextWindow"] // 1000),
    ("site_context_window", "docs/index.html", "a {N}K context", QWEN["contextWindow"] // 1000),
    ("install_md_elm_reports_the_context_window", "INSTALL.md", "ELM reports {N} for Qwen", QWEN["contextWindow"]),
    ("readme_providers_stripped", "README.md", "{N} non-ELM provider catalogues stripped", len(CONFIG["builtinProviders"])),
    ("lockdown_built_in_providers", "LOCKDOWN.md", "ships {N} built-in providers", len(CONFIG["builtinProviders"])),
    ("lockdown_pi_release", "LOCKDOWN.md", "pi {V} ships",
     ".".join(VERSIONS["core"]["@earendil-works/pi-coding-agent"].split(".")[:2])),
    ("readme_skill_count", "README.md", "| **Skills** | {N} —", len(SKILLS)),
    ("install_md_skill_count", "INSTALL.md", "`agent/skills` holds {N} skills", len(SKILLS)),
    ("install_md_package_count", "INSTALL.md", "The set is {N} packages", len(PACKAGES)),
    ("readme_package_count_now", "README.md", "The set is now {N} and has not been re-measured", len(PACKAGES)),
    ("install_md_package_count_now", "INSTALL.md", "It is now {N} and has not been re-measured", len(PACKAGES)),
    ("install_md_tool_count", "INSTALL.md", "All {N} are a single static binary", len(TOOLSET)),
    ("install_md_tools_the_model_reaches_for", "INSTALL.md", "{N} more are there because the *model* keeps reaching",
     len(TOOLSET) - 2),
    ("lockdown_web_tool_count", "LOCKDOWN.md", "`pi-web-access` registers {N} tools", len(CONFIG["webTools"])),
    ("lockdown_excludes_all_web_tools", "LOCKDOWN.md", "passes `--exclude-tools` for all {N}", len(CONFIG["webTools"])),
    ("install_md_notebook_tools_left_out", "INSTALL.md", "and {N} notebook tools with simple substitutes",
     len([t for t in CONFIG["excludedTools"]["always"] if t.startswith("notebook_")])),
    ("install_md_shim_port", "INSTALL.md", "starts it on demand on `127.0.0.1:{N}`",
     int(re.search(r"ELM_SHIM_PORT \?\? (\d+)", ELM_SHIM_TS).group(1))),
    ("install_md_shim_py_default_port", "INSTALL.md", "usually because port {N} is taken",
     int(re.search(r'SHIM_PORT", "(\d+)"', read("shim/shim.py")).group(1))),
    ("install_md_llama_max_tokens", "INSTALL.md", "capped at {N} tokens (`maxTokens`, set in `elm-shim.ts`)",
     int(re.search(r"maxTokens: (\d+)", ELM_SHIM_TS).group(1))),
    ("install_md_command_output_head", "INSTALL.md", "the first {N} and last",
     int(re.search(r"HEAD_LINES = (\d+)", COMMAND_OUTPUT).group(1))),
    ("install_md_command_output_tail", "INSTALL.md", "and last {N} lines",
     int(re.search(r"TAIL_LINES = (\d+)", COMMAND_OUTPUT).group(1))),
    ("install_md_router_inlines", "INSTALL.md", "adds the best {N} matching skills in full", ROUTER["MAX_INLINED"]),
    ("install_md_router_names_more", "INSTALL.md", "and names up to {N} more by path",
     ROUTER["MAX_ROUTED"] - ROUTER["MAX_INLINED"]),
    ("install_md_node_version", "INSTALL.md", "V={V};", CONFIG["nodeVersion"]),
    ("readme_node_major", "README.md", "generated: Node {N} + pi", int(CONFIG["nodeVersion"].lstrip("v").split(".")[0])),
    ("site_node_major", "docs/index.html", "its own copy of Node {N}", int(CONFIG["nodeVersion"].lstrip("v").split(".")[0])),
    ("install_md_python_minimum", "INSTALL.md", "Python {V}+ is used when the system has one", PY_MIN),
    ("delegation_notice_previews", "skills/elm-delegation/SKILL.md", "A completion notice previews only the first {N} children",
     ("pi-subagents", r"CHILD_OUTPUT_PREVIEW_COUNT = (\d+)")),
    ("asking_questions_per_call", "reference/asking.md", "up to {N} questions per call",
     ("@juicesharp/rpiv-ask-user-question", r"MAX_QUESTIONS = (\d+)")),
    # sets: the modes the code applies
    ("readme_state_dirs_mode", "README.md", "Session and memory directories are mode {N}", STATE_MODES),
    ("readme_state_files_mode", "README.md", "existing state files are tightened to mode {N}", STATE_MODES),
    ("readme_locked_credentials_mode", "README.md", "locked credentials use mode {N}", STATE_MODES),
    ("lockdown_locked_auth_mode", "LOCKDOWN.md", "locked `auth.json` is mode {N}", STATE_MODES),
    ("install_md_dotenv_mode", "INSTALL.md", "`.env` is written mode {N}", DOTENV_MODES),
    ("site_dotenv_mode", "docs/index.html", "Writes your key to .env with mode {N}", DOTENV_MODES),
]
CAPTURES = {"{N}": r"(\d[\d,]*|[a-z]+)", "{L}": r"(\d+(?:, \d+)+)", "{V}": r"(v?\d+(?:\.\d+)+)"}


def parse_number(text):
    if text in NUMBER_WORDS or text.capitalize() in map(str.capitalize, NUMBER_WORDS):
        return NUMBER_WORDS[text.lower()]
    if re.fullmatch(r"\d[\d,]*", text):
        return int(text.replace(",", ""))
    if re.fullmatch(r"\d+(?:, \d+)+", text):
        return [int(x) for x in text.split(", ")]
    return text


def _number(self, doc, claim, actual):
    text = FLAT.get(doc) or PROMPT_FLAT.get(doc)
    pattern = re.escape(claim)
    for token, capture in CAPTURES.items():
        pattern = pattern.replace(re.escape(token), capture)
    match = re.search(pattern, text, re.I)
    self.assertIsNotNone(match, f"{doc} no longer says {claim!r}")
    said = parse_number(match.group(1).lower() if match.group(1).isalpha() else match.group(1))
    if isinstance(actual, tuple):           # measured from an installed package
        package, source_pattern = actual
        source = package_source(package)
        if source is None:
            self.skipTest(f"{package} is not installed in this checkout")
        actual = int(re.search(source_pattern, source).group(1))
    if isinstance(actual, set):
        self.assertIn(said, actual, f"{doc}: {match.group(0)!r}")
    else:
        self.assertEqual(actual, said, f"{doc}: {match.group(0)!r}")


generate(NumberTests, NUMBER_CLAIMS, _number)


class PiDefaultTests(unittest.TestCase):
    """What the docs say pi itself does by default, against the installed pi."""

    def setUp(self):
        if not (PI_DIST / "core/settings-defaults.js").is_file():
            self.skipTest("pi is not installed in this checkout")

    def test_pis_default_max_retries_is_three(self):
        self.assertIn("The default `maxRetries: 3` gives ~14s of tolerance", FLAT["INSTALL.md"])
        self.assertIn("maxRetries: 3,", (PI_DIST / "core/settings-defaults.js").read_text())

    def test_pis_default_base_delay_is_two_seconds(self):
        self.assertIn("With a 2s base the waits were 2, 4, 8 and 16s", FLAT["INSTALL.md"])
        self.assertIn("baseDelayMs: 2000,", (PI_DIST / "core/settings-defaults.js").read_text())

    def test_pis_idle_timeout_is_300_seconds(self):
        self.assertIn("pi gives up on a connection that sends nothing for 300 s", FLAT["INSTALL.md"])
        self.assertIn("httpIdleTimeoutMs (300 s)", ELM_SHIM_TS)
        self.assertIn("DEFAULT_HTTP_IDLE_TIMEOUT_MS = 300_000", (PI_DIST / "core/http-dispatcher.js").read_text())

    def test_bug_uploads_to_radius_bug_reports(self):
        self.assertIn("`https://radius.pi.dev/v1/bug-reports`", FLAT["LOCKDOWN.md"])
        self.assertIn('"/v1/bug-reports"', (PI_DIST / "core/bug-report-upload.js").read_text())

    def test_pi_engine_requirement_is_node_22_19(self):
        self.assertIn("pi needs Node ≥ 22.19", FLAT["INSTALL.md"])
        engines = json.loads((PI_DIST.parent / "package.json").read_text())["engines"]["node"]
        self.assertEqual(">=22.19.0", engines)
        major, minor = (int(x) for x in CONFIG["nodeVersion"].lstrip("v").split(".")[:2])
        self.assertGreaterEqual((major, minor), (22, 19))

    # LOCKDOWN.md: "kept in step with the variables pi-ai 1.5 itself reads"
    def test_lockdown_names_the_installed_pi_ai_release(self):
        version = json.loads((ROOT / "node_modules/@earendil-works/pi-ai/package.json").read_text())["version"]
        self.assertIn(f"pi-ai {'.'.join(version.split('.')[:2])} itself reads", FLAT["LOCKDOWN.md"])


BUILTIN_EXTENSIONS = ["mcp", "llama.cpp", "codemode", "tool-search"]


class BuiltinExtensionTests(unittest.TestCase):
    """LOCKDOWN.md, "pi's built-in extensions"."""

    def test_codemode_and_tool_search_are_not_turned_off(self):
        self.assertIn("`codemode` and `tool-search` stay loaded but inactive", FLAT["LOCKDOWN.md"])
        for name in ("codemode", "tool-search"):
            self.assertNotIn(f"-builtin:{name}", SETTINGS["extensions"])

    def test_neither_default_tools_nor_tools_is_set(self):
        self.assertIn("unless `defaultTools` or `--tools` names it, and this install sets neither", FLAT["LOCKDOWN.md"])
        self.assertNotIn("defaultTools", SETTINGS)
        self.assertNotRegex(LAUNCHER, r"PRE\+=\(--tools\b")

    def test_extensions_is_installer_owned(self):
        self.assertIn("(`extensions` is an installer-owned key)", FLAT["LOCKDOWN.md"])
        self.assertIn('"extensions",', BOOTSTRAP)


def _builtin_exists(self, name):
    self.assertIn(f"`builtin:{name}`", FLAT["LOCKDOWN.md"])
    source = package_source("pi")
    if source is None:
        self.skipTest("pi is not installed in this checkout")
    self.assertRegex(source, rf'name: ?"{re.escape(name)}"', f"pi has no builtin:{name}")


generate(BuiltinExtensionTests, [(f"builtin_{slug(n)}_exists_in_pi", n) for n in BUILTIN_EXTENSIONS], _builtin_exists)


# --- what pi --list-models shows, as quoted in INSTALL.md and LOCKDOWN.md ------------

def _k(n):
    return f"{n / 1000:.1f}K".replace(".0K", "K")


SHIM_MODEL = {
    "contextWindow": int(re.search(r"contextWindow: (\d+)", ELM_SHIM_TS).group(1)),
    "maxTokens": int(re.search(r"maxTokens: (\d+)", ELM_SHIM_TS).group(1)),
    "reasoning": re.search(r"reasoning: (true|false)", ELM_SHIM_TS).group(1) == "true",
    "input": re.search(r"input: \[([^\]]*)\]", ELM_SHIM_TS).group(1),
}
LIST_ROWS = {
    "elm": (CONFIG["models"]["qwen"], {"context": _k(QWEN["contextWindow"]), "max-out": _k(QWEN["maxTokens"]),
                                       "thinking": "yes" if QWEN["reasoning"] else "no",
                                       "images": "yes" if "image" in QWEN["input"] else "no"}),
    "elm-shim": (CONFIG["models"]["llama"], {"context": _k(SHIM_MODEL["contextWindow"]),
                                             "max-out": _k(SHIM_MODEL["maxTokens"]),
                                             "thinking": "yes" if SHIM_MODEL["reasoning"] else "no",
                                             "images": "yes" if "image" in SHIM_MODEL["input"] else "no"}),
}
COLUMNS = ["context", "max-out", "thinking", "images"]


class ListModelsTableTests(unittest.TestCase):
    pass


def _list_cell(self, doc, provider, column):
    model, cells = LIST_ROWS[provider]
    row = re.search(rf"^{re.escape(provider)}\s+{re.escape(model)}\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", DOCS[doc], re.M)
    self.assertIsNotNone(row, f"{doc}: no --list-models row for {provider} {model}")
    self.assertEqual(cells[column], row.group(COLUMNS.index(column) + 1), f"{doc}: {provider} {column}")


generate(ListModelsTableTests, [(f"{slug(d)}_{slug(p)}_{slug(c)}", d, p, c)
                                for d in ("INSTALL.md", "LOCKDOWN.md") for p in LIST_ROWS for c in COLUMNS], _list_cell)


# --- model ids -----------------------------------------------------------------------

class ModelIdTests(unittest.TestCase):
    def test_the_id_the_skill_calls_wrong_is_not_the_configured_one(self):
        self.assertIn("`elm/qwen-3.5-397b`, an id that does not exist", PROMPT_FLAT["skills/elm-dynamic-workflows/SKILL.md"])
        self.assertNotEqual("qwen-3.5-397b", CONFIG["models"]["qwen"])
        self.assertIn("Not `qwen-3.5-397b`", FLAT["INSTALL.md"])

    def test_vision_claim_matches_qwens_inputs(self):
        self.assertIn("262K context, tool calling, vision", FLAT["README.md"])
        self.assertIn("image", QWEN["input"])

    def test_only_qwen_sees_images(self):
        # AGENTS.md: "Only `qwen` sees images"
        self.assertIn("Only `qwen` sees images", flat(AGENTS_MD))
        self.assertNotIn("image", SHIM_MODEL["input"])
        self.assertIn("view", re.search(r"^excludeTools: (.*)$", PROMPTS["agents/llama.md"], re.M).group(1).split(", "))

    def test_served_models_are_the_two_allowed_providers(self):
        self.assertIn("Only `elm/@QWEN_MODEL@` and `elm-shim/@LLAMA_MODEL@` are served", flat(AGENTS_MD))
        self.assertEqual(["elm", "elm-shim"], CONFIG["allowedProviders"])
        self.assertEqual(["elm"], list(MODELS["providers"]))
        self.assertIn('pi.registerProvider("elm-shim"', ELM_SHIM_TS)

    def test_the_gateway_url_is_the_one_install_md_curls(self):
        self.assertIn("https://elm.edina.ac.uk/api/v1/chat/completions", INSTALL)
        self.assertEqual("https://elm.edina.ac.uk/api/v1", MODELS["providers"]["elm"]["baseUrl"])
        self.assertIn('BASE="${ELM_BASE_URL:-https://elm.edina.ac.uk/api/v1}"', CONFIGURE)


def _ids(self, doc, pattern, key):
    text = DOCS.get(doc) or PROMPTS.get(doc)
    found = set(re.findall(pattern, text))
    self.assertTrue(found)
    self.assertEqual({CONFIG["models"][key]}, found, doc)


_ID_CASES = []
for _doc, _text in {**DOCS, **PROMPTS}.items():
    for _key, _pattern in (("qwen", r"Qwen/Qwen[\w.-]*\w"), ("llama", r"meta-llama/Llama[\w.-]*\w")):
        if re.search(_pattern, _text):
            _ID_CASES.append((f"{_key}_ids_in_{slug(_doc)}_are_the_configured_one", _doc, _pattern, _key))
generate(ModelIdTests, _ID_CASES, _ids)


# --- extensions --------------------------------------------------------------------------

REQUIRED = CONFIG["requiredExtensions"]
INSTALL_EXT_ROWS = re.findall(r"^\| `agent/extensions/([\w.-]+\.ts)` \|", INSTALL, re.M)
LAYER3 = between(FLAT["LOCKDOWN.md"], "### 3. Catalogue strip", "Measured on this install")
FAST_LEVER = between(FLAT["INSTALL.md"], "1. **`pi --fast`** for one-shot work.", "Measured on the three-package set")
FAST_NAMES = {"elm-only": "the ELM-only guard", "protected-paths": "protected paths",
              "pinned-instructions": "pinned instructions", "trust-guard": "trust guard",
              "command-guard": "command guard"}


class ExtensionDocTests(unittest.TestCase):
    # LOCKDOWN.md: "If one of the five local files is missing", against
    # POLICY_EXTENSIONS in ./pi.
    def test_layer_3_counts_the_policy_files(self):
        match = re.search(r"If one of the (\w+) local files is missing", LAYER3)
        self.assertIsNotNone(match)
        self.assertEqual(len(POLICY_EXTENSIONS), NUMBER_WORDS.get(match.group(1)), "LOCKDOWN.md layer 3 file count")

    def test_policy_set_includes_the_permission_gate(self):
        self.assertIn("and the permission gate", LAYER3)
        self.assertIn('GATE="$GATE_PKG/src/index.ts"', LAUNCHER)

    def test_command_guard_loads_wherever_the_gate_does(self):
        self.assertIn("It loads wherever the gate does: plain sessions, `--fast`, `-ne` and workflow agents",
                      FLAT["LOCKDOWN.md"])
        self.assertIn("command-guard", POLICY_EXTENSIONS)
        self.assertIn("command-guard", WORKFLOWS["providerMiddlewareExtensions"])
        self.assertIn("command-guard.ts", REQUIRED)

    def test_workflow_model_scope_is_required(self):
        self.assertIn("`agent/extensions/workflow-model-scope.ts` is a **required** extension", FLAT["INSTALL.md"])
        self.assertIn("workflow-model-scope.ts", REQUIRED)

    def test_skill_router_line_is_labelled_skills(self):
        self.assertIn("shown as a dim `skills:` line", FLAT["README.md"])
        self.assertIn("shown as a dim `skills: ...` line", FLAT["INSTALL.md"])
        self.assertIn("`skills: ${", SKILL_ROUTER)

    def test_install_notes_logs_to_installs_log(self):
        self.assertIn("logged in `agent/installs.log`", FLAT["README.md"])
        self.assertIn("installs.log", INSTALL_NOTES)

    def test_view_outputs_uses_the_bundled_mupdf(self):
        self.assertIn("Uses the bundled `mupdf`", FLAT["INSTALL.md"])
        self.assertIn("mupdf", VIEW_OUTPUTS)
        self.assertIn("mupdf", VERSIONS["core"])


def _in_layer3(self, name):
    if name == "elm-only":
        self.assertIn("(`agent/extensions/elm-only.ts`)", LAYER3)
    else:
        self.assertIn(f"`{name}.ts`", between(LAYER3, "the launcher loads the policy set", "pi does not start"),
                      f"LOCKDOWN.md layer 3 does not name {name}.ts in the policy set")


def _in_fast_lever(self, name):
    self.assertIn(FAST_NAMES[name], FAST_LEVER, f"INSTALL.md's --fast lever does not name {name}")


generate(ExtensionDocTests, both("extension", "requiredExtensions", REQUIRED, "INSTALL.md's generated-file table",
                                 INSTALL_EXT_ROWS), _in_both)
generate(ExtensionDocTests, [(f"policy_extension_{slug(n)}_is_in_lockdown_layer_3", n) for n in POLICY_EXTENSIONS],
         _in_layer3)
generate(ExtensionDocTests, [(f"policy_extension_{slug(n)}_is_in_install_md_fast_lever", n) for n in POLICY_EXTENSIONS],
         _in_fast_lever)

# elm-dynamic-workflows: "This install loads the ELM-only policy, the permission
# gate, the protected-paths guard and cc-safety-net into them"
SKILL_MIDDLEWARE = {"the ELM-only policy": "elm-only", "the permission gate": "@gotgenes/pi-permission-system",
                    "the protected-paths guard": "protected-paths", "cc-safety-net": "cc-safety-net"}
generate(ExtensionDocTests,
         [(f"workflow_skill_middleware_{slug(n)}_is_loaded", phrase, n) for phrase, n in SKILL_MIDDLEWARE.items()],
         lambda self, phrase, n: (self.assertIn(phrase, PROMPT_FLAT["skills/elm-dynamic-workflows/SKILL.md"]),
                                  self.assertIn(n, WORKFLOWS["providerMiddlewareExtensions"])))

# view-outputs: the converters INSTALL.md names are the ones the extension tries.
CONVERTERS = {"rsvg-convert": "rsvg-convert", "Inkscape": "inkscape", "ImageMagick": "magick",
              "Ghostscript": '"gs"', "epstopdf": "epstopdf", "sips": "sips", "qlmanage": "qlmanage"}
generate(ExtensionDocTests,
         [(f"view_outputs_handles_{slug(k)}", k, v) for k, v in CONVERTERS.items()],
         lambda self, k, v: (self.assertIn(k, FLAT["INSTALL.md"].split("`agent/extensions/view-outputs.ts`")[1][:900]),
                             self.assertIn(v, VIEW_OUTPUTS.lower())))

# install-notes: "when the agent installs something (pip, pixi, docker pull, brew)"
generate(ExtensionDocTests,
         [(f"install_notes_handles_{slug(k)}", k) for k in ("pip", "pixi", "docker", "brew")],
         lambda self, k: (self.assertIn("(pip, pixi, docker pull, brew)", FLAT["INSTALL.md"]),
                          self.assertRegex(INSTALL_NOTES, rf"\b{k}\b")))

# command-guard: the wrappers LOCKDOWN.md and INSTALL.md say it looks through.
WRAPPERS = set(re.findall(r'^\t\["([\w-]+)", \{', COMMAND_GUARD, re.M))
LOCKDOWN_WRAPPERS = ["sudo", "env", "xargs", "command", "exec", "nohup", "timeout", "uvx", "parallel"]
SUBCOMMAND_WRAPPERS = [("pixi", "run"), ("pixi", "exec"), ("uv", "run"), ("pipx", "run")]
generate(ExtensionDocTests,
         [(f"command_guard_looks_behind_{slug(w)}", w) for w in LOCKDOWN_WRAPPERS],
         lambda self, w: (self.assertIn(f"`{w}`", between(FLAT["LOCKDOWN.md"], "A denied command spelled so its rules miss",
                                                           "is refused by")),
                          self.assertIn(w, WRAPPERS)))
generate(ExtensionDocTests,
         [(f"command_guard_looks_inside_{slug(w)}_{s}", w, s) for w, s in SUBCOMMAND_WRAPPERS],
         lambda self, w, s: (self.assertIn(f"{w} {s}", FLAT["LOCKDOWN.md"]),
                             self.assertRegex(between(COMMAND_GUARD, f'["{w}", {{', "}],"),
                                              rf'subcommands: \[[^\]]*"{s}"')))
generate(ExtensionDocTests,
         [(f"command_guard_checks_{slug(n)}", n) for n in sorted(ENGINE_ENV)],
         lambda self, n: (self.assertIn(f"`{n}`", LOCKDOWN), self.assertIn(f'"{n}"', COMMAND_GUARD)))


class ShellWrapperTests(unittest.TestCase):
    def test_bash_c_and_eval_payloads_are_read(self):
        self.assertIn("or inside `bash -c`/`eval`", FLAT["LOCKDOWN.md"])
        self.assertIn('"bash"', re.search(r"const SHELLS = new Set\(\[([^\]]*)\]\)", COMMAND_GUARD).group(1))
        self.assertIn('name === "eval"', COMMAND_GUARD)


# --- colour.sh ------------------------------------------------------------------------

WRAPPED = (set(re.findall(r"^_pi_flag ([\w-]+)", COLOUR, re.M))
           | set(re.findall(r"^_pi_has ([\w-]+) && \1\(\)", COLOUR, re.M))
           | ({"ls"} if re.search(r"^\t+ls\(\) \{", COLOUR, re.M) else set())
           | ({"python -m pytest"} if "_pi_python python" in COLOUR else set()))
GIT_SUBS = re.search(r"^\t\t((?:[\w-]+ \| )+[\w-]+)\)\n\t\t\tif _pi_here", COLOUR, re.M).group(1).split(" | ")
COLOUR_ROW = INSTALL.split("| `agent/shell/colour.sh` |")[1].split("\n")[0]
INSTALL_COLOURED = re.findall(r"`([^`]+)`", COLOUR_ROW.split("colour their output")[0].split("`settings.json`):")[1])
INSTALL_GIT_SUBS = re.search(r"`git` \(([^)]*)\)", COLOUR_ROW).group(1).split(", ")
AGENTS_COLOURED = re.findall(r"`([^`]+)`", flat(AGENTS_MD).split("colour their output for the user")[0].rsplit(".", 1)[1])


class ColourTests(unittest.TestCase):
    pass


generate(ColourTests,
         both("coloured", "colour.sh's wrappers", sorted(WRAPPED), "INSTALL.md's colour.sh row", INSTALL_COLOURED)
         + both("coloured_git", "colour.sh's git subcommands", GIT_SUBS, "INSTALL.md's git list", INSTALL_GIT_SUBS),
         _in_both)
generate(ColourTests, [(f"agents_md_coloured_{slug(c)}_is_wrapped", c, WRAPPED, "AGENTS.md") for c in AGENTS_COLOURED
                       if c not in INSTALL_COLOURED],
         _flag_in)
# (a name in both lists is already a case of `both` above)


class ColourSwitchTests(unittest.TestCase):
    def test_no_color_turns_the_wrappers_off(self):
        self.assertIn("`NO_COLOR=1` turns them off", FLAT["INSTALL.md"])
        self.assertIn('[ -z "$NO_COLOR" ] || return 0', COLOUR)

    def test_shell_command_prefix_sources_colour_sh(self):
        self.assertIn("(`shellCommandPrefix` in `settings.json`)", FLAT["INSTALL.md"])
        self.assertIn("shell/colour.sh", SETTINGS["shellCommandPrefix"])


# --- the bundled tools ---------------------------------------------------------------------

TOOLBOX_ROWS = re.findall(r"^\| `([\w-]+)` \|", between(INSTALL, "### The rest of the toolbox", "All eleven are"), re.M)
SKILL_TOOL_LINE = between(PROMPT_FLAT["skills/installing-software/SKILL.md"], "`agent/bin` has", "On a cluster")
SKILL_TOOLS = [w for w in re.findall(r"[\w-]+", re.sub(r"\([^)]*\)", "", SKILL_TOOL_LINE.split(" has ", 1)[1]))
               if w != "and"]
NO_TOOLS_DESCRIPTIONS = {
    "install_sh_help": re.search(r"^  --no-tools\s+(.*)$", INSTALL_USAGE, re.M).group(1),
    "bootstrap_help": re.search(r"^  --no-tools\s+(.*)$", BOOT_USAGE, re.M).group(1),
    "install_md": re.search(r"^\| `--no-tools` \| (.*) \|$", INSTALL, re.M).group(1),
}


class ToolsetTests(unittest.TestCase):
    pass


SITE_TOOLS = re.findall(r"[\w-]+", between(FLAT["docs/index.html"], "command-line tools inside that directory —",
                                           "and more").split("—", 1)[1])
generate(ToolsetTests,
         both("installing_software_tool", "TOOLSET in bootstrap.sh", TOOLSET, "installing-software's agent/bin list",
              SKILL_TOOLS)
         # fd and rg are introduced above the table, as the two pi needs
         + both("install_md_toolbox_tool", "TOOLSET in bootstrap.sh", TOOLSET, "INSTALL.md's toolbox table",
                TOOLBOX_ROWS + ["fd", "rg"]),
         _in_both)
generate(ToolsetTests, [(f"site_tool_{slug(t)}_is_bundled", t, TOOLSET, "TOOLSET in bootstrap.sh") for t in SITE_TOOLS],
         _flag_in)


def _no_tools_names_every_tool(self, where):
    described = NO_TOOLS_DESCRIPTIONS[where]
    self.assertEqual([], [t for t in TOOLSET if not mentions(described, t)], f"--no-tools in {where}: {described}")


generate(ToolsetTests, [(f"no_tools_in_{w}_names_every_bundled_tool", w) for w in NO_TOOLS_DESCRIPTIONS],
         _no_tools_names_every_tool)

# Commands the prompts tell the model to run from agent/bin, and bootstrap's link.
BIN_HELPERS = {"workflow-check": "AGENTS.md", "conda-search": "skills/installing-software/SKILL.md",
               "pypi-search": "skills/installing-software/SKILL.md", "brew": "LOCKDOWN.md"}


def _bin_helper(self, name, doc):
    self.assertIn(f"`{name}", DOCS.get(doc) or PROMPTS.get(doc))
    self.assertIn(f'ln -sfn "$HERE/scripts/{name}" agent/bin/{name}', BOOTSTRAP)
    self.assertTrue((ROOT / "scripts" / name).is_file())


generate(ToolsetTests, [(f"agent_bin_{slug(n)}_is_linked_by_bootstrap", n, d) for n, d in BIN_HELPERS.items()], _bin_helper)


class ToolCacheTests(unittest.TestCase):
    def test_tool_cache_default_and_override(self):
        self.assertIn("under `~/.cache/elm-pi/tools` (`ELM_PI_TOOL_CACHE` moves it)", FLAT["INSTALL.md"])
        self.assertIn('TOOL_CACHE="${ELM_PI_TOOL_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/elm-pi/tools}"', BOOTSTRAP)

    def test_tools_are_checked_against_tools_sha256(self):
        self.assertIn("sha256-checked against `templates/tools.sha256`", FLAT["INSTALL.md"])
        self.assertIn("tools.sha256", BOOTSTRAP)

    def test_node_is_checked_against_shasums(self):
        self.assertIn("after a SHA-256 check against `SHASUMS256.txt`", FLAT["INSTALL.md"])
        self.assertIn("SHASUMS256.txt", BOOTSTRAP)

    def test_resvg_has_no_arm_linux_build_before_0_49(self):
        # INSTALL.md: "64-bit ARM Linux has no 0.48 build"
        self.assertIn("64-bit ARM Linux has no 0.48 build", FLAT["INSTALL.md"])
        version = re.search(r'RESVG_VERSION="\$\{RESVG_VERSION:-([0-9.]+)\}"', BOOTSTRAP).group(1)
        self.assertTrue(version.startswith("0.48"))
        self.assertNotIn(f"resvg/{version}/resvg-linux-aarch64", read("templates/tools.sha256"))


# --- python ----------------------------------------------------------------------------

INSTALL_PY_PACKAGES = re.split(r",\s*|\s+and\s+",
                               between(FLAT["INSTALL.md"], "`python.packages` - ", ". The launcher").split(" - ", 1)[1])


class PythonPackageTests(unittest.TestCase):
    def test_python_version_comes_from_the_config(self):
        self.assertIn("(`python.version` in `config/elm-pi.json`)", FLAT["INSTALL.md"])
        self.assertRegex(CONFIG["python"]["version"], r"^3\.\d+$")
        self.assertIn("value pythonVersion", BOOTSTRAP)


generate(PythonPackageTests, both("agent_python_package", "python.packages", CONFIG["python"]["packages"],
                                  "INSTALL.md's agent Python list", INSTALL_PY_PACKAGES), _in_both)


# --- skills --------------------------------------------------------------------------

AGENTS_PHYSICS = re.findall(r"`([a-z-]+)`", between(flat(AGENTS_MD), "The physics skills:", "Each is a checked procedure"))


class SkillDocTests(unittest.TestCase):
    pass


generate(SkillDocTests,
         [(f"skill_{slug(s)}_is_named_in_agents_md", s) for s in SKILLS],
         lambda self, s: self.assertIn(f"`{s}`", AGENTS_MD, f"nothing in AGENTS.md points the model at {s}"))
generate(SkillDocTests,
         [(f"agents_md_physics_skill_{slug(s)}_exists", s) for s in AGENTS_PHYSICS],
         lambda self, s: self.assertIn(s, SKILLS))


# --- packages, tools and commands the docs and prompts name ----------------------------

DOC_PACKAGE_NAMES = sorted({m for text in [*DOCS.values(), *PROMPTS.values()]
                            for m in re.findall(r"`(@[a-z0-9-]+/[a-z0-9.-]+|pi-[a-z0-9-]+)`", text)})
# INSTALL.md and README.md: dropped, and said to be gone.
REMOVED_PACKAGES = {"pi-hermes-memory", "pi-zentui", "pi-powerline-footer"}


def short(name):
    return name.rsplit("/", 1)[-1]


class PackageDocTests(unittest.TestCase):
    def test_computer_use_is_installed_but_not_in_settings(self):
        self.assertIn("it is installed with the other packages but is not in `settings.json`'s list", FLAT["LOCKDOWN.md"])
        self.assertIn("@injaneity/pi-computer-use", PACKAGES)
        self.assertNotIn("npm:@injaneity/pi-computer-use", json.dumps(SETTINGS["packages"]))

    def test_dynamic_workflows_is_loaded_by_default(self):
        self.assertIn("**is** loaded by the default package set", FLAT["LOCKDOWN.md"])
        self.assertIn("npm:@quintinshaw/pi-dynamic-workflows", SETTINGS["packages"])

    def test_install_md_three_package_set_is_still_installed(self):
        self.assertIn("(`pi-subagents`, `pi-hashline-edit-pro`, `pi-web-access`)", FLAT["INSTALL.md"])
        for name in ("pi-subagents", "pi-hashline-edit-pro", "pi-web-access"):
            self.assertIn(name, PACKAGES)

    def test_no_memory_tool_package(self):
        self.assertIn("No memory tool: `pi-hermes-memory` is not installed", FLAT["README.md"])
        self.assertFalse([p for p in PACKAGES if "memory" in p])


def _named_package(self, name):
    if name in REMOVED_PACKAGES:
        self.assertNotIn(name, {short(p) for p in PACKAGES}, f"{name} is said to be removed but is installed")
    else:
        self.assertIn(name if name.startswith("@") else name, {*PACKAGES, *map(short, PACKAGES)},
                      f"the docs name {name}, which templates/packages.json does not install")


generate(PackageDocTests, [(f"named_package_{slug(n)}", n) for n in DOC_PACKAGE_NAMES], _named_package)

# INSTALL.md's package table: each package exists and provides what it says.
PACKAGE_TABLE = re.findall(r"^\| `([@\w/.-]+)` \| (.*) \|$", between(INSTALL, "| Package | |", "> pi packages run"), re.M)
generate(PackageDocTests, [(f"install_md_package_row_{slug(n)}_is_installed_and_loaded", n) for n, _ in PACKAGE_TABLE],
         lambda self, n: (self.assertIn(n, PACKAGES), self.assertIn(f"npm:{n}", SETTINGS["packages"])))

# Where each tool the docs and prompts name comes from.
LOCAL_TOOL_FILES = {"pin_instruction": "pinned-instructions.ts", "unpin_instruction": "pinned-instructions.ts",
                    "todo": "todo.ts", "view": "view-outputs.ts"}
TOOL_HOME = {
    **{t: "pi-subagents" for t in ("subagent", "bg_wait", "subagent_supervisor", "contact_supervisor")},
    **{t: "pi-hashline-edit-pro" for t in ("read", "grep", "replace", "replace_match", "insert", "undo_last_change")},
    **{t: "pi-web-access" for t in CONFIG["webTools"]},
    **{t: "pi-python" for t in ("python", "python_set_interpreter")},
    **{t: "@quintinshaw/pi-dynamic-workflows" for t in ("workflow", "workflow_control")},
    **{t: "@tmustier/pi-ralph-wiggum" for t in ("ralph_start", "ralph_done")},
    "ask_user_question": "@juicesharp/rpiv-ask-user-question",
}
NOTEBOOK = "@xl0/pi-lovely-notebook"
# Backticked a_b tokens that are not tools.
NOT_TOOLS = {"node_modules", "tool_calls", "add_executable", "cmake_minimum_required", "target_compile_options",
             "target_link_libraries"}
REMOVED_TOOLS = {"memory_add", "memory_replace", "memory_remove", "memory_search"}
UNDERSCORE_TOKENS = sorted({t for text in [*DOCS.values(), *PROMPTS.values()]
                            for t in re.findall(r"`([a-z]+(?:_[a-z]+)+)`", text)} - NOT_TOOLS)
SINGLE_WORD_TOOLS = ["subagent", "workflow", "view", "todo", "python", "replace", "insert", "read", "grep"]


REGISTRATION = re.compile(r"""(?:\bname|_NAME)\s*[:=]\s*["']([\w:-]+)["']""")
_REGISTERED = {}


def registers(source, tool):
    """The tool's name as a registration gives it: `name: "x"` or a *_NAME = "x" constant."""
    key = id(source)   # package_source is cached, so one string per package
    if key not in _REGISTERED:
        _REGISTERED[key] = (source, set(REGISTRATION.findall(source)))
    return tool in _REGISTERED[key][1]


def tool_source(tool):
    if tool in LOCAL_TOOL_FILES:
        return "local", read(f"templates/extensions/{LOCAL_TOOL_FILES[tool]}")
    package = NOTEBOOK if tool.startswith("notebook_") else TOOL_HOME.get(tool)
    return package, (package_source(package) if package else None)


class ToolNameTests(unittest.TestCase):
    """Every tool a doc or prompt names is registered by the extension or package it belongs to."""


def _tool_exists(self, tool):
    package, source = tool_source(tool)
    self.assertIsNotNone(package, f"`{tool}`: no extension or package is known to provide it")
    if package != "local":
        self.assertIn(package, PACKAGES)
        if source is None:
            self.skipTest(f"{package} is not installed in this checkout")
    self.assertTrue(registers(source, tool), f"`{tool}` is not registered by {package}")


def _tool_is_gone(self, tool):
    self.assertIn(f"`{tool}`", PROMPTS["reference/project-memory.md"])
    for package in PACKAGES:
        source = package_source(package)
        if source is not None:
            self.assertFalse(registers(source, tool), package)
    for path in TEMPLATES.glob("extensions/*.ts"):
        self.assertNotIn(tool, path.read_text(), path)


generate(ToolNameTests, [(f"named_tool_{slug(t)}_exists", t) for t in UNDERSCORE_TOKENS if t not in REMOVED_TOOLS],
         _tool_exists)
generate(ToolNameTests, [(f"named_tool_{slug(t)}_exists", t) for t in SINGLE_WORD_TOOLS
                         if any(f"`{t}`" in text or f"`{t}(" in text for text in PROMPTS.values())], _tool_exists)
generate(ToolNameTests, [(f"removed_tool_{slug(t)}_is_registered_nowhere", t) for t in sorted(REMOVED_TOOLS)], _tool_is_gone)


def _excluded_tool(self, agent, tool):
    if tool in CONFIG["webTools"] or tool in LOCAL_TOOL_FILES or tool in TOOL_HOME:
        _tool_exists(self, tool)
    else:
        self.fail(f"agents/{agent}.md excludes `{tool}`, which nothing provides - pi ignores it silently")


AGENT_DEFS = {name: dict(line.split(": ", 1) for line in re.match(r"---\n(.*?)\n---\n", PROMPTS[f"agents/{name}.md"],
                                                                 re.S).group(1).splitlines())
              for name in ("qwen", "llama")}
generate(ToolNameTests, [(f"{a}_excluded_tool_{slug(t)}_exists", a, t) for a, d in AGENT_DEFS.items()
                         for t in d["excludeTools"].split(", ") if t not in CONFIG["webTools"]], _excluded_tool)
generate(ToolNameTests, [(f"{a}_excludes_web_tool_{slug(t)}", a, t) for a in AGENT_DEFS for t in CONFIG["webTools"]],
         lambda self, a, t: self.assertIn(t, AGENT_DEFS[a]["excludeTools"].split(", ")))


def _excluded_exists(self, tool, package):
    source = package_source(package)
    if source is None:
        self.skipTest(f"{package} is not installed in this checkout")
    # the config's own comment: pi ignores an exclusion for a tool that does not exist
    self.assertTrue(registers(source, tool), f"{package} registers no `{tool}`")


generate(ToolNameTests,
         [(f"always_excluded_{slug(t)}_exists", t, NOTEBOOK) for t in CONFIG["excludedTools"]["always"]]
         + [(f"workflow_excluded_{slug(t)}_exists", t, "@quintinshaw/pi-dynamic-workflows")
            for t in CONFIG["excludedTools"]["workflows"]],
         _excluded_exists)
generate(ToolNameTests,
         [(f"always_excluded_{slug(t)}_is_named_by_no_prompt", t) for t in CONFIG["excludedTools"]["always"]],
         lambda self, t: self.assertEqual([], [n for n, text in PROMPTS.items() if t in text],
                                          f"a prompt tells the model to use {t}, which is never offered"))


class AgentDefinitionTests(unittest.TestCase):
    def test_qwen_forks_as_agents_md_and_the_skill_say(self):
        self.assertIn("A `qwen` child starts with a copy of this conversation", flat(AGENTS_MD))
        self.assertIn("(`defaultContext: fork`)", PROMPT_FLAT["skills/elm-delegation/SKILL.md"])
        self.assertEqual("fork", AGENT_DEFS["qwen"]["defaultContext"])

    def test_llama_starts_fresh_as_agents_md_and_the_skill_say(self):
        self.assertIn("a `llama` child starts empty", flat(AGENTS_MD))
        self.assertIn("a `llama` child starts with nothing (`fresh`)", PROMPT_FLAT["skills/elm-delegation/SKILL.md"])
        self.assertEqual("fresh", AGENT_DEFS["llama"]["defaultContext"])

    def test_child_models_are_the_configured_providers(self):
        self.assertEqual("elm/@QWEN_MODEL@", AGENT_DEFS["qwen"]["model"])
        self.assertEqual("elm-shim/@LLAMA_MODEL@", AGENT_DEFS["llama"]["model"])

    def test_install_md_quotes_the_model_scope(self):
        self.assertIn('`enforce: true, strict: true, allow: ["elm/*", "elm-shim/*", "inherit"]`', FLAT["INSTALL.md"])
        scope = SETTINGS["subagents"]["modelScope"]
        self.assertEqual((True, True, ["elm/*", "elm-shim/*", "inherit"]), (scope["enforce"], scope["strict"], scope["allow"]))

    def test_workflows_inherit_the_main_model(self):
        self.assertIn("With `inheritMainModel: true` in `agent/workflows/settings.json`", FLAT["INSTALL.md"])
        self.assertIn("`inheritMainModel` is on", PROMPT_FLAT["skills/elm-dynamic-workflows/SKILL.md"])
        self.assertIs(True, WORKFLOWS["inheritMainModel"])

    def test_workflow_keyword_trigger_is_off(self):
        self.assertIn("Its keyword trigger stays switched off here", PROMPT_FLAT["skills/elm-dynamic-workflows/SKILL.md"])
        self.assertIs(False, WORKFLOWS["keywordTriggerEnabled"])


@lru_cache(maxsize=None)
def subagent_builtins():
    agents = NPM / "pi-subagents/agents"
    return {p.stem for p in agents.glob("*.md")} if agents.is_dir() else None


def _override_exists(self, name):
    builtins = subagent_builtins()
    if builtins is None:
        self.skipTest("pi-subagents is not installed in this checkout")
    self.assertIn(name, builtins, f"settings.json overrides `{name}`, which pi-subagents no longer ships")


generate(AgentDefinitionTests, [(f"override_{slug(n)}_is_a_pi_subagents_agent", n)
                                for n in SETTINGS["subagents"]["agentOverrides"]], _override_exists)

# Slash commands the docs and prompts name, and who registers them.
COMMAND_HOME = {
    "elm-policy": "local", "ralph": "@tmustier/pi-ralph-wiggum",
    **{c: "@pify/btw" for c in ("btw", "btw:new", "btw:tangent", "btw:model", "btw:thinking")},
    **{c: "@quintinshaw/pi-dynamic-workflows" for c in ("ultracode", "effort", "deep-research", "adversarial-review",
                                                        "code-review", "multi-perspective", "codebase-audit", "workflows")},
}


class SlashCommandTests(unittest.TestCase):
    pass


def _command(self, doc, command):
    home = COMMAND_HOME[command]
    if home == "local":
        source = "\n".join(p.read_text() for p in TEMPLATES.glob("extensions/*.ts"))
    else:
        source = package_source(home)
        if source is None:
            self.skipTest(f"{home} is not installed in this checkout")
    self.assertIn(f'registerCommand("{command}"', source, f"{doc} names /{command}")


_COMMAND_DOCS = {}
for _doc, _text in {**DOCS, **PROMPTS}.items():
    for _cmd in COMMAND_HOME:
        if re.search(rf"(?<![\w/.-])/{re.escape(_cmd)}(?![\w:-])", _text):
            _COMMAND_DOCS.setdefault(_cmd, []).append(_doc)
generate(SlashCommandTests, [(f"command_{slug(c)}_is_registered", ", ".join(d), c) for c, d in _COMMAND_DOCS.items()],
         _command)


# --- the egress proxy's list ----------------------------------------------------------

HOSTS = CONFIG["proxyAllow"]["hosts"]
EGRESS_MD = PROMPT_FLAT["reference/egress.md"]
REGISTRY_NAMES = {"docker.io": "Docker Hub", "production.cloudflare.docker.com": "Docker Hub", "ghcr.io": "GHCR",
                  "pkg-containers.githubusercontent.com": "GHCR", "quay.io": "Quay"}
EGRESS_LISTED = re.findall(r"`([a-z0-9.-]+\.[a-z]+)`", between(EGRESS_MD, "On its list are", "see `proxyAllow`"))
LOCKDOWN_LISTED = (re.findall(r"`([a-z0-9.-]+\.[a-z]+)`", between(FLAT["LOCKDOWN.md"], "**PyPI is on the list**", "in `config/elm-pi.json`"))
                   + re.findall(r"`([a-z0-9.-]+\.[a-z]+)`", between(FLAT["LOCKDOWN.md"], "**conda-forge is on it too**", "for searching them")))
UPDATE_HOSTS = re.findall(r"`([a-z0-9.-]+\.[a-z]+)`", between(FLAT["LOCKDOWN.md"], "updates need", "The proxy is started"))


class ProxyHostTests(unittest.TestCase):
    def test_the_lists_were_found(self):
        self.assertEqual(5, len(EGRESS_LISTED))
        self.assertEqual(5, len(LOCKDOWN_LISTED))
        self.assertEqual(3, len(UPDATE_HOSTS))

    def test_open_mode_logs_open(self):
        self.assertIn("logs each new destination once as `OPEN`", FLAT["LOCKDOWN.md"])
        self.assertIn('self.log("OPEN"', EGRESS)

    def test_refusals_are_logged_as_rejected(self):
        self.assertIn("# REJECTED <host> not on the allowlist", EGRESS_MD)
        self.assertIn('self.log("REJECTED"', EGRESS)
        self.assertIn('"not on the allowlist"', EGRESS)

    def test_brew_runs_are_logged_unproxied(self):
        self.assertIn("writes it to `agent/egress.log` as `UNPROXIED`", FLAT["LOCKDOWN.md"])
        self.assertIn("UNPROXIED", read("scripts/brew"))

    def test_the_elm_host_comes_from_elm_base_url(self):
        self.assertIn("taken from `ELM_BASE_URL`", FLAT["LOCKDOWN.md"])
        self.assertRegex(LAUNCHER, r"ELM_HOST=.*ELM_BASE_URL")

    def test_the_proxy_is_on_loopback(self):
        self.assertIn("a small allowlisting proxy on loopback", FLAT["LOCKDOWN.md"])
        self.assertIn('export HTTPS_PROXY="http://127.0.0.1:$PROXY_PORT"', LAUNCHER)


def _host_in_reference(self, host):
    self.assertTrue(f"`{host}`" in EGRESS_MD or REGISTRY_NAMES.get(host, "\0") in EGRESS_MD,
                    f"proxyAllow has {host}; reference/egress.md does not tell the model")


generate(ProxyHostTests, [(f"allowed_{slug(h)}_is_in_the_egress_reference", h) for h in HOSTS], _host_in_reference)
generate(ProxyHostTests,
         [(f"egress_reference_host_{slug(h)}_is_allowed", h, HOSTS, "proxyAllow.hosts") for h in EGRESS_LISTED
          if h not in HOSTS]
         + [(f"lockdown_host_{slug(h)}_is_allowed", h, HOSTS, "proxyAllow.hosts") for h in LOCKDOWN_LISTED],
         _flag_in)
generate(ProxyHostTests,
         [(f"update_host_{slug(h)}_is_not_allowed", h) for h in UPDATE_HOSTS],
         lambda self, h: self.assertFalse([a for a in HOSTS if h == a or h.endswith("." + a)],
                                          f"{h} is quoted as refused but the proxy allows it"))
generate(ProxyHostTests,
         [(f"egress_reference_header_{slug(h)}_is_sent", h) for h in ("X-Elm-Pi-Egress", "X-Elm-Pi-Reason", "X-Elm-Pi-Remedy")],
         lambda self, h: (self.assertIn(f"`{h}`", EGRESS_MD), self.assertIn(f'b"{h}: ', EGRESS)))

# "Allows only the gateway": true once, stale since proxyAllow gained PyPI,
# conda-forge and the registries. These places used to say it; each may say it
# again only if proxyAllow.hosts is emptied.
GATEWAY_ONLY = [
    ("pi_help_remote", PI_USAGE, "instead of allowing only the ELM gateway"),
    ("lockdown_lifting_it", LOCKDOWN, "Layer 6 still allows only the gateway"),
    ("lockdown_web_tools", LOCKDOWN, "layer 6 still allows only the gateway"),
    ("append_system_web", PROMPTS["APPEND_SYSTEM.md"], "every host but the ELM gateway is refused"),
    ("delegation_skill_web", PROMPTS["skills/elm-delegation/SKILL.md"], "refuses every host but the ELM gateway"),
]


def _gateway_only(self, text, phrase):
    if phrase in flat(text):
        self.assertEqual([], HOSTS, f"says {phrase!r}, but proxyAllow lets {len(HOSTS)} more hosts through")


generate(ProxyHostTests, [(f"{n}_gateway_only_claim_holds", t, p) for n, t, p in GATEWAY_ONLY], _gateway_only)


# --- credentials and providers ----------------------------------------------------------

CREDENTIAL_LIST = CONFIG["providerCredentials"]


class CredentialTests(unittest.TestCase):
    def test_aws_bearer_token_is_the_only_aws_variable_scrubbed(self):
        self.assertIn("`AWS_*` (except `AWS_BEARER_TOKEN_BEDROCK`)", FLAT["LOCKDOWN.md"])
        self.assertEqual(["AWS_BEARER_TOKEN_BEDROCK"], [c for c in CREDENTIAL_LIST if c.startswith("AWS_")])

    def test_github_token_is_not_scrubbed_but_copilots_is(self):
        self.assertIn("`GITHUB_TOKEN` (`COPILOT_GITHUB_TOKEN` is)", FLAT["LOCKDOWN.md"])
        self.assertNotIn("GITHUB_TOKEN", CREDENTIAL_LIST)
        self.assertIn("COPILOT_GITHUB_TOKEN", CREDENTIAL_LIST)

    def test_bedrock_and_copilot_are_stripped_from_the_catalogue(self):
        self.assertIn("layer 3 already removes `amazon-bedrock` and `github-copilot`", FLAT["LOCKDOWN.md"])
        self.assertIn("amazon-bedrock", CONFIG["builtinProviders"])
        self.assertIn("github-copilot", CONFIG["builtinProviders"])

    def test_the_keys_install_md_verifies_with_are_scrubbed(self):
        self.assertIn("ANTHROPIC_API_KEY=x OPENAI_API_KEY=x ./pi --list-models", INSTALL)
        self.assertIn("ANTHROPIC_API_KEY", CREDENTIAL_LIST)
        self.assertIn("OPENAI_API_KEY", CREDENTIAL_LIST)

    def test_bootstraps_lockdown_check_provokes_with_fake_keys(self):
        self.assertIn("it sets fake Anthropic and OpenAI keys to provoke exactly that", FLAT["LOCKDOWN.md"])
        block = between(BOOTSTRAP, "# --- 7. verify the lockdown", "commercial providers are still visible")
        self.assertIn("ANTHROPIC_API_KEY=probe", block)
        self.assertIn("OPENAI_API_KEY=probe", block)

    def test_bootstraps_lockdown_check_names_the_three_providers(self):
        self.assertIn("if any `anthropic`, `openai` or `google` model is listed", FLAT["LOCKDOWN.md"])
        self.assertIn("grep -qE '^(anthropic|openai|google) '", BOOTSTRAP)
        self.assertIn('die "commercial providers are still visible', BOOTSTRAP)

    def test_allowed_providers_reach_every_layer_through_runtime_env(self):
        self.assertIn("the argument guard, `elm-only.ts` and `workflow-model-scope.ts` all take their allowlist from it",
                      FLAT["LOCKDOWN.md"])
        self.assertIn('"ELM_ALLOWED_PROVIDERS": " ".join(config["allowedProviders"])', read("scripts/elm_config.py"))
        for path in ("templates/extensions/elm-only.ts", "templates/extensions/workflow-model-scope.ts", "lib/policy.sh"):
            self.assertIn("ELM_ALLOWED_PROVIDERS", read(path), path)

    def test_builtin_providers_feed_the_catalogue_strip(self):
        self.assertIn("`builtinProviders` in `config/elm-pi.json` feeds the pre-session catalogue pass", FLAT["LOCKDOWN.md"])
        self.assertIn('"ELM_BUILTIN_PROVIDERS": " ".join(config["builtinProviders"])', read("scripts/elm_config.py"))
        self.assertIn("process.env.ELM_BUILTIN_PROVIDERS", read("templates/extensions/elm-only.ts"))

    def test_the_escape_hatch_provider_list_starts_with_the_allowed_ones(self):
        hatch = re.search(r'PI_ELM_ALLOWED_PROVIDERS="([^"]+)"', LOCKDOWN).group(1).split(",")
        self.assertEqual(CONFIG["allowedProviders"], hatch[:len(CONFIG["allowedProviders"])])

    def test_the_escape_hatch_needs_unlock(self):
        self.assertIn("the launcher unsets it unless `PI_ELM_UNLOCK=1` is also present", FLAT["LOCKDOWN.md"])
        block = between(LAUNCHER, 'if [ "$UNLOCK" != "1" ]; then', "  # 2. argument guard")
        self.assertIn("unset PI_ELM_ALLOWED_PROVIDERS", block)

    def test_help_runs_with_the_same_scrub(self):
        self.assertIn("`pi --help` runs with the same scrub", FLAT["LOCKDOWN.md"])
        block = between(LAUNCHER, 'if [ "$WANTS_HELP" = "1" ]; then', 'exec "$HERE/pi.orig" --help')
        self.assertIn('for credential_name in ${ELM_PROVIDER_CREDENTIALS:-}; do', block)

    def test_settings_scope_key_the_lifting_steps_name_exists(self):
        self.assertIn('add `"<provider>/*"` to `subagents.modelScope.allow` in `templates/settings.json`', FLAT["LOCKDOWN.md"])
        self.assertIsInstance(SETTINGS["subagents"]["modelScope"]["allow"], list)

    def test_default_project_trust_is_never(self):
        self.assertIn("(`defaultProjectTrust: never`)", FLAT["LOCKDOWN.md"])
        self.assertEqual("never", SETTINGS["defaultProjectTrust"])

    def test_subagent_sharing_is_explicitly_off(self):
        self.assertIn('that file now says `"share": false` explicitly', FLAT["LOCKDOWN.md"])
        self.assertIs(False, SUBAGENT["share"])

    def test_auth_json_is_locked_to_mode_400(self):
        self.assertIn("`bootstrap.sh` sets mode 400 on it", FLAT["LOCKDOWN.md"])
        self.assertIn("Undo with: chmod 600 agent/auth.json", BOOTSTRAP)
        self.assertIn("chmod 400", read("lib/state.sh"))

    def test_patch_pi_throws_in_the_three_upload_functions(self):
        self.assertIn("the three upload functions (`uploadBugReport`, `tryShareViaRadius`, `shareViaGist`) throw",
                      FLAT["LOCKDOWN.md"])
        patch = read("patch-pi.py")
        for name in ("uploadBugReport", "tryShareViaRadius", "shareViaGist"):
            self.assertIn(name, patch)

    def test_thinking_is_off_by_default(self):
        self.assertIn("**Thinking is off.**", FLAT["README.md"])
        self.assertEqual("off", SETTINGS["defaultThinkingLevel"])
        self.assertTrue(SETTINGS["subagents"]["disableThinking"])

    def test_removed_cache_settings_are_gone_from_models_json(self):
        # INSTALL.md: tried and removed, "Neither produced a measurable gain"
        self.assertIn("Two settings were tried and removed: `compat.sendSessionAffinityHeaders` / `sessionAffinityFormat`",
                      FLAT["INSTALL.md"])
        text = json.dumps(MODELS) + ELM_SHIM_TS
        self.assertNotIn("sendSessionAffinityHeaders", text)
        self.assertNotIn("sessionAffinityFormat", text)

    def test_web_search_routes_duckduckgo_then_exa(self):
        self.assertIn("`pi-web-access` (DuckDuckGo, then Exa)", FLAT["README.md"])
        self.assertIn("DuckDuckGo, then Exa", FLAT["docs/index.html"])
        self.assertIn("| `agent/web-search.json` | DuckDuckGo then Exa; `unpdf` for PDFs |", INSTALL)
        self.assertEqual(["duckduckgo", "exa"], WEB_SEARCH["searchRouting"]["providers"])
        self.assertEqual("unpdf", WEB_SEARCH["pdf"]["provider"])

    def test_lockdown_web_tool_names_are_the_config_list(self):
        named = re.findall(r"`(\w+)`", between(FLAT["LOCKDOWN.md"], "registers five tools", "which switches the others on"))
        self.assertEqual(CONFIG["webTools"], named)


# --- folders that are never a project ---------------------------------------------------

FOLDERS = CONFIG["untrustedFolders"]
FOLDER_CLAIMS = [  # (folder, kind) as LOCKDOWN.md "Folders that are never a project" describes it
    ("~", "exact"), ("/", "exact"), ("~/Documents", "exact"), ("~/Downloads", "exact"), ("~/Library", "exact"),
    ("~/Library/CloudStorage", "exact"),                          # "the OneDrive ... roots"
    ("~/Library/Mobile Documents/com~apple~CloudDocs", "exact"),  # "and iCloud roots"
    ("~/.ssh", "tree"), ("~/.gnupg", "tree"), ("~/.aws", "tree"), ("~/.pi", "tree"),
    ("~/Library/Keychains", "tree"), ("/etc", "tree"), ("/usr", "tree"),
]
FOLDER_PARA = between(FLAT["LOCKDOWN.md"], "**The launcher refuses to start a session**", "`PI_FORCE=1` starts there anyway")


class FolderTests(unittest.TestCase):
    pass


def _folder(self, folder, kind):
    if folder.startswith("~/Library/") and folder.count("/") > 1 and "Keychains" not in folder:
        self.assertIn("OneDrive and iCloud roots", FOLDER_PARA)
    elif folder not in ("~", "/"):
        self.assertIn(f"`{folder}`", FOLDER_PARA)
    self.assertIn(folder, FOLDERS[kind], f"LOCKDOWN.md describes {folder} as {kind}")


generate(FolderTests, [(f"{ {'~': 'home', '/': 'root'}.get(f) or slug(f)}_is_{k}", f, k) for f, k in FOLDER_CLAIMS],
         _folder)


# --- the permission gate's rules, as LOCKDOWN.md and the skills describe them ------------

def decide(rules, subject):
    """pi-permission-system's decision: wildcard patterns, last match wins."""
    decision = None
    for pattern, rule in rules.items():
        regex = ".*".join(re.escape(part).replace("\\ ", " ").replace("\\?", ".") for part in pattern.split("*"))
        if regex.endswith(" .*"):
            regex = regex[:-3] + "( .*)?"
        if re.fullmatch(regex, subject, re.S):
            decision = rule if isinstance(rule, str) else rule["action"]
    return decision


BASH_CLAIMS = [  # (phrase in LOCKDOWN.md, a command it covers, the decision it implies)
    ("`ssh`", "ssh login.example.org", "deny"),
    ("`scp`", "scp results.csv host:/tmp/", "deny"),
    ("`sftp`", "sftp host", "deny"),
    ("`rsync` to a remote (`host:path`", "rsync -a out/ host:backup/", "deny"),
    ("`rsync://`", "rsync -a rsync://mirror.example.org/pub/ out/", "deny"),
    ("a local `rsync` is fine", "rsync -a src/ dst/", "allow"),
    ("`sshfs`", "sshfs host:/data mnt", "deny"),
    ("`ssh-copy-id`", "ssh-copy-id host", "deny"),
    ("`autossh`", "autossh -M 0 host", "deny"),
    ("`mosh`", "mosh host", "deny"),
    ("`nc`/`ncat`/`netcat`", "nc example.org 80", "deny"),
    ("`nc`/`ncat`/`netcat`", "ncat example.org 80", "deny"),
    ("`nc`/`ncat`/`netcat`", "netcat example.org 80", "deny"),
    ("`socat`", "socat - TCP:example.org:80", "deny"),
    ("`telnet`", "telnet example.org 80", "deny"),
    ("`ftp`", "ftp example.org", "deny"),
    ("`lftp`", "lftp example.org", "deny"),
    ("`rclone`", "rclone copy out remote:bucket", "deny"),
    ("`ngrok`", "ngrok http 8000", "deny"),
    ("`cloudflared`", "cloudflared tunnel run", "deny"),
    ("`tailscale serve`/`funnel`/`file`", "tailscale serve 8000", "deny"),
    ("`tailscale serve`/`funnel`/`file`", "tailscale funnel 8000", "deny"),
    ("`tailscale serve`/`funnel`/`file`", "tailscale file cp notes.txt laptop:", "deny"),
    ("`parallel -S`", "parallel -S host echo ::: a", "deny"),
    ("every `run`/`create` must carry `--network=none`", "docker run --rm alpine true", "deny"),
    ("every `run`/`create` must carry `--network=none`", "docker run --rm --network=none alpine true", "allow"),
    ("every `run`/`create` must carry `--network=none`", "docker create alpine", "deny"),
    ("every `run`/`create` must carry `--network=none`", "podman run --rm alpine true", "deny"),
    ("every `run`/`create` must carry `--network=none`", "podman run --rm --network=none alpine true", "allow"),
    ("The agent may pull images", "docker pull alpine", "allow"),
    ("`push`, `login` and a remote engine", "docker push me/image", "deny"),
    ("`push`, `login` and a remote engine", "podman push me/image", "deny"),
    ("`push`, `login` and a remote engine", "docker login ghcr.io", "deny"),
    ("`push`, `login` and a remote engine", "podman login quay.io", "deny"),
    ("(`-H`, `--context`,", "docker -H tcp://build.example.org:2375 ps", "deny"),
    ("(`-H`, `--context`,", "docker --context remote ps", "deny"),
    ("`podman --remote`/`--connection`", "podman --remote ps", "deny"),
    ("`podman --remote`/`--connection`", "podman --connection other ps", "deny"),
    ("`build` and `compose` ask", "docker build .", "ask"),
    ("`build` and `compose` ask", "docker compose up", "ask"),
    ("`build` and `compose` ask", "podman build .", "ask"),
    ("a `-c`/`--channel` option", "pixi global install -c bioconda samtools", "ask"),
    ("a `-c`/`--channel` option", "pixi exec --channel bioconda samtools", "ask"),
    ("a `channel::package` spec", "pixi global install bioconda::samtools", "ask"),
    ("`pixi workspace channel add`", "pixi workspace channel add bioconda", "ask"),
    ("`pixi upload`/`auth` are denied", "pixi upload pkg.conda", "deny"),
    ("`pixi upload`/`auth` are denied", "pixi auth login prefix.dev", "deny"),
    ("`brew install`, `upgrade`, `fetch` and the rest ask", "brew install gdal", "ask"),
    ("`brew install`, `upgrade`, `fetch` and the rest ask", "brew upgrade gdal", "ask"),
    ("`brew install`, `upgrade`, `fetch` and the rest ask", "brew fetch gdal", "ask"),
    ("`brew install`, `upgrade`, `fetch` and the rest ask", "brew uninstall gdal", "ask"),
    ("casks, third-party taps and formula files are denied", "brew install --cask firefox", "deny"),
    ("casks, third-party taps and formula files are denied", "brew tap someone/tools", "deny"),
    ("casks, third-party taps and formula files are denied", "brew install someone/tools/thing", "deny"),
    ("casks, third-party taps and formula files are denied", "brew install ./thing.rb", "deny"),
    ("calling Homebrew by its full path, past the wrapper, is denied", "/opt/homebrew/bin/brew install gdal", "deny"),
    ("Read-only `brew info`/`list`/`deps` stay behind the proxy", "brew info gdal", "allow"),
    ("Read-only `brew info`/`list`/`deps` stay behind the proxy", "brew list", "allow"),
    ("Read-only `brew info`/`list`/`deps` stay behind the proxy", "brew deps gdal", "allow"),
    ("through apt, dnf, yum,", "apt install curl", "deny"),
    ("through apt, dnf, yum,", "apt-get install -y curl", "deny"),
    ("through apt, dnf, yum,", "apt remove curl", "deny"),
    ("through apt, dnf, yum,", "dnf install curl", "deny"),
    ("through apt, dnf, yum,", "dnf remove curl", "deny"),
    ("through apt, dnf, yum,", "yum install curl", "deny"),
    ("zypper, pacman, apk, snap, flatpak, MacPorts,", "zypper install curl", "deny"),
    ("zypper, pacman, apk, snap, flatpak, MacPorts,", "pacman -S curl", "deny"),
    ("zypper, pacman, apk, snap, flatpak, MacPorts,", "apk add curl", "deny"),
    ("zypper, pacman, apk, snap, flatpak, MacPorts,", "snap install curl", "deny"),
    ("zypper, pacman, apk, snap, flatpak, MacPorts,", "flatpak install org.example.App", "deny"),
    ("zypper, pacman, apk, snap, flatpak, MacPorts,", "port install curl", "deny"),
    ("`dpkg` and `rpm` are denied outright", "dpkg -i tool.deb", "deny"),
    ("`dpkg` and `rpm` are denied outright", "rpm -i tool.rpm", "deny"),
    ("(`zypper rm`, `pacman --sync`, `rpm --install`)", "zypper rm curl", "deny"),
    ("(`zypper rm`, `pacman --sync`, `rpm --install`)", "pacman --sync curl", "deny"),
    ("(`zypper rm`, `pacman --sync`, `rpm --install`)", "rpm --install tool.rpm", "deny"),
    ("`git push` asks", "git push origin main", "ask"),
    ("with global options too (`git -C dir push`)", "git -C dir push origin main", "ask"),
    ("behind `sudo`, `env`, `xargs`, `command`, `exec`, `nohup`, `timeout` and the like (which the gate would otherwise ask about",
     "sudo make install", "ask"),
]
PATH_CLAIMS = [  # (phrase in LOCKDOWN.md's credential-store list, a path in it, the decision)
    ("`~/.ssh`", "~/.ssh/id_ed25519", "deny"),
    ("`~/.aws`", "~/.aws/credentials", "deny"),
    ("`~/.gnupg`", "~/.gnupg/private-keys-v1.d/key", "deny"),
    ("`~/.azure`", "~/.azure/accessTokens.json", "deny"),
    ("`~/.config/gh`", "~/.config/gh/hosts.yml", "deny"),
    ("and `gcloud`", "~/.config/gcloud/credentials.db", "deny"),
    ("`~/.kube/config`", "~/.kube/config", "deny"),
    ("`~/.docker/config.json`", "~/.docker/config.json", "deny"),
    ("`~/.netrc`", "~/.netrc", "deny"),
    ("`~/.git-credentials`", "~/.git-credentials", "deny"),
    ("`~/.npmrc`", "~/.npmrc", "deny"),
    ("`~/.pypirc`", "~/.pypirc", "deny"),
    ("the macOS keychains", "~/Library/Keychains/login.keychain-db", "deny"),
    ("browser profiles", "~/Library/Application Support/Google/Chrome/Default/Cookies", "deny"),
    ("browser profiles", "~/Library/Application Support/Firefox/Profiles/a.default/key4.db", "deny"),
    ("browser profiles", "~/.mozilla/firefox/a.default/key4.db", "deny"),
    ("browser profiles", "~/.config/google-chrome/Default/Login Data", "deny"),
    ("browser profiles", "~/Library/Safari/History.db", "deny"),
    ("browser profiles", "~/Library/Cookies/Cookies.binarycookies", "deny"),
    ("Mail and Messages", "~/Library/Mail/V10/MailData/Envelope Index", "deny"),
    ("Mail and Messages", "~/Library/Messages/chat.db", "deny"),
    ("other agents' state (`~/.pi`,", "~/.pi/agent/auth.json", "deny"),
    ("`~/.claude`)", "~/.claude/settings.json", "deny"),
    ("`~/.claude`)", "~/.claude.json", "deny"),
    ("`.env` and key files anywhere", "project/.env", "deny"),
    ("`.env` and key files anywhere", "project/.env.local", "deny"),
    ("`.env` and key files anywhere", "certs/server.pem", "deny"),
    ("`.env` and key files anywhere", "backup/id_rsa", "deny"),
]


class PermissionClaimTests(unittest.TestCase):
    """What LOCKDOWN.md says the gate denies or asks about, decided by its rules."""


def _bash_claim(self, phrase, cases):
    self.assertIn(phrase, FLAT["LOCKDOWN.md"], "LOCKDOWN.md no longer says this")
    self.assertEqual(cases, [(c, decide(PERMISSION["bash"], c)) for c, _ in cases], phrase)


def _path_claim(self, phrase, cases):
    self.assertIn(phrase, between(FLAT["LOCKDOWN.md"], "the gate's `path` rules deny", "### 6. Egress proxy"))
    self.assertEqual(cases, [(p, decide(PERMISSION["path"], p)) for p, _ in cases], phrase)


def by_phrase(claims):
    """One case per phrase: every command or path the docs mean by it."""
    grouped = {}
    for phrase, subject, expected in claims:
        grouped.setdefault(phrase, []).append((subject, expected))
    return grouped.items()


generate(PermissionClaimTests, [(f"lockdown_bash_{slug(p)[:70]}", p, c) for p, c in by_phrase(BASH_CLAIMS)], _bash_claim)
generate(PermissionClaimTests, [(f"lockdown_path_{slug(p)}", p, c) for p, c in by_phrase(PATH_CLAIMS)], _path_claim)

# Skill and doc examples the model copies run as written: a `docker run`/`podman
# run` example that the gate denies would teach a refused command.
RUN_EXAMPLES = sorted({line.strip().rstrip("\\").strip() for text in PROMPTS.values() for line in text.splitlines()
                       if re.match(r"\s*(docker|podman) run ", line)})
generate(PermissionClaimTests, [(f"prompt_example_{slug(c)[:60]}_is_allowed", c) for c in RUN_EXAMPLES],
         lambda self, c: self.assertEqual("allow", decide(PERMISSION["bash"], c + " cmd")))


def _family(pattern):
    word = pattern.split()[0]
    if word == "*/brew":
        return "brew"
    return {"apt-get": "apt", "aptitude": "apt", "port": "MacPorts"}.get(word, word)


DENY_FAMILIES = sorted({_family(p) for p, r in PERMISSION["bash"].items() if isinstance(r, dict) and r["action"] == "deny"})
generate(PermissionClaimTests, [(f"denied_family_{slug(f)}_is_in_lockdown", f) for f in DENY_FAMILIES],
         lambda self, f: self.assertTrue(mentions(FLAT["LOCKDOWN.md"], f), f"the gate denies {f}; LOCKDOWN.md never says so"))

# Each path the gate denies, by the words LOCKDOWN.md (or INSTALL.md, for the
# write protections) uses for it.
PATH_PHRASES = {
    "*.env": "`.env`", "*.env.*": "`.env`", "*/.git/*": "`.git/`", ".git/*": "`.git/`",
    "~/.ssh/*": "`~/.ssh`", "~/.aws/*": "`~/.aws`", "~/.config/gh/*": "`~/.config/gh`", "*.pem": "key files",
    "*id_rsa*": "key files", "~/.gnupg/*": "`~/.gnupg`", "~/.azure/*": "`~/.azure`", "~/.kube/config": "`~/.kube/config`",
    "~/.docker/config.json": "`~/.docker/config.json`", "~/.config/gcloud/*": "`gcloud`", "~/.netrc": "`~/.netrc`",
    "~/.git-credentials": "`~/.git-credentials`", "~/.npmrc": "`~/.npmrc`", "~/.pypirc": "`~/.pypirc`",
    "~/.password-store/*": "`~/.password-store`", "~/.pi/*": "`~/.pi`", "~/.claude/*": "`~/.claude`",
    "~/.claude.json": "`~/.claude`", "~/Library/Keychains/*": "keychains", "~/Library/Cookies/*": "browser profiles",
    "~/Library/Safari/*": "browser profiles", "~/Library/Mail/*": "Mail", "~/Library/Messages/*": "Messages",
    "~/Library/Application Support/Google/Chrome/*": "browser profiles",
    "~/Library/Application Support/Firefox/*": "browser profiles", "~/.mozilla/*": "browser profiles",
    "~/.config/google-chrome/*": "browser profiles", "~/.config/chromium/*": "browser profiles",
    "~/.local/share/keyrings/*": "keyrings",
}
DENIED_PATHS = [p for p, r in PERMISSION["path"].items() if r == "deny"]


def _path_rule_documented(self, phrase, patterns):
    self.assertIn(phrase, FLAT["LOCKDOWN.md"] + FLAT["INSTALL.md"], f"denied by {patterns}")


def pslug(pattern):
    return slug(pattern.replace("*", " star ").replace(".", " dot "))


generate(PermissionClaimTests,
         [(f"denied_paths_called_{slug(ph)}_are_documented", ph, [p for p in DENIED_PATHS if PATH_PHRASES.get(p) == ph])
          for ph in dict.fromkeys(PATH_PHRASES[p] for p in DENIED_PATHS if p in PATH_PHRASES)],
         _path_rule_documented)
# A rule added without a word for it here fails by name.
generate(PermissionClaimTests, [(f"denied_path_{pslug(p)}_has_a_documented_name", p) for p in DENIED_PATHS
                                if p not in PATH_PHRASES],
         lambda self, p: self.fail(f"new path rule {p}: say in LOCKDOWN.md what it protects, and add it to PATH_PHRASES"))

# A denial's reason sends the model to a document or a skill: each one named has
# to exist, and a doc it is sent to has to say why.
REASONS = sorted({r["reason"] for section in ("bash", "path") for r in PERMISSION[section].values() if isinstance(r, dict)})
REASON_DOCS = sorted({d for r in REASONS for d in re.findall(r"\b([A-Z]+\.md)\b", r)})
REASON_SKILLS = sorted({k for r in REASONS for k in re.findall(r"the ([a-z-]+) skill", r)})
generate(PermissionClaimTests,
         [(f"denials_point_at_{slug(d)}_which_explains_them", d) for d in REASON_DOCS],
         lambda self, d: (self.assertTrue((ROOT / d).is_file(), d), self.assertIn("denied", read(d))))
generate(PermissionClaimTests,
         [(f"denials_point_at_the_{slug(k)}_skill_which_exists", k) for k in REASON_SKILLS],
         lambda self, k: self.assertIn(k, SKILLS))


# --- generated files and reference topics -------------------------------------------------

GENERATED_ROWS = {  # INSTALL.md's generated-file table row -> its source under templates/
    "agent/models.json": "templates/models.json", "agent/settings.json": "templates/settings.json",
    "agent/AGENTS.md": "templates/AGENTS.md", "agent/reference/": "templates/reference",
    "agent/shell/colour.sh": "templates/shell/colour.sh",
    "agent/extensions/subagent/config.json": "templates/extensions/subagent/config.json",
    "agent/web-search.json": "templates/web-search.json",
}


class GeneratedFileTests(unittest.TestCase):
    def test_install_options_and_installed_versions_are_written_by_bootstrap(self):
        for name in ("agent/install-options", "agent/installed-versions.json"):
            self.assertIn(f"| `{name}` |", INSTALL)
            self.assertIn(name.split("/", 1)[1], BOOTSTRAP)

    def test_agent_bin_pi_is_a_link_to_the_launcher(self):
        self.assertIn("| `agent/bin/pi` | symlink to the launcher", INSTALL)
        self.assertIn('ln -sfn "$HERE/pi" agent/bin/pi', BOOTSTRAP)

    def test_lock_stamp_file_is_the_one_bootstrap_writes(self):
        self.assertIn("(`node_modules/.elm-pi-lock.sha256`", FLAT["CONTRIBUTING.md"])
        self.assertIn(".elm-pi-lock.sha256", BOOTSTRAP)

    def test_runtime_installs_ignore_scripts(self):
        self.assertIn("Runtime installs use `npm install --ignore-scripts`", FLAT["CONTRIBUTING.md"])
        self.assertIn("`npm install --omit=dev --ignore-scripts`", FLAT["INSTALL.md"])
        self.assertIn("--omit=dev --ignore-scripts", BOOTSTRAP)
        self.assertNotRegex(BOOTSTRAP, r"elm_npm (?:install|ci)(?![^\n]*--ignore-scripts)")

    def test_elm_config_writes_model_ids(self):
        self.assertIn("`configure.sh` records a gateway-resolved Qwen id in `agent/model-ids.json`", FLAT["CONTRIBUTING.md"])
        self.assertIn('"agent/model-ids.json"', read("scripts/elm_config.py"))


def _generated_row(self, row, source):
    self.assertIn(f"| `{row}` |", INSTALL)
    self.assertTrue((ROOT / source).exists(), source)
    # bootstrap.sh installs it from there
    self.assertIn(source, BOOTSTRAP)
    self.assertIn(row.rstrip("/"), BOOTSTRAP)


generate(GeneratedFileTests, [(f"generated_{slug(r)}_has_its_template", r, s) for r, s in GENERATED_ROWS.items()],
         _generated_row)

REFERENCE_TOPICS = {"finished-work.md": "finished work", "git-and-dot-pi.md": "`.pi` and git",
                    "project-memory.md": "project memory", "editing.md": "anchor editing", "egress.md": "the egress proxy",
                    "reporting.md": "reporting", "asking.md": "asking", "fits-and-figures.md": "fits and figures",
                    "elm.md": "the ELM service"}
REFERENCE_LISTS = {
    "generated_table": between(FLAT["INSTALL.md"], "| `agent/reference/` |", "| `agent/extensions/elm-only.ts`"),
    "what_every_request_carries": between(FLAT["INSTALL.md"], "point to `agent/reference/`", "for the rest"),
}
generate(GeneratedFileTests,
         [(f"reference_{slug(f)}_is_listed_in_{where}", f, where) for where in REFERENCE_LISTS
          for f in sorted(p.name for p in TEMPLATES.glob("reference/*.md"))],
         # "finished work" is "finished-work checklist" in the second list
         lambda self, f, where: self.assertIn(REFERENCE_TOPICS[f], REFERENCE_LISTS[where].replace("-", " "),
                                              f"INSTALL.md {where}: {f}"))


if __name__ == "__main__":
    unittest.main()
