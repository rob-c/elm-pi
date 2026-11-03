"""Three implementations of the permission-rule matcher, held to one answer.

The same wildcard rules (`*` any text, `?` one character, a trailing ` *` that
may also match nothing, every other character literal, the last matching rule
wins) are applied by three pieces of code:

- the gate: the installed @gotgenes/pi-permission-system, loaded with jiti as
  pi loads it - compileWildcardPattern for one pattern, PermissionManager for a
  rule set read from a config file, resolveBashCommandCheck over tree-sitter's
  parse for a whole bash program, and the path resolver for file tools;
- the Python copy: bash_rule in tests/test_agent_environment.py, which other
  tests use to decide container commands without node;
- command-guard.ts's own wildcard() and last-match-wins, which deniedSpelling
  uses to decide each spelling "as the gate would".

Every case is generated: the real templates/extensions/pi-permission-system/
config.json rules, and synthetic rule sets with regex characters
([ ] ( ) + . $ ^ | { } \\), unicode, empty patterns, overlapping, shadowed,
duplicated and integer-like keys. Each is also checked against a fourth matcher
written here from the documented rules (a character-by-character glob, no
regex), so agreement is not three copies of one mistake. One node process
answers every case.

How each implementation is asked:

- the guard through its exported deniedSpelling, given the rules as its own
  bashRulesOf reads them from the config file: called with every rule's
  action set to deny (order kept), it returns the pattern its own
  last-match-wins picked; called with the real actions, the denial it adds.
  Its private wildcard() is exported from a temporary copy of the file,
  otherwise unchanged;
- the Python copy as written, with the rules it reads swapped for the case's
  and each rule's action set to its own pattern, so the "decision" bash_rule
  returns names the rule that won.

Differences by design, asserted as differences:

- chains: the gate splits a program into commands (tree-sitter) and the first
  of the most restrictive decides; the Python copy matches the whole string;
  the guard reads each command as one spelling, words re-joined by single
  spaces, so `x  y` (two spaces, or a tab) is matched as `x y`, and an ask the
  re-spelling hides is refused with the rule that asks.
- trimming: the gate matches a command with surrounding whitespace removed
  (a blank command as typed); the Python copy is given the trimmed text.
- home: the gate expands a leading `~`, `$HOME` or `${HOME}` in every pattern,
  bash ones included, and also matches a command starting with one by its
  expanded spelling; the guard and the Python copy read `~` as a character.
- validation: the gate rejects a config with an empty pattern or an object
  rule that is not a deny, and fails closed (ask, no rule); the others match
  such rules as written. With no matching rule the gate asks; the others
  report no rule.
- integer-like keys: the gate reads rules into a JS object, which lists an
  integer-like pattern ("7") before every other, so it can lose to an earlier
  catch-all; the guard and the Python copy keep the file's order.
  scripts/check_config.py refuses such a key in the shipped config.
- `?` and astral characters: the gate's `?` is one UTF-16 unit (a regex
  without the u flag), the guard's one character, as documented.
  scripts/check_config.py refuses every `?` where the two could differ, and a
  pattern it accepts matches alike either way (asserted here).
- paths: the gate matches a path by its absolute form, its project-relative
  form, the form typed and the symlink-resolved form. The Python copy has no
  path logic, so it is given those forms as Python's os.path computes them
  (asserted equal to the gate's), with `~` in the rules expanded, and the last
  rule matching any form wins, as in the gate's evaluateAnyValue.

Cases marked BUG are real disagreements, kept as expected failures (none is,
now). HOME is a temporary folder. The tests skip on a checkout that has not been bootstrapped.
"""

import functools
import importlib.util
import sys
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/extensions/pi-permission-system/config.json"
GUARD = ROOT / "templates/extensions/command-guard.ts"
NPM = ROOT / "agent/npm/node_modules"
PACKAGE = NPM / "@gotgenes/pi-permission-system"
JITI = NPM / "jiti/lib/jiti.mjs"
REAL = json.loads(TEMPLATE.read_text())["permission"]


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


# --- the Python copy, run as written ----------------------------------------

def _load_python_copy():
    spec = importlib.util.spec_from_file_location("_agent_environment_copy", ROOT / "tests/test_agent_environment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENVIRONMENT = _load_python_copy()
sys.path.insert(0, str(ROOT / "scripts"))
import check_config  # noqa: E402


class _RulesFile:
    """Stands in for ROOT in the Python copy: every path under it reads as the given config."""

    def __init__(self, text):
        self.text = text

    def __truediv__(self, _):
        return self

    def read_text(self):
        return self.text


def action_of(rule):
    return rule if isinstance(rule, str) else rule.get("action")


def python_winner(rules, command):
    """The pattern bash_rule picks for `command` under `rules` (a dict, file order), or None."""
    tagged = {pattern: {"action": pattern} for pattern in rules}
    saved = ENVIRONMENT.ROOT
    ENVIRONMENT.ROOT = _RulesFile(json.dumps({"permission": {"bash": tagged}}))
    try:
        return ENVIRONMENT.bash_rule(command)
    finally:
        ENVIRONMENT.ROOT = saved


def python_decide(rules, command):
    pattern = python_winner(rules, command)
    return None if pattern is None else [action_of(rules[pattern]), pattern]


# --- the documented rules, without regex -------------------------------------

def glob(pattern, value):
    """`*` any run of characters, `?` exactly one character, anything else itself."""
    reach = [True] + [False] * len(value)        # reach[j]: the pattern so far matches value[:j]
    for c in pattern:
        if c == "*":
            for j in range(1, len(value) + 1):
                reach[j] = reach[j] or reach[j - 1]
        else:
            reach = [False] + [reach[j] and (c == "?" or c == value[j]) for j in range(len(value))]
    return reach[-1]


def spec_match(pattern, value):
    # A trailing " *" may also match nothing: `git *` covers a bare `git`.
    return glob(pattern, value) or (pattern.endswith(" *") and glob(pattern[:-2], value))


def units(text):
    """text as UTF-16 code units, one str character each: what the gate's regex (no u flag) counts."""
    data = text.encode("utf-16-le", "surrogatepass")
    return "".join(chr(int.from_bytes(data[i:i + 2], "little")) for i in range(0, len(data), 2))


def gate_match(pattern, value):
    """The documented rules over UTF-16 units, as the gate applies them."""
    return spec_match(units(pattern), units(value))


def spec_decide(rules, command):
    winner = None
    for pattern, rule in rules.items():
        if spec_match(pattern, command):
            winner = [action_of(rule), pattern]
    return winner


def spec_any(rules, values):
    """evaluateAnyValue: the last rule that matches any of the values."""
    winner = None
    for pattern, rule in rules.items():
        if any(spec_match(pattern, value) for value in values):
            winner = [action_of(rule), pattern]
    return winner


def js_order(rules):
    """A JS object's key order: canonical array indices first, ascending, then the rest as written."""
    index = [k for k in rules if re.fullmatch(r"0|[1-9][0-9]*", k) and int(k) < 2 ** 32 - 1]
    return {**{k: rules[k] for k in sorted(index, key=int)}, **{k: v for k, v in rules.items() if k not in index}}


def expand_home(text, home):
    """expandHomePath: a leading ~, $HOME or ${HOME}, alone or before a slash."""
    for prefix in ("~", "$HOME", "${HOME}"):
        rest = text[len(prefix):]
        if text.startswith(prefix) and (rest == "" or rest.startswith("/")):
            return home if rest == "" else os.path.join(home, rest[1:])
    return text


RESTRICTIVE = {"allow": 0, "ask": 1, "deny": 2}


def first_most_restrictive(decisions):
    worst = decisions[0]
    for d in decisions:
        if RESTRICTIVE[d[0]] > RESTRICTIVE[worst[0]]:
            worst = d
    return worst


# --- the cases --------------------------------------------------------------

# One-pattern cases: the real config's shapes, and every character a regex reads as syntax.
SYNTHETIC_PATTERNS = [
    "*", "", " *", "?", "??", "?*", "*?", "* *", "*  *", "a **", "a *?", "a? *", "* x",
    "git *", "git push *", "git push*", "git -* push *", "pi setup*", "rsync *:*", "brew tap ?*",
    "*/brew *", "*.env", "*.env.*", "a*b*c", "a.b", "a+b", "c++ *", "x [y] *", "[abc]", "f(x) *",
    "(a|b)", "p|q *", "^start *", "end$", "$PATH *", "{a,b} *", "a{2}", "\\d *", "a\\?", "a\\ *",
    "back\\slash", "-- *", "é *", "naïve*", "日本 *", "ß?", "tab\t*", "new\nline *", "Make *",
    ".*", "a.*b", "a?c?e", "*--network=none *", "x?y *", "😀 *", "*?*?",
]

STAR_FILLERS = ["", "x", " ", "a b", "*", "é"]
QUESTION_FILLERS = ["q", " ", "é", ""]


def unique(values):
    seen, out = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def instances(pattern):
    """Values a pattern should and should not match: its wildcards filled, then nudged."""
    out = [pattern.replace("*", s).replace("?", q) for s, q in itertools.product(STAR_FILLERS, QUESTION_FILLERS)]
    base = pattern.replace("*", "x").replace("?", "q")
    out += [base + "!", "!" + base, base[:-1], base.replace(" ", "  "), base.upper(), base.replace(" ", "\t")]
    if pattern.endswith(" *"):
        out += [pattern[:-2], pattern[:-2] + "x"]
    return unique(out)


def wildcard_cases():
    """Two values per pattern: one it matches and one it does not, where both exist."""
    cases = []
    for pattern in SYNTHETIC_PATTERNS:
        values = instances(pattern)
        yes = [v for v in values if spec_match(pattern, v)]
        no = [v for v in values if not spec_match(pattern, v)]
        for value in (yes[:1] + no[:1] + values)[:2] if yes and no else values[:2]:
            cases.append((pattern, value, ""))
    return cases


# `?` against a character of two UTF-16 units: the gate counts units, the others characters.
SPECIAL_WILD = [
    ("?", "😀", ""),
    ("a?", "a😀", ""),
    ("??", "😀", ""),
    ("a??b", "a😀b", ""),
    ("?", "é", ""),                       # one code unit: all agree
    ("*?", "😀😀", ""),                   # a star absorbs the difference
]
# Values for checking that a pattern check_config accepts matches alike in units and in characters.
ASTRAL_VALUES = ["", "😀", "😀😀", "a😀", "😀a", "a😀b", "é😀", "x 😀", "😀 *", "brew tap 😀", "brew tap 😀x"]

# Home prefixes in a pattern: (pattern, value). The gate expands the pattern; the others do not.
HOME_WILD = [
    ("~/x/*", "{home}/x/y"), ("~/x/*", "~/x/y"), ("$HOME/x", "{home}/x"), ("$HOME/x", "$HOME/x"),
    ("${HOME}/*", "{home}/a"), ("~", "{home}"), ("~", "~"), ("~user/*", "~user/a"), ("$HOMEDIR", "$HOMEDIR"),
]

# Rule sets as JSON text, so a duplicate key reaches each implementation the
# way its own JSON parser reads it.
RULE_SETS = {
    "overlap": '{"*": "allow", "git *": "ask", "git push *": "deny", "git push --dry-run *": "allow"}',
    "shadowed": '{"git push *": "deny", "git *": "ask", "*": "allow", "rm -rf *": "deny"}',
    "no_catch_all": '{"ls *": "allow", "rm *": "deny", "make*": "ask"}',
    "regex_chars": '{"*": "allow", "c++ *": "ask", "a.b *": "deny", "x[1] *": "deny", "f(x)*": "ask",'
                   ' "p|q": "deny", "^a$": "deny", "$PATH *": "ask", "a+": "deny", "{x}": "ask", "\\\\d": "deny"}',
    "unicode": '{"*": "allow", "\\u00e9 *": "deny", "na\\u00efve*": "ask", "\\u65e5\\u672c\\u8a9e *": "deny",'
               ' "\\u00df?": "ask", "caf\\u00e9": "deny"}',
    "questions": '{"*": "allow", "??": "deny", "? *": "ask", "a?c *": "deny", "???*": "ask"}',
    "trailing": '{"*": "allow", "tool *": "deny", "tool*": "ask", "tool  *": "allow", "tool -n *": "allow"}',
    "reasons": '{"*": "allow", "x *": {"action": "deny", "reason": "not x"}, "x y *": {"action": "deny"}, "x y z": "ask"}',
    "deny_all": '{"*": "deny", "ls*": "allow", "cat *": "allow", "cat *.env": "deny", "cat *.env.example": "allow"}',
    "stars": '{"*": "allow", "*a*": "ask", "*b*": "deny", "*a*b*": "allow"}',
    "case": '{"*": "allow", "Make *": "deny", "MAKE": "ask"}',
    "duplicates": '{"*": "allow", "a *": "deny", "*": "ask", "b *": "deny", "b *": "allow"}',
    "spaces": '{"*": "allow", " *": "deny", "* ": "ask", "a  b": "deny"}',
    "network": '{"*": "allow", "docker run *": "deny", "docker run *--network=none *": "allow"}',
    "middle": '{"*": "allow", "git -* push *": "ask", "pixi * -c *": "deny", "rsync *:*": "deny"}',
}

# A JS object lists integer-like keys first, whatever the file's order.
INTEGER_KEYS = '{"*": "allow", "7": "deny", "42 *": "deny", "0": "ask", "12": "deny", "007": "deny"}'

# Rule sets the gate's schema rejects as a whole (it then fails closed to ask).
INVALID_SETS = {
    "empty_first": '{"": "deny", "*": "ask", "x": "allow"}',
    "empty_last": '{"*": "allow", "": "deny"}',
    "ask_object": '{"*": "allow", "x *": {"action": "ask", "reason": "why"}}',
    "unknown_action": '{"*": "allow", "x *": "block"}',
}
INVALID_COMMANDS = {"empty_first": ["x", "ls"], "empty_last": ["", "ls"], "ask_object": ["x y", "z"],
                    "unknown_action": ["x y", "z"]}

GENERIC_COMMANDS = ["ls", "x", "git status", "a b c", "rm -rf build", "make"]

# Command names a wrapper, shell or keyword reads past, in the gate or the guard.
WRAPPER_NAMES = {
    "sudo", "doas", "env", "xargs", "nohup", "time", "timeout", "nice", "setsid", "stdbuf", "flock",
    "caffeinate", "watch", "command", "exec", "pixi", "uv", "uvx", "pipx", "parallel", "eval", "sh", "bash",
    "dash", "zsh", "ksh", "fish", "find", "fd", "builtin", "[", "[[", "if", "for", "while", "case", "docker",
    "podman", "busybox", "nix", "npx", "chroot", "ionice", "taskset", "script", "su", "runuser",
}
SYNTAX = "'\"\\$`;&|()<>#!{}~"


def readable(command):
    """No shell syntax: the guard reads it as one command of whitespace-separated words."""
    return bool(command.split()) and not any(c in SYNTAX or c == "\n" for c in command)


def plain(command):
    """One simple command every implementation reads alike: single spaces, no syntax, no wrapper."""
    if not readable(command) or command != " ".join(command.split()):
        return False
    first = command.split(" ")[0]
    return "=" not in first and "/" not in first and first not in WRAPPER_NAMES


def ruleset_commands(rules):
    out = [p.replace("*", s).replace("?", q) for p in rules for s, q in (("x", "q"), ("", "é"), (" y", ""))]
    return unique(out + GENERIC_COMMANDS)


def real_commands():
    """A command derived from every other real bash pattern: filled, bared, glued on or renamed, in turn."""
    out = []
    for i, pattern in enumerate(p for p in REAL["bash"] if p != "*"):
        filled = pattern.replace("*", "x").replace("?", "q")
        derived = [filled]
        if pattern.endswith(" *"):
            derived.append(pattern[:-2])                          # the bare command
        elif pattern.endswith("*"):
            derived.append(pattern[:-1] + "-y")                   # glued on: `apt-get install-y`
        if " " in filled:
            head, tail = filled.split(" ", 1)
            derived.append(f"{head}-x {tail}")                    # another command
        out.append(derived[i % len(derived)])
    return unique(out)[::2]


# Chains: the gate splits them and the first of the most restrictive commands decides.
CHAINS = [
    ("overlap", "ls && git push x"), ("overlap", "git push --dry-run x; git status"),
    ("overlap", "git status | git push"), ("overlap", "ls || git commit"), ("overlap", "git push x\nls"),
    ("overlap", "ls & git push"), ("deny_all", "ls -la && cat a.env"), ("deny_all", "cat a && cat b.env.example"),
    ("deny_all", "ls; rm x"), ("shadowed", "ls && rm -rf /"), ("shadowed", "git push; ls"),
    ("questions", "ab && ls"), ("questions", "abc x | ls"), ("reasons", "ls && x y z"), ("reasons", "x; x y"),
    ("stars", "zzz && a && b"), ("stars", "ab; ba"), ("trailing", "tool -n x && tool"),
    ("no_catch_all", "ls x && rm y"), ("no_catch_all", "ls x && make"),
]

# Whitespace the guard re-spells and the gate keeps.
SPACING = [
    ("overlap", "git  push x"), ("overlap", "git\tpush x"), ("trailing", "tool  x"), ("spaces", "a  b"),
    ("reasons", "x  y z"), ("shadowed", "rm  -rf  /"), ("deny_all", "cat  a.env"), ("middle", "rsync  a:b"),
]

HOME_RULES = '{"*": "allow", "~/bin/tool *": "deny", "$HOME/bin/other *": "deny", "${HOME}/lib *": "ask",' \
             ' "~": "deny", "~user/x": "deny", "$HOMEDIR *": "ask"}'
HOME_COMMANDS = ["~/bin/tool x", "{home}/bin/tool x", "$HOME/bin/other y", "{home}/bin/other y",
                 "${HOME}/lib z", "{home}/lib z", "~", "{home}", "~user/x", "$HOMEDIR q"]

# Paths against the real path rules; the tool alternates read / write.
PATH_CASES = [
    "a.txt", "src/main.py", ".env", "config/.env", "app.env.local", ".env.example", "sub/.env.example",
    ".git/config", "./.git/HEAD", "src/../.git/config", "sub/.git/objects/x", "key.pem", "deep/a/b/server.pem",
    "id_rsa.pub", "keys/my_id_rsa", "notes/.envrc", "a.environment", ".gitignore", "x/.github/workflows/ci.yml",
    "~/.ssh/config", "~/.ssh", "~/.aws/credentials", "~/.config/gh/hosts.yml", "~/.gnupg/pubring.kbx",
    "~/.kube/config", "~/.kube/cache/x", "~/.docker/config.json", "~/.netrc", "~/.npmrc", "~/.pypirc",
    "~/.git-credentials", "~/.pi/agent/auth.json", "~/.claude/settings.json", "~/.claude.json",
    "~/Library/Keychains/login.keychain-db", "~/Library/Application Support/Google/Chrome/Default/Cookies",
    "~/Library/Application Support/Firefox/x", "~/.local/share/keyrings/login", "~/.local/share/other",
    "~/notes.txt", "~/project/.env", "{home}/.ssh/id_ed25519", "{home}/.netrc", "../outside.txt",
    "../outside/.git/config", "{cwd}/src/a.py", "{cwd}/.git/config", "/etc/hosts", "/etc/ssl/cert.pem",
    "src//double.py", "src/./dot.py", "./a.txt", "sub/", "~/.config/gcloud/creds.json",
    "naïve.env", "日本/.git/x", "a b/c.pem", "[x].env", "~/.mozilla/firefox/p", "~/.azure/x",
]

# Paths against the real external_directory rules, with read and with write.
EXTERNAL_CASES = [
    "/etc/hosts", "/tmp", "/tmp/x/y", "/private/tmp/z", "/tmp/pi-subagents-uid-501/a/b",
    "/var/folders/ab/cd/T/pi-subagents-uid-501/x", "/var/folders/ab/T/pi-subagents-uid-501/x",
    "{install}", "{install}/bin/pi", "{install}x/y", "{agent}/workflows", "{agent}/workflows/w.json",
    "{agent}/auth.json", "~/.cache/elm-pi/worktrees/w1/a.py", "~/.cache/elm-pi/other", "/usr/share/dict/words",
]


def slug(text):
    text = text.encode("ascii", "backslashreplace").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "empty"


ALL_SETS = {**RULE_SETS, **INVALID_SETS, "integer_keys": INTEGER_KEYS, "home": HOME_RULES,
            "real": json.dumps(REAL["bash"])}
WILD = wildcard_cases() + SPECIAL_WILD
SYNTHETIC_DECIDE = [(name, c) for name in RULE_SETS for c in ruleset_commands(json.loads(RULE_SETS[name]))[:7]]
INTEGER_DECIDE = [("integer_keys", c) for c in ["7", "0", "12", "42 x", "007", "8"]]
INVALID_DECIDE = [(name, c) for name, commands in INVALID_COMMANDS.items() for c in commands]
REAL_DECIDE = [("real", c) for c in real_commands()]
HOME_DECIDE = [("home", c) for c in HOME_COMMANDS]
DECIDE = SYNTHETIC_DECIDE + INTEGER_DECIDE + INVALID_DECIDE + REAL_DECIDE + CHAINS + SPACING + HOME_DECIDE
PATHS = [(("read", "write")[i % 2], p) for i, p in enumerate(PATH_CASES)]
EXTERNAL = [(tool, p) for p in EXTERNAL_CASES for tool in ("read", "write")]


# --- one node process -------------------------------------------------------

RUNNER = r"""
const [jitiPath, pkg, base, casesPath, guardCopy] = process.argv.slice(1);
const { readFileSync, mkdirSync, writeFileSync } = await import("node:fs");
const { createJiti } = await import(jitiPath);
const jiti = createJiti(import.meta.url, { fsCache: false });
const load = (p) => jiti.import(`${pkg}/src/${p}`);
const { compileWildcardPattern } = await load("policy/wildcard-matcher.ts");
const { PermissionManager } = await load("policy/permission-manager.ts");
const { PermissionResolver } = await load("policy/permission-resolver.ts");
const { BashProgram } = await load("access-intent/bash/program.ts");
const { resolveBashCommandCheck } = await load("handlers/gates/bash-command.ts");
const { PathNormalizer } = await load("path/path-normalizer.ts");
const { posixPathFlavor } = await load("path/path-flavor.ts");
const { capabilitySurfaceForTool } = await load("access-intent/path-surfaces.ts");
const { loadUnifiedConfig } = await load("config/config-loader.ts");
const guard = await jiti.import(guardCopy);

const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const cwd = `${base}/project`;
const normalizer = new PathNormalizer(posixPathFlavor, cwd);
const pick = (r) => ({ state: r.state, pattern: r.matchedPattern ?? null, reason: r.reason ?? null });
const out = { wild: [], decide: {}, paths: {}, external: {}, issues: {} };

for (const [pattern, value] of cases.wild) {
  out.wild.push({ gate: compileWildcardPattern(pattern, null).matches(value), guard: guard.wildcard(pattern).test(value) });
}

// One agent dir per rule set, read by the package the way pi reads it.
const managers = {};
const manager = (name) => {
  if (managers[name]) return managers[name];
  const agentDir = `${base}/agents/${name}`;
  mkdirSync(`${agentDir}/extensions/pi-permission-system`, { recursive: true });
  writeFileSync(`${agentDir}/extensions/pi-permission-system/config.json`,
    `{"permission": {"*": "allow", "bash": ${cases.ruleSets[name]}}}`);
  const m = new PermissionManager({ agentDir });
  m.configureForCwd(cwd);
  out.issues[name] = loadUnifiedConfig(`${agentDir}/extensions/pi-permission-system/config.json`).issues.length;
  // The guard's rules as it reads them from that file, in the file's order.
  const rules = guard.bashRulesOf(readFileSync(`${agentDir}/extensions/pi-permission-system/config.json`, "utf8"));
  return (managers[name] = { m, resolver: new PermissionResolver(m, { getRuleset: () => [] }), rules });
};
const allDeny = (rules) => rules.map(([k]) => [k, "deny"]);
for (const [name, command] of cases.decide) {
  const { m, resolver, rules } = manager(name);
  const raw = pick(m.check({ kind: "bash-command", surface: "bash", command, spellings: [], agentName: undefined }, []));
  const program = await BashProgram.parse(command, normalizer);
  const gate = pick(resolveBashCommandCheck(command, program.commands(), undefined, resolver));
  const units = program.commands().map((c) => c.text);
  const winner = guard.deniedSpelling(command, allDeny(rules));
  const denial = guard.deniedSpelling(command, rules);
  out.decide[`${name}\u0000${command}`] = {
    raw, gate, units,
    guardWinner: winner ? winner.pattern : null,
    guardDeny: denial ? { pattern: denial.pattern, reason: denial.reason ?? null, spelling: denial.spelling } : null,
  };
}

const real = new PermissionManager({ agentDir: cases.realAgent });
real.configureForCwd(cwd);
const realResolver = new PermissionResolver(real, { getRuleset: () => [] });
const onSurface = (family, tool, path) => {
  const access = normalizer.forToolPath(tool, path);
  const surface = capabilitySurfaceForTool(family, tool);
  return { ...pick(realResolver.resolve({ kind: "access-path", surface, path: access })), values: access.matchValues() };
};
for (const [tool, path] of cases.paths) out.paths[`${tool} ${path}`] = onSurface("path", tool, path);
for (const [tool, path] of cases.external) out.external[`${tool} ${path}`] = onSurface("external_directory", tool, path);
console.log(JSON.stringify(out));
"""


def make_fill(home, cwd, install, agent):
    table = {"{home}": str(home), "{cwd}": str(cwd), "{install}": str(install), "{agent}": str(agent)}

    def fill(text):
        for key, value in table.items():
            text = text.replace(key, value)
        return text
    return fill


@functools.lru_cache(maxsize=None)
def results():
    """Every case through the package and the guard in one node process; None when not installed."""
    binary = node()
    if not binary or not (PACKAGE / "src/service.ts").exists() or not JITI.exists():
        return None
    # Resolved, so no folder in it is a symlink (macOS /var is /private/var).
    base = Path(tempfile.mkdtemp()).resolve()
    try:
        home, cwd, install = base / "home", base / "project", base / "install"
        agent = install / "agent"
        policy = agent / "extensions/pi-permission-system"
        for d in (home, cwd / "src", cwd / "sub", cwd / ".git", policy):
            d.mkdir(parents=True)
        for f in ("a.txt", "src/main.py", ".env", ".git/config"):
            (cwd / f).write_text("x\n")
        text = TEMPLATE.read_text().replace("@AGENT_DIR@", str(agent)).replace("@INSTALL_DIR@", str(install))
        (policy / "config.json").write_text(text)
        # command-guard.ts with its private wildcard() exported, nothing else changed.
        guard_copy = base / "guard/command-guard.ts"
        guard_copy.parent.mkdir()
        guard_copy.write_text(GUARD.read_text() + "\nexport { wildcard };\n")
        fill = make_fill(home, cwd, install, agent)
        cases = {
            "wild": [[p, fill(v)] for p, v, _ in WILD] + [[p, fill(v)] for p, v in HOME_WILD],
            "ruleSets": ALL_SETS,
            "decide": [[n, fill(c)] for n, c in DECIDE],
            "realAgent": str(agent),
            "paths": [[t, fill(p)] for t, p in PATHS],
            "external": [[t, fill(p)] for t, p in EXTERNAL],
        }
        (base / "cases.json").write_text(json.dumps(cases))
        run = subprocess.run(
            [binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
             str(JITI), str(PACKAGE), str(base), str(base / "cases.json"), str(guard_copy)],
            cwd=cwd, capture_output=True, text=True, timeout=300,
            env={**os.environ, "HOME": str(home), "NO_COLOR": "1", "PI_CODING_AGENT_DIR": str(agent)})
        if run.returncode != 0:
            raise AssertionError(f"the matcher runner failed:\n{run.stderr}")
        out = json.loads(run.stdout)
        out["fill"] = fill
        out["dirs"] = {"home": str(home), "cwd": str(cwd), "install": str(install), "agent": str(agent)}
        out["wild"] = dict(zip([tuple(c) for c in cases["wild"]], out["wild"]))
        return out
    finally:
        shutil.rmtree(base, ignore_errors=True)


# --- the tests --------------------------------------------------------------

class Agreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = results()
        if cls.out is None:
            raise unittest.SkipTest("needs node and the installed pi-permission-system (run bootstrap.sh)")

    def decided(self, name, command):
        return self.out["decide"][f"{name}\0{self.out['fill'](command)}"]

    @staticmethod
    def pair(result):
        return [result["state"], result["pattern"]]


class WildcardTests(Agreement):
    """One pattern, one value: the gate's compileWildcardPattern, the guard's wildcard(), the Python copy."""

    def check(self, pattern, value):
        got = self.out["wild"][(pattern, value)]
        want = spec_match(pattern, value)
        python = python_decide({pattern: "allow"}, value) is not None
        # By design: the gate counts `?` in UTF-16 units; for every other case that is the same.
        self.assertEqual({"gate": gate_match(pattern, value), "guard": want, "python": want}, {**got, "python": python})
        if gate_match(pattern, value) != want:
            self.assertIsNotNone(check_config.pattern_problem(pattern), "check_config would ship this pattern")


class ShippedPatternTests(unittest.TestCase):
    """What check_config.py lets into the shipped config, the gate applies as written."""

    def test_an_accepted_question_mark_matches_alike_in_units_and_characters(self):
        patterns = SYNTHETIC_PATTERNS + [p for p, _, _ in SPECIAL_WILD] + list(REAL["bash"]) + list(REAL["path"])
        accepted = [p for p in unique(patterns) if "?" in p and check_config.pattern_problem(p) is None]
        self.assertIn("brew tap ?*", accepted)
        for pattern in accepted:
            for value in unique(ASTRAL_VALUES + instances(pattern.replace("?", "😀"))):
                self.assertEqual(spec_match(pattern, value), gate_match(pattern, value), (pattern, value))

    def test_a_question_mark_that_could_differ_is_refused(self):
        for pattern in ("?", "a?", "??", "a??b", "??*", "*??", "x?y *", "? *"):
            self.assertRegex(check_config.pattern_problem(pattern) or "", "UTF-16", pattern)

    def test_integer_like_keys_are_refused(self):
        # The keys a JS object moves ahead of an earlier "*".
        moved = [k for k in json.loads(INTEGER_KEYS) if k != "*" and next(iter(js_order({"*": 1, k: 1}))) == k]
        self.assertEqual(["7", "0", "12"], moved)
        for key in json.loads(INTEGER_KEYS):
            self.assertEqual(key in moved, check_config.pattern_problem(key) is not None, key)
        self.assertIsNotNone(check_config.pattern_problem("4294967294"))
        self.assertIsNone(check_config.pattern_problem("4294967295"))   # not an array index: kept in place

    def test_the_shipped_config_has_no_such_key(self):
        self.assertEqual([], check_config.rule_problems(TEMPLATE))

    def test_rule_problems_names_the_surface_and_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"permission": {"*": "ask", "bash": {"*": "allow", "22": "deny", "x?": "ask"},
                                                       "path": {"*": "allow"}}}))
            problems = check_config.rule_problems(path)
        self.assertEqual(2, len(problems))
        self.assertIn('permission.bash rule "22" is integer-like', problems[0])
        self.assertIn('permission.bash rule "x?" has `?`', problems[1])


class HomePatternTests(Agreement):
    """By design: the gate expands a home prefix in the pattern, the guard and the Python copy do not."""

    def check(self, pattern, value):
        home = self.out["dirs"]["home"]
        value = self.out["fill"](value)
        got = self.out["wild"][(pattern, value)]
        self.assertEqual(spec_match(expand_home(pattern, home), value), got["gate"])
        self.assertEqual(spec_match(pattern, value), got["guard"])
        self.assertEqual(spec_match(pattern, value), python_decide({pattern: "allow"}, value) is not None)


class RuleSetCase(Agreement):
    """A command under a rule set: decision and winning rule, from all three and the documented rules."""

    def check(self, name, command, order=None):
        rules = json.loads(ALL_SETS[name])
        if order:
            rules = order(rules)
        got = self.decided(name, command)
        # The gate trims (unless nothing would be left); the Python copy is handed the trimmed text.
        trimmed = command.strip() or command
        want = spec_decide(rules, trimmed)
        self.assertEqual(want, python_decide(rules, trimmed))
        self.assertEqual(want or ["ask", None], self.pair(got["raw"]))
        if readable(command):
            # The guard's own last-match-wins, on its single-spaced spelling.
            spelled = spec_decide(rules, " ".join(command.split()))
            self.assertEqual(spelled and spelled[1], got["guardWinner"])
        if plain(command):
            # A plain command is one unit to the gate, and the guard adds only a deny.
            self.assertEqual([command], got["units"])
            self.assertEqual(self.pair(got["raw"]), self.pair(got["gate"]))
            deny = got["raw"]["pattern"] if got["raw"]["state"] == "deny" else None
            self.assertEqual(deny, got["guardDeny"] and got["guardDeny"]["pattern"])
            if deny is not None:
                rule = rules[deny]
                reason = None if isinstance(rule, str) else rule.get("reason")
                self.assertEqual(reason, got["gate"]["reason"])
                self.assertEqual(reason, got["guardDeny"]["reason"])


class RuleSetTests(RuleSetCase):
    """Synthetic rule sets: regex characters, unicode, overlapping, shadowed and duplicated rules."""


class IntegerKeyTests(Agreement):
    """By design: the gate applies integer-like patterns first, as a JS object lists them; the guard keeps the file's order."""

    def check(self, command):
        rules = json.loads(INTEGER_KEYS)
        got = self.decided("integer_keys", command)
        self.assertEqual(spec_decide(js_order(rules), command) or ["ask", None], self.pair(got["raw"]))
        written = spec_decide(rules, command)
        self.assertEqual(written, python_decide(rules, command))
        self.assertEqual(written and written[1], got["guardWinner"])
        deny = written[1] if written and written[0] == "deny" else None
        self.assertEqual(deny, got["guardDeny"] and got["guardDeny"]["pattern"])


class InvalidConfigTests(Agreement):
    """By design: the gate rejects the whole rule set and asks; the others match the rules as written."""

    def check(self, name, command):
        rules = json.loads(ALL_SETS[name])
        got = self.decided(name, command)
        self.assertGreater(self.out["issues"][name], 0)
        self.assertEqual(["ask", None], self.pair(got["raw"]))
        self.assertEqual(["ask", None], self.pair(got["gate"]))
        want = spec_decide(rules, command)
        self.assertNotEqual(want, ["ask", None])
        self.assertEqual(want, python_decide(rules, command))
        if readable(command):
            self.assertEqual(want and want[1], got["guardWinner"])


class RealPolicyTests(RuleSetCase):
    """Commands derived from every other real bash rule: the three agree on the shipped policy."""


class ChainTests(Agreement):
    """By design: the gate decides each command of a chain, the Python copy the whole string."""

    def check(self, name, command):
        rules = json.loads(ALL_SETS[name])
        got = self.decided(name, command)
        segments = [s.strip() for s in re.split(r"&&|\|\||[;|&\n]", command)]
        self.assertEqual(segments, got["units"])
        each = [spec_decide(rules, s) or ["ask", None] for s in segments]
        self.assertEqual(first_most_restrictive(each), self.pair(got["gate"]))
        self.assertEqual(spec_decide(rules, command), python_decide(rules, command))
        self.assertEqual(spec_decide(rules, command) or ["ask", None], self.pair(got["raw"]))
        # The guard adds the first denied command's rule.
        denied = next((d[1] for d in each if d[0] == "deny"), None)
        self.assertEqual(denied, got["guardDeny"] and got["guardDeny"]["pattern"])


class SpacingTests(Agreement):
    """By design: the gate matches the spacing as typed, the guard one space between words."""

    def check(self, name, command):
        rules = json.loads(ALL_SETS[name])
        got = self.decided(name, command)
        typed = spec_decide(rules, command)
        spelled = spec_decide(rules, " ".join(command.split()))
        self.assertEqual([command], got["units"])
        self.assertEqual(typed, self.pair(got["gate"]))
        self.assertEqual(typed, python_decide(rules, command))
        self.assertEqual(spelled[1], got["guardWinner"])
        # A deny in the re-spelling is added; so is an ask the typed spacing hides.
        if spelled[0] == "deny" or (spelled[0] == "ask" and typed[0] == "allow"):
            self.assertEqual(spelled[1], got["guardDeny"]["pattern"])
        else:
            self.assertIsNone(got["guardDeny"])


class HomeCommandTests(Agreement):
    """By design: the gate expands home in bash patterns and commands; the others match `~` as written."""

    def check(self, command):
        rules = json.loads(HOME_RULES)
        home = self.out["dirs"]["home"]
        command = self.out["fill"](command)
        got = self.decided("home", command)
        expanded = {expand_home(p, home): r for p, r in rules.items()}
        names = dict(zip(expanded, rules))
        rename = lambda d: d and [d[0], names[d[1]]]
        self.assertEqual(rename(spec_decide(expanded, command)), self.pair(got["raw"]))
        # The gate's unit also carries the command's home spelling.
        self.assertEqual(rename(spec_any(expanded, unique([command, expand_home(command, home)]))),
                         self.pair(got["gate"]))
        written = spec_decide(rules, command)
        self.assertEqual(written, python_decide(rules, command))
        self.assertEqual(written[1], got["guardWinner"])


def path_values(raw, cwd, home):
    """The forms the gate matches a path by, as Python's os.path computes them."""
    absolute = os.path.normpath(os.path.join(cwd, expand_home(raw, home)))
    values = [absolute]
    if absolute.startswith(cwd + os.sep):
        values.append(os.path.relpath(absolute, cwd))
    if not raw.startswith(("/", "~")):
        values.append(raw)
    values.append(os.path.realpath(absolute))
    return unique(values)


def python_any(rules, values):
    """The Python copy over several forms: the latest rule any form's winner is."""
    order = list(rules)
    winners = [python_winner(rules, v) for v in values]
    found = [w for w in winners if w is not None]
    if not found:
        return None
    best = max(found, key=order.index)
    return [action_of(rules[best]), best]


class PathCase(Agreement):
    """A file tool's path under the real `path` rules: the gate, and the Python copy on os.path's forms."""

    surface = "paths"

    def rules(self, tool):
        return REAL["path"]

    def check(self, tool, path):
        dirs = self.out["dirs"]
        filled = self.out["fill"](path)
        got = self.out[self.surface][f"{tool} {filled}"]
        values = path_values(filled, dirs["cwd"], dirs["home"])
        self.assertEqual(sorted(values), sorted(got["values"]))
        rules = {self.out["fill"](p): r for p, r in self.rules(tool).items()}
        expanded = {expand_home(p, dirs["home"]): r for p, r in rules.items()}
        names = dict(zip(expanded, rules))
        want = spec_any(expanded, values)
        python = python_any(expanded, values)
        self.assertEqual(want, python)
        self.assertEqual([want[0], names[want[1]]], self.pair(got))


class PathTests(PathCase):
    """Project files, home credentials, .env and .git, typed absolute, relative, with ~ and ../."""


class ExternalDirectoryTests(PathCase):
    """A path outside the project under the real `external_directory` rules; read adds its own allows."""

    surface = "external"

    def rules(self, tool):
        base = {k.replace("@INSTALL_DIR@", "{install}").replace("@AGENT_DIR@", "{agent}"): v
                for k, v in REAL["external_directory"].items()}
        extra = {k.replace("@INSTALL_DIR@", "{install}").replace("@AGENT_DIR@", "{agent}"): v
                 for k, v in REAL["external_directory_read"].items()}
        assert not set(base) & set(extra)
        # The family key's rules first, then the direction's own (expandDirectionalSugar).
        return {**base, **extra} if tool == "read" else base


def add(cls, name, method, note=""):
    if note.startswith("BUG:"):
        method = unittest.expectedFailure(method)
    method.__doc__ = note or None
    assert not hasattr(cls, name), name
    setattr(cls, name, method)


def build():
    for i, (pattern, value, note) in enumerate(WILD):
        add(WildcardTests, f"test_{i:03d}_{slug(pattern)}_vs_{slug(value)}",
            lambda self, p=pattern, v=value: self.check(p, v), note)
    for i, (pattern, value) in enumerate(HOME_WILD):
        add(HomePatternTests, f"test_{i:03d}_{slug(pattern)}_vs_{slug(value)}",
            lambda self, p=pattern, v=value: self.check(p, v))
    for i, (name, command) in enumerate(SYNTHETIC_DECIDE):
        add(RuleSetTests, f"test_{i:03d}_{name}_{slug(command)}", lambda self, n=name, c=command: self.check(n, c))
    for i, (_, command) in enumerate(INTEGER_DECIDE):
        add(IntegerKeyTests, f"test_{i:03d}_{slug(command)}", lambda self, c=command: self.check(c))
    for i, (name, command) in enumerate(INVALID_DECIDE):
        add(InvalidConfigTests, f"test_{i:03d}_{name}_{slug(command)}", lambda self, n=name, c=command: self.check(n, c))
    for i, (_, command) in enumerate(REAL_DECIDE):
        add(RealPolicyTests, f"test_{i:03d}_{slug(command)}", lambda self, c=command: self.check("real", c))
    for i, (name, command) in enumerate(CHAINS):
        add(ChainTests, f"test_{i:03d}_{name}_{slug(command)}", lambda self, n=name, c=command: self.check(n, c))
    for i, (name, command) in enumerate(SPACING):
        add(SpacingTests, f"test_{i:03d}_{name}_{slug(command)}", lambda self, n=name, c=command: self.check(n, c))
    for i, command in enumerate(HOME_COMMANDS):
        add(HomeCommandTests, f"test_{i:03d}_{slug(command)}", lambda self, c=command: self.check(c))
    for i, (tool, path) in enumerate(PATHS):
        add(PathTests, f"test_{i:03d}_{tool}_{slug(path)}", lambda self, t=tool, p=path: self.check(t, p))
    for i, (tool, path) in enumerate(EXTERNAL):
        add(ExternalDirectoryTests, f"test_{i:03d}_{tool}_{slug(path)}", lambda self, t=tool, p=path: self.check(t, p))


build()


if __name__ == "__main__":
    unittest.main()
