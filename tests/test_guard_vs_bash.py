"""command-guard.ts's reading of a bash command, checked against bash itself.

templates/extensions/command-guard.ts has its own small shell lexer
(commandsOf) and its own idea of which commands a command line runs
(collectRuns, behind deniedSpelling). Both stand in for bash, so this file
asks bash and compares, case by generated case:

- the words of a simple command: generated from quotes, $'...' and $"..."
  strings, backslashes, globs, comments and line continuations, each must
  split and unquote exactly as bash's own `eval "set -- <words>"` does (with
  noglob, and only words that expand to nothing but themselves);
- the simple commands of a program: generated simple commands joined by
  operators, lists, subshells, groups, compound commands, redirections,
  heredocs, comments and substitutions must come out as the same commands,
  each with bash's words, in the order the guard lists them. Every program
  parses in bash (as the body of a function that is defined, never called);
- deniedSpelling: every generated spelling of a denied tool (ssh, scp, nc,
  rclone, ...) - quoted, escaped, $'\\x..', a path - which bash resolves to that
  tool, in every context, behind every wrapper and in a `bash -c` or `eval`
  payload, is denied with the tool's own rule; and a command that only names
  the tool as an argument, as data or in a comment is not.

Nothing is executed: bash only splits inert words and defines functions,
with PATH pointing nowhere, in a temporary folder. One bash process and one
node process answer every case. A case marked BUG is a real disagreement
with bash, kept as an expected failure (none is, now). A command too deeply
nested or a brace expansion too large to read is refused outright; RefusalTests
holds those.
"""

import functools
import importlib.util
import json
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "templates/extensions/command-guard.ts"
RULES = json.loads((ROOT / "templates/extensions/pi-permission-system/config.json").read_text())["permission"]["bash"]


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def modern_bash():
    """A bash new enough for $'\\u..' and |& (4.4+); macOS's /bin/bash is 3.2."""
    for candidate in (shutil.which("bash"), "/usr/local/bin/bash", "/opt/homebrew/bin/bash", "/bin/bash"):
        if not candidate or not Path(candidate).exists():
            continue
        run = subprocess.run([candidate, "-c", "echo ${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"],
                             capture_output=True, text=True, env={"PATH": "/nonexistent"})
        major, minor = (int(n) for n in run.stdout.split())
        if (major, minor) >= (4, 4):
            return candidate
    return None


def existing_commands():
    """The bash cases tests/test_permission_rules.py already decides, so none is repeated here."""
    spec = importlib.util.spec_from_file_location("permission_rules_cases", ROOT / "tests/test_permission_rules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {command for command, _, _ in module.BASH}


EXISTING = existing_commands()


def basename(word):
    return word[word.rfind("/") + 1:]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48] or "empty"


def sq(text):
    """text as one single-quoted bash word."""
    return "'" + text.replace("'", "'\\''") + "'"


def dq(text):
    """text as one double-quoted bash word."""
    return '"' + re.sub(r'([\\"$`])', r"\\\1", text) + '"'


# --- words: pieces of a word whose value bash computes without side effects.
# None contains an unquoted operator, expansion or substitution, so
# `eval "set -- ..."` over them only splits and unquotes.
PLAIN_ATOMS = [
    "a", "ssh", "x1", "-v", "--opt=1", "a.b", "p/q", "@", "%", "+", ":", ",", "=", "a=b", "^", "]",
    "*", "?", "[ab]", "-", "--", "a#b", "{", "}", "!x", "0",
    "'a b'", "''", "'\"'", "'#'", "';'", "'|&'", "'a\tb'", "' '", "'$x'", "'$(ssh h)'", "'`ssh h`'",
    '"a b"', '""', '"#"', '"a\tb"', '"$"', '"\'"', '";|&<>"',
    '$"a b"', '$""', "$''", "$'a b'",
]
ESCAPED_ATOMS = [
    "\\ ", "\\'", '\\"', "\\\\", "\\$", "\\#", "\\;", "\\|", "\\&", "\\(", "\\)", "\\<", "\\>", "\\a",
    "\\\t", "\\*", "\\`", "\\{",
    '"\\$"', '"\\\\"', '"\\""', '"\\`"', '"\\a"', '"x\\\ny"', '"\\\'"', '"\\n"',
    "$'a\\tb'", "$'\\x41'", "$'\\101'", "$'\\''", "$'\\\\'", "$'\\n'", "$'\\e'", "$'\\u0041'", "$'\\x4g'",
    "$'\\q'", "$'\\\"'", '$"\\$"',
]
# A comment and a line continuation only mean anything between words.
WORD_ONLY_ATOMS = ["#c", "#"]
BLANK_RUNS = [" ", "\t", "  ", " \t ", " \\\n ", "\\\n "]


def generate_word(rng, atoms):
    return "".join(rng.choice(atoms) for _ in range(rng.choice([1, 1, 2, 2, 3])))


def generate_words(rng, atoms, count, leading=True, trailing=True):
    words = [generate_word(rng, atoms) for _ in range(count)]
    text = words[0]
    for word in words[1:]:
        text += rng.choice(BLANK_RUNS) + word
    if leading and rng.random() < 0.15:
        text = rng.choice([" ", "\t"]) + text
    if trailing and rng.random() < 0.15:
        text += rng.choice([" ", "\t"])
    return text


def word_cases():
    rng = random.Random(20261103)
    atoms = PLAIN_ATOMS + ESCAPED_ATOMS
    # The escape cases below stand alone; a generated word does not repeat one.
    seen, cases = {source for source, _ in escape_cases()}, []
    while len(cases) < 120:
        source = generate_words(rng, atoms + (WORD_ONLY_ATOMS if rng.random() < 0.2 else []), rng.randint(1, 5))
        if source in seen or source.lstrip(" \t").startswith(("#", "\\\n")):
            continue
        seen.add(source)
        cases.append((source, ""))
    return cases


# Every escape of $'...' and of a double-quoted string, one at a time.
ANSI_C_BODIES = [
    "\\a", "\\b", "\\e", "\\E", "\\f", "\\n", "\\r", "\\t", "\\v", "\\\\", "\\'", '\\"', "\\?",
    "\\x41", "\\x4", "\\x4142", "\\x", "\\xg", "\\xG1", "\\X41", "\\101", "\\1", "\\18", "\\0101", "\\177", "\\8",
    "\\u41", "\\u0041", "\\u00410", "\\uZ", "\\z", "\\ ", "\\x7e\\x7E", "s\\163\\x68", "\\x73\\x73\\x68",
    # \cX is control-X (a backslash after it is taken with the one escaping it), \U takes
    # up to eight hex digits, and a NUL ends the value.
    "\\cA", "\\ca", "\\c[", "\\c?", "\\c1", "\\c", "\\c\\\\", "\\c\\\\x", "\\c\\a", "\\c\\'",
    "\\U41", "\\U00000073sh", "\\U000000731", "\\U", "\\Ug",
    "ss\\0h", "ss\\x00h", "ss\\u0000h", "ss\\c@h",
]
DOUBLE_QUOTED_BODIES = [
    "\\$", "\\\\", '\\"', "\\`", "\\a", "\\n", "\\'", "\\ ", "\\#", "a\\\nb", "\\\\\\$", "$", "'", "#a",
]


def escape_cases():
    cases = [(f"$'{body}'", "") for body in ANSI_C_BODIES]
    cases += [(f'"{body}"', "") for body in DOUBLE_QUOTED_BODIES]
    cases += [(f'$"{body}"', "") for body in ("\\$", "a b", "\\\\")]
    # Brace expansion makes several words of one, and an empty one none unless quoted.
    cases += [(source, "") for source in (
        "{a,b}", "x{1,2}y z", "{a}", "'{a,b}'", "\\{a,b}", "{,}", "''{,}", "x{,}", "{a,}\"\"", "{,}{,}",
        "{a}{b,c}", "{a,b}{c}", "{a{b,c}", "{a,b", "{{a,b}", "{a,b}}", "a{b,c}d{e,f}", "{a,{b,c}}",
        "{a,'b,c'}", "{a,b\\}c}", "{a\\,b,c}", "{}", "x{}y", "{ab}{c,d}",
        "{1..3}", "{01..3}", "{-01..1}", "{3..1}", "{1..10..3}", "{1..3..0}", "{a..e..2}", "{z..w}", "{s..s}sh",
        "{a..}", '{"a"..c}', "{a..c}{1,2}",
    )]
    return cases


# --- structure: generated simple commands put together. Each template is
# (name, program from the commands' sources, the commands the guard should
# list from the commands' bash words and sources).
STRUCTURE_ATOMS = [a for a in PLAIN_ATOMS + ESCAPED_ATOMS
                   if a not in ("{", "}", "!x", "0", "a=b", "--opt=1", "=") and "#" not in a.strip("'\"") and "\n" not in a]
# Inside backticks a backslash is read twice; these pieces have none.
BACKTICK_ATOMS = [a for a in STRUCTURE_ATOMS if "\\" not in a and "`" not in a]

TEMPLATES = [
    ("semicolon", "{A} ; {B}", lambda a, b, sa, sb: [a, b]),
    ("semicolon_tight", "{A};{B}", lambda a, b, sa, sb: [a, b]),
    ("and", "{A} && {B}", lambda a, b, sa, sb: [a, b]),
    ("or_tight", "{A}||{B}", lambda a, b, sa, sb: [a, b]),
    ("pipe", "{A} | {B}", lambda a, b, sa, sb: [a, b]),
    ("pipe_stderr", "{A} |& {B}", lambda a, b, sa, sb: [a, b]),
    ("background", "{A} & {B}", lambda a, b, sa, sb: [a, b]),
    ("background_last", "{A}&", lambda a, b, sa, sb: [a]),
    ("newline", "{A}\n{B}", lambda a, b, sa, sb: [a, b]),
    ("blank_lines", "\n\n{A}\n\n{B}\n", lambda a, b, sa, sb: [a, b]),
    ("continued_operator", "{A} \\\n&& {B}", lambda a, b, sa, sb: [a, b]),
    ("subshell", "({A})", lambda a, b, sa, sb: [a]),
    ("subshell_list", "( {A} ; {B} )", lambda a, b, sa, sb: [a, b]),
    ("group", "{ {A}; }", lambda a, b, sa, sb: [["{"] + a, ["}"]]),
    ("negated_pipe", "! {A} | {B}", lambda a, b, sa, sb: [["!"] + a, b]),
    ("if", "if {A}; then {B}; fi", lambda a, b, sa, sb: [["if"] + a, ["then"] + b, ["fi"]]),
    ("if_else", "if {A}\nthen :\nelse {B}\nfi", lambda a, b, sa, sb: [["if"] + a, ["then", ":"], ["else"] + b, ["fi"]]),
    ("while", "while {A}; do {B}; done", lambda a, b, sa, sb: [["while"] + a, ["do"] + b, ["done"]]),
    ("until", "until {A}; do {B}; done", lambda a, b, sa, sb: [["until"] + a, ["do"] + b, ["done"]]),
    ("for", "for v in 1 2; do {A}; done", lambda a, b, sa, sb: [["for", "v", "in", "1", "2"], ["do"] + a, ["done"]]),
    ("case", "case w in p) {A};; esac", lambda a, b, sa, sb: [["case", "w", "in", "p"], a, ["esac"]]),
    ("function", "f() { {A}; }", lambda a, b, sa, sb: [["f"], ["{"] + a, ["}"]]),
    ("substitution", "echo $({A})", lambda a, b, sa, sb: [a, ["echo", f"$({sa})"]]),
    ("substitution_list", "echo $({A}; {B}) z", lambda a, b, sa, sb: [a, b, ["echo", f"$({sa}; {sb})", "z"]]),
    ("substitution_nested", "echo $(echo $({A}))",
     lambda a, b, sa, sb: [a, ["echo", f"$({sa})"], ["echo", f"$(echo $({sa}))"]]),
    ("substitution_quoted", 'echo "$({A})"', lambda a, b, sa, sb: [a, ["echo", f"$({sa})"]]),
    ("substitution_in_word", "echo pre$({A})post", lambda a, b, sa, sb: [a, ["echo", f"pre$({sa})post"]]),
    ("substitution_assigned", "v=$({A}) {B}", lambda a, b, sa, sb: [a, [f"v=$({sa})"] + b]),
    ("process_substitution", "cat <({A})", lambda a, b, sa, sb: [a, ["cat", f"<({sa})"]]),
    ("process_substitution_out", "{B} > >({A})", lambda a, b, sa, sb: [a, b]),
    ("redirect_out", "{A} > out ; {B}", lambda a, b, sa, sb: [a, b]),
    ("redirect_both", "{A} 2>&1 | {B}", lambda a, b, sa, sb: [a, b]),
    ("redirect_in_append", "{A} >>out <in", lambda a, b, sa, sb: [a]),
    ("redirect_first", ">out {A}", lambda a, b, sa, sb: [a]),
    ("redirect_all", "{A} &>/dev/null; {B}", lambda a, b, sa, sb: [a, b]),
    ("redirect_clobber", "{A} >| out 3<>rw", lambda a, b, sa, sb: [a]),
    ("here_string", "{A} <<< word; {B}", lambda a, b, sa, sb: [a, b]),
    ("heredoc", "{A} <<EOF\nssh host\nEOF\n{B}", lambda a, b, sa, sb: [a, b]),
    ("heredoc_tabs", "{A} <<-EOF\n\tssh host\n\tEOF\n{B}", lambda a, b, sa, sb: [a, b]),
    ("heredoc_quoted", "{A} <<'EOF'\n$(ssh host)\nEOF\n{B}", lambda a, b, sa, sb: [a, b]),
    ("heredoc_then_more", "{A} <<X; {B}\nssh host\nX", lambda a, b, sa, sb: [a, b]),
    # A comment ends at its newline, a backslash before it or not.
    ("comment", "{A} # ssh 'host \\\n{B}", lambda a, b, sa, sb: [a, b]),
    ("time_pipe", "time {A} | {B}", lambda a, b, sa, sb: [["time"] + a, b]),
]
BACKTICK_TEMPLATES = [
    ("backticks", "echo `{A}`", lambda a, b, sa, sb: [a, ["echo", f"`{sa}`"]]),
    ("backticks_list", "x `{A}; {B}`", lambda a, b, sa, sb: [a, b, ["x", f"`{sa}; {sb}`"]]),
]


def structure_cases():
    rng = random.Random(1103)
    cases = []
    for templates, atoms in ((TEMPLATES, STRUCTURE_ATOMS), (BACKTICK_TEMPLATES, BACKTICK_ATOMS)):
        for name, template, expect in templates:
            for n in range(2):
                sa = generate_words(rng, atoms, rng.randint(1, 3), leading=False, trailing=False)
                sb = generate_words(rng, atoms, rng.randint(1, 3), leading=False, trailing=False)
                program = template.replace("{A}", sa).replace("{B}", sb)
                cases.append((f"{name}_{n}", program, sa, sb, expect))
    return cases


# --- deniedSpelling. Tools whose own `<tool> *` rule denies them.
TOOLS = ["ssh", "scp", "sftp", "sshfs", "ssh-copy-id", "autossh", "mosh", "nc", "ncat", "netcat", "socat",
         "telnet", "ftp", "lftp", "rclone", "ngrok", "cloudflared"]
assert all(RULES[f"{t} *"]["action"] == "deny" for t in TOOLS)


def spellings(t):
    """Ways to write the command name t, each of which bash resolves to t (checked below)."""
    return {
        "plain": t,
        "single": f"'{t}'",
        "double": f'"{t}"',
        "backslash_first": "\\" + t,
        "backslash_inner": t[0] + "\\" + t[1:],
        "split_quotes": f"'{t[0]}'{t[1:]}",
        "quoted_last": f'{t[:-1]}"{t[-1]}"',
        "empty_prefix": "''" + t,
        "empty_suffix": t + '""',
        "ansi_c": f"$'{t}'",
        "ansi_hex": f"$'\\x{ord(t[0]):02x}'{t[1:]}",
        "ansi_octal": f"$'\\{ord(t[0]):03o}'{t[1:]}",
        "ansi_unicode": f"$'\\u{ord(t[0]):04x}'{t[1:]}",
        "locale": f'$"{t}"',
        "continued": t[0] + "\\\n" + t[1:],
        "abs_path": f"/usr/bin/{t}",
        "quoted_path": f"'/opt/tools/bin/'{t}",
        "mixed": f"\"{t[0]}\"'{t[1]}'{t[2:]}",
    }


SPELLING_NAMES = list(spellings("ssh"))

# Where the command sits: each runs it, as bash reads the program.
CONTEXTS = [
    ("alone", "{c}"),
    ("after_semicolon", "ls; {c}"),
    ("after_and", "make && {c}"),
    ("after_or", "false || {c}"),
    ("piped_into", "cat f | {c}"),
    ("piped_from", "{c} | tee log"),
    ("subshell", "( {c} )"),
    ("group", "{ {c}; }"),
    ("if_then", "if true; then {c}; fi"),
    ("if_condition", "if {c}; then :; fi"),
    ("negated", "! {c}"),
    ("loop_body", "while :; do {c}; done"),
    ("for_body", "for i in 1 2; do {c}; done"),
    ("case_arm", "case x in x) {c};; esac"),
    ("substitution", "echo $({c})"),
    ("quoted_substitution", 'echo "$({c})"'),
    ("backticks", "echo `{c}`"),
    ("process_substitution", "diff <({c}) b"),
    ("assignment", "X=1 Y=2 {c}"),
    ("second_line", "cd /tmp\n{c}"),
    ("after_heredoc", "cat <<E\nhello\nE\n{c}"),
    ("after_comment", "ls # not this\n{c}"),
    ("background", "{c} &"),
    ("redirected", "{c} >out 2>&1"),
    ("redirect_first", "2>/dev/null {c}"),
    ("time", "time -p {c}"),
    ("coproc", "coproc {c}"),
    ("in_assignment", "v=$({c})"),
]

WRAPPERS = [
    "sudo", "sudo -u root", "sudo -E --", "sudo --user=root -H", "doas", "doas -u root",
    "env", "env -i A=1", "env -u X", "env -C /tmp", "xargs", "xargs -n 1", "xargs -I {}", "xargs -0 -P 4",
    "nohup", "time -o t.log", "timeout 5", "timeout -s KILL 5", "timeout --kill-after=2 5", "nice", "nice -n 10",
    "setsid", "stdbuf -oL", "stdbuf -o L", "flock /tmp/l", "flock -w 3 /tmp/l", "caffeinate -i", "caffeinate -t 5",
    "watch", "watch -n 2", "command", "command -p", "command --", "exec", "exec -a name", "pixi run",
    "pixi run -e dev", "pixi exec", "pixi exec -s openssh", "pixi x", "uv run", "uv run --with x",
    "uv run -p 3.12 --", "uvx", "uvx --from x", "pipx run", "pipx run --spec x", "parallel",
    "sudo -u root env A=1 timeout 5", "env nohup nice", "timeout 5 nohup", "exec env", "command exec",
]

# The command as a shell's or eval's payload.
PAYLOADS = [
    ("bash_c", lambda c: f"bash -c {sq(c)}"),
    ("sh_c", lambda c: f"sh -c {sq(c)}"),
    ("bash_lc", lambda c: f"bash -lc {sq(c)}"),
    ("bash_option_c", lambda c: f"bash -o pipefail -c {sq(c)}"),
    ("zsh_c_dq", lambda c: f"zsh -c {dq(c)}"),
    ("dash_ec", lambda c: f"/bin/dash -ec {sq(c)}"),
    ("eval_quoted", lambda c: f"eval {sq(c)}"),
    ("eval_dq", lambda c: f"eval {dq(c)}"),
    ("eval_words", lambda c: f"eval {c}"),
    ("sudo_bash_c", lambda c: f"sudo bash -c {sq(c)}"),
    ("bash_c_sudo", lambda c: f"bash -c {sq('sudo ' + c)}"),
    ("timeout_bash_c", lambda c: f"timeout 5 bash -c {sq(c)}"),
    ("eval_env", lambda c: f"eval {sq('env ' + c)}"),
    ("bash_c_in_substitution", lambda c: f"echo $(bash -c {sq(c)})"),
    ("bash_c_bash_c", lambda c: f"bash -c {sq('bash -c ' + sq(c))}"),
    ("xargs_sudo", lambda c: f"xargs sudo {c}"),
]


def deny_cases():
    """(name, program, tool, the spelled simple command bash must resolve to tool, note)."""
    cases = []
    n = 0

    def add(name, program, tool, spelled, note=""):
        nonlocal n
        if program not in EXISTING:
            cases.append((name, program, tool, spelled, note))
        n += 1

    # Every spelling, alone, for three tools each.
    for i, s in enumerate(SPELLING_NAMES):
        for k in range(3):
            tool = TOOLS[(i * 3 + k) % len(TOOLS)]
            spelled = f"{spellings(tool)[s]} host"
            add(f"{s}_{slug(tool)}", spelled, tool, spelled)
    # Every context, wrapper and payload, with two spellings and two tools each.
    combos = [(f"in_{name}", lambda c, t=t: t.replace("{c}", c)) for name, t in CONTEXTS[1:]]
    combos += [(f"behind_{slug(w)}", lambda c, w=w: f"{w} {c}") for w in WRAPPERS]
    combos += [(f"payload_{name}", f) for name, f in PAYLOADS]
    for j, (name, build) in enumerate(combos):
        for k in range(2):
            tool = TOOLS[(j * 2 + k + 5) % len(TOOLS)]
            s = SPELLING_NAMES[(j * 5 + k * 7) % len(SPELLING_NAMES)]
            spelled = f"{spellings(tool)[s]} host"
            add(f"{name}_{s}_{slug(tool)}", build(spelled), tool, spelled)
    # Expansions, wrappers and keywords bash or the wrapper reads past.
    past = [
        # brace expansion: {ssh,host} is `ssh host`, ss{h,} is `ssh ss`, {,} is no word at all
        ("brace_expansion", "{ssh,host}", "ssh", "{ssh,host}"),
        ("brace_suffix", "ss{h,} host", "ssh", "ss{h,} host"),
        ("brace_sequence", "{s..s}sh host", "ssh", "{s..s}sh host"),
        ("brace_empty_first", "{,} nc host 1", "nc", "{,} nc host 1"),
        ("brace_nested", "{s{c,}p,x} a b:", "scp", "{s{c,}p,x} a b:"),
        ("brace_in_path", "/usr/bin/{scp,cp} a b:", "scp", "/usr/bin/{scp,cp} a b:"),
        ("ansi_c_long_unicode", "$'\\U00000073'sh host", "ssh", "$'\\U00000073'sh host"),
        ("ansi_c_control_then_nul", "$'ssh\\0x' host", "ssh", "$'ssh\\0x' host"),
        # sudo -iu root is -i -u root; -uroot is -u root
        ("sudo_combined_flags", "sudo -iu root scp a b:", "scp", None),
        ("sudo_attached_value", "sudo -Euroot sftp host", "sftp", None),
        # env -S splits its string and runs it, `\_` a separator outside quotes
        ("env_split_string_attached", "env -S'rclone copy a r:b'", "rclone", None),
        ("env_split_string_long", "env --split-string='-i A=1 ssh host'", "ssh", None),
        ("env_split_string_escape", "env -S'ssh\\_host'", "ssh", None),
        # bash -c reads options up to its payload: `-c --`, `-c -x`, `+c`
        ("bash_c_after_dashdash", "bash -c -- 'nc host 22'", "nc", None),
        ("bash_c_then_option", "bash -c -x 'nc host 22'", "nc", None),
        ("bash_plus_c", "bash +c 'ssh host'", "ssh", None),
        ("bash_co_pipefail", "bash -co pipefail 'ssh host'", "ssh", None),
        ("builtin_exec", "builtin exec sftp host", "sftp", None),
        ("builtin_eval", "builtin eval 'ssh host'", "ssh", None),
        ("builtin_command", "builtin command telnet host", "telnet", None),
        # a function's body runs when it is called
        ("function_keyword_body", "function f { ssh host; }; f", "ssh", None),
        ("function_keyword_parens", "function f() { scp a b:; }; f", "scp", None),
        ("coproc_named", "coproc c { ssh host; }", "ssh", None),
        # substitutions inside ${...}, $(( )) and array words run
        ("parameter_default_substitution", "echo ${x:-$(ssh host)}", "ssh", None),
        ("parameter_quoted_single_quotes", "echo \"${x:-'$(ssh host)'}\"", "ssh", None),
        ("parameter_nested", "echo ${x:-${y:-`nc h 1`}}", "nc", None),
        ("arithmetic_substitution", "echo $(( $(ssh host) + 1 ))", "ssh", None),
        ("arithmetic_quoted", "echo \"$(( $(nc h 1) ))\"", "nc", None),
        ("subshell_in_substitution", "echo $((ssh host) )", "ssh", None),
        ("array_substitution", "a=($(ssh host))", "ssh", None),
        ("array_append_backticks", "a+=(x `scp a b:`)", "scp", None),
        # a case pattern's ) closes nothing
        ("case_in_substitution", "echo $(case x in x) ssh host;; esac)", "ssh", None),
        ("case_paren_pattern_in_substitution", "echo $(case x in (x) ssh host;; esac)", "ssh", None),
        ("case_last_arm_in_substitution", "echo $(case x in y) :;; x) ssh host\nesac)", "ssh", None),
        ("comment_in_substitution", "echo $(: # )\nssh host)", "ssh", None),
        # flock FILE -c runs its string in a shell
        ("flock_command_option", "flock /tmp/l -c 'scp a b:'", "scp", None),
        ("flock_wait_command_option", "flock --wait 3 /tmp/l --command 'nc h 1'", "nc", None),
        # watch and parallel run their command in a shell
        ("watch_shell_string", "watch -n 5 'ls; ssh host'", "ssh", None),
        ("parallel_shell_string", "parallel 'cd x; nc {} 1' ::: h", "nc", None),
    ]
    for name, program, tool, spelled in past:
        add(name, program, tool, spelled)
    return cases


# Commands that name a tool only as an argument, as data or in a comment.
# (name, template with {t}, whether it is one inert simple command bash can split).
MENTIONS = [
    ("echo", "echo {t}", True),
    ("echo_host", "echo {t} host", True),
    ("man", "man {t}", True),
    ("which", "which {t}", True),
    ("type", "type -a {t}", True),
    ("command_v", "command -v {t}", True),
    ("command_V", "command -V {t}", True),
    ("sudo_list", "sudo -l {t}", True),
    ("grep", "grep -rn {t} .", True),
    ("printf", "printf '%s\\n' {t}", True),
    ("single_quoted", "echo '{t} host'", True),
    ("double_quoted", 'echo "{t} host"', True),
    ("ansi_c_data", "echo $'{t} host'", True),
    ("commit_message", "git commit -m '{t} host'", True),
    ("quoted_substitution_text", "echo '$({t} host)'", True),
    ("ansi_c_backticks_text", "echo $'`{t} host`'", True),
    ("escaped_backticks", "echo \\`{t} host\\`", True),
    ("escaped_dollar_quoted", 'echo "\\$({t} host)"', True),
    ("directory", "ls -la {t}/", True),
    ("config_file", "cat ~/.config/{t}.conf", False),
    ("assignment_value", "X={t}", True),
    ("assignment_quoted", "X='{t} host' ls", True),
    ("export", "export X={t}", True),
    ("alias", "alias s='{t} host'", True),
    ("lookalike_suffix", "{t}x host", True),
    ("lookalike_prefix", "x{t} host", True),
    ("lookalike_extension", "./{t}.py host", True),
    ("pixi_add", "pixi add {t}", True),
    ("uv_pip", "uv pip install {t}", True),
    ("pipx_install", "pipx install {t}", True),
    ("xargs_grep", "xargs grep -l {t}", True),
    ("env_grep", "env grep -w {t} f", True),
    ("timeout_grep", "timeout 5 grep {t} f", True),
    ("nice_grep", "nice -n 5 grep {t} f", True),
    ("bash_script", "bash run.sh {t} host", True),
    ("bash_c_echo", "bash -c 'echo {t} host'", True),
    ("bash_c_argument", "bash -c 'echo \"$0\"' {t}", True),
    ("eval_echo", "eval echo {t} host", True),
    ("pixi_run_grep", "pixi run grep {t} f", True),
    ("heredoc_body", "cat <<E\n{t} host\nE", False),
    ("quoted_heredoc_substitution", "cat <<'E'\n$({t} host)\nE", False),
    ("tab_heredoc_body", "cat <<-E\n\t{t} host\n\tE", False),
    ("comment", "# {t} host", False),
    ("trailing_comment", "ls # {t} host", False),
    ("piped_data", "echo {t} | wc -c", False),
    ("case_word", "case {t} in *) :;; esac", False),
    ("redirect_target", "echo hi > {t}", False),
    ("here_string", "cat <<< '{t} host'", False),
]
# Forms whose {t} must be a shell identifier.
IDENTIFIER_MENTIONS = [
    ("for_variable", "for {t} in a b; do :; done"),
    ("assignment_name", "{t}=1 ls"),
    ("function_keyword_name", "function {t} {{ :; }}"),
]
# Forms that name a tool where bash runs nothing, each with that tool.
MENTION_EXTRA = [
    ("array_assignment", "a=(ssh host)", "ssh"),             # an array's words are data
    ("array_append", "hosts+=(sftp x)", "sftp"),
    ("array_quoted_substitution", "a=('$(ssh host)')", "ssh"),
    ("declare_array", "declare -a a=(scp x)", "scp"),
    ("parameter_single_quotes", "echo ${x:-'$(ssh host)'}", "ssh"),  # quoted outside double quotes
    ("arithmetic_variable", "echo $(( ssh + 1 ))", "ssh"),
    ("brace_data", "echo {ssh,scp} host", "ssh"),
    ("brace_sequence_data", "echo {1..100} nc", "nc"),
    ("case_word_not_keyword", "echo $(echo case x in x) ssh host", "ssh"),
    ("flock_grep_count", "flock /tmp/l grep -c ssh f", "ssh"),
    ("watch_exec_argument", "watch -x grep ssh f", "ssh"),
    ("parallel_argument", "parallel grep ssh ::: a b", "ssh"),
    ("env_split_data", "env -S'grep -w' ssh f", "ssh"),
    ("bash_c_argument_after_payload", "bash -c 'echo $1' x ssh", "ssh"),
    ("coproc_simple_argument", "coproc grep ssh f", "ssh"),
    ("function_named_tool", "function nc() { :; }", "nc"),
]


def mention_cases():
    """(name, program, tool, an inert simple command bash splits or None, note)."""
    cases = []
    for i, (name, template, simple) in enumerate(MENTIONS):
        for k in range(2):
            tool = TOOLS[(i * 2 + k) % len(TOOLS)]
            program = template.replace("{t}", tool)
            if program not in EXISTING:
                cases.append((f"{name}_{slug(tool)}", program, tool, program if simple else None, ""))
    identifiers = [t for t in TOOLS if re.fullmatch(r"[a-z_]+", t)]
    for i, (name, template) in enumerate(IDENTIFIER_MENTIONS):
        for k in range(2):
            tool = identifiers[(i * 2 + k) % len(identifiers)]
            program = template.replace("{t}", tool).replace("{{", "{").replace("}}", "}")
            cases.append((f"{name}_{tool}", program, tool, None, ""))
    for name, program, tool in MENTION_EXTRA:
        cases.append((name, program, tool, None, ""))
    return cases


# Commands too deep or too wide to read: refused whatever they run.
REFUSE = [
    ("deep_wrappers", "nice " * 20 + "ssh host"),
    ("deep_substitutions", "echo " + "$(echo " * 20 + "x" + ")" * 20),
    ("deep_payloads", "eval " * 20 + "ls"),
    ("wide_sequence", "echo {1..5000}"),
    ("wide_product", "echo {a..z}{a..z}{a..z}"),
    ("wide_hides_a_command", "env {X{1..2000}=1,ssh,host}"),
]


WORDS = word_cases()
ESCAPES = escape_cases()
STRUCTURE = structure_cases()
DENY = deny_cases()
MENTION = mention_cases()


# bash's view, read from a NUL-separated list of (kind, source) pairs. `words`
# splits inert words with set --; `parse` defines a function with the program
# as its body, which parses it without running it.
BASH_READER = r"""
set -o noglob
while IFS= read -r -d '' kind && IFS= read -r -d '' src; do
  if [[ $kind == words ]]; then
    set --
    if eval "set -- $src" 2>/dev/null; then
      printf 'ok\0%s\0' "$#"
      (( $# )) && printf '%s\0' "$@"
    else
      printf 'error\0'
    fi
  else
    unset -f __parse_check
    if eval "__parse_check() { :
$src
}" 2>/dev/null; then printf 'ok\0'; else printf 'error\0'; fi
  fi
done < "$1"
"""

NODE_READER = r"""
const [guardPath, casesPath] = process.argv.slice(1);
const { readFileSync } = await import("node:fs");
const guard = await import(guardPath);
const { commands, denials, rules } = JSON.parse(readFileSync(casesPath, "utf8"));
const out = { commands: {}, denials: {} };
for (const source of commands) out.commands[source] = guard.commandsOf(source);
for (const source of denials) out.denials[source] = guard.deniedSpelling(source, rules) ?? null;
console.log(JSON.stringify(out));
"""


@functools.lru_cache(maxsize=None)
def results():
    """bash's and the guard's answers for every case; a str naming what is missing instead."""
    shell, binary = modern_bash(), node()
    if not shell:
        return "needs bash 4.4 or later"
    if not binary:
        return "needs node (the bundled .node/bin/node)"
    words = [s for s, _ in WORDS + ESCAPES]
    words += [s for _, _, sa, sb, _ in STRUCTURE for s in (sa, sb)]
    words += [spelled for _, _, _, spelled, _ in DENY if spelled]
    words += [simple for _, _, _, simple, _ in MENTION if simple]
    programs = [p for _, p, _, _, _ in STRUCTURE] + [p for _, p, _, _, _ in DENY + MENTION] + [p for _, p in REFUSE]
    pairs = [("words", s) for s in dict.fromkeys(words)] + [("parse", p) for p in dict.fromkeys(programs)]
    base = Path(tempfile.mkdtemp())
    try:
        (base / "reader.sh").write_text(BASH_READER)
        (base / "cases").write_bytes(b"".join(f"{k}\0{s}\0".encode() for k, s in pairs))
        run = subprocess.run([shell, str(base / "reader.sh"), str(base / "cases")], cwd=base,
                             capture_output=True, timeout=120,
                             env={"PATH": "/nonexistent", "LC_ALL": "C", "HOME": str(base)})
        if run.returncode != 0:
            raise AssertionError(f"the bash reader failed:\n{run.stderr.decode()}")
        fields = iter(run.stdout.decode().split("\0"))
        bash = {"words": {}, "parse": {}}
        for kind, source in pairs:
            status = next(fields)
            if kind == "parse":
                bash["parse"][source] = status == "ok"
            elif status == "ok":
                bash["words"][source] = [next(fields) for _ in range(int(next(fields)))]
            else:
                bash["words"][source] = None

        commands = list(dict.fromkeys(words + [p for _, p, _, _, _ in STRUCTURE]))
        denials = list(dict.fromkeys([p for _, p, _, _, _ in DENY + MENTION] + [p for _, p in REFUSE]))
        (base / "cases.json").write_text(json.dumps({"commands": commands, "denials": denials, "rules": RULES}))
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", NODE_READER,
                              str(GUARD), str(base / "cases.json")],
                             cwd=base, capture_output=True, text=True, timeout=120, env={"PATH": "/nonexistent"})
        if run.returncode != 0:
            raise AssertionError(f"the guard runner failed:\n{run.stderr}")
        guard = json.loads(run.stdout)
        return {"bash": bash, "guard": guard}
    finally:
        shutil.rmtree(base, ignore_errors=True)


class GuardVsBash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = results()
        if isinstance(out, str):
            raise unittest.SkipTest(out)
        cls.bash, cls.guard = out["bash"], out["guard"]

    def bash_words(self, source):
        words = self.bash["words"][source]
        self.assertIsNotNone(words, f"bash cannot split {source!r}: the case itself is wrong")
        return words

    def parses(self, program):
        self.assertTrue(self.bash["parse"][program], f"bash does not parse {program!r}: the case itself is wrong")


    def check_words(self, source):
        words = self.bash_words(source)
        self.assertEqual([words] if words else [], self.guard["commands"][source], repr(source))


class WordTests(GuardVsBash):
    """A generated simple command splits into bash's words, quotes and escapes removed."""


class EscapeTests(GuardVsBash):
    """Each escape of $'...', "..." and $"...", and brace expansion, read as bash reads it."""


class StructureTests(GuardVsBash):
    """Generated commands joined into a program come out as the same commands, in the guard's order."""

    def check_structure(self, program, sa, sb, expect):
        self.parses(program)
        want = expect(self.bash_words(sa), self.bash_words(sb), sa, sb)
        self.assertEqual(want, self.guard["commands"][program], repr(program))


class DeniedSpellingTests(GuardVsBash):
    """A spelling bash runs as a denied tool is denied with that tool's own rule."""

    def check_denied(self, program, tool, spelled):
        self.parses(program)
        if spelled is not None:
            # bash itself says the spelling names the tool.
            words = self.bash_words(spelled)
            self.assertEqual(tool, basename(words[0]), f"{spelled!r} is not {tool} to bash: the case is wrong")
        got = self.guard["denials"][program]
        self.assertIsNotNone(got, f"{program!r} runs {tool} but is not denied")
        self.assertEqual(f"{tool} *", got["pattern"], got)
        self.assertEqual(RULES[f"{tool} *"]["reason"], got["reason"])
        self.assertEqual(tool, got["spelling"].split(" ")[0], got)


class MentionTests(GuardVsBash):
    """A command that only names a denied tool as an argument, data or a comment is not denied."""

    def check_not_denied(self, program, tool, simple):
        self.parses(program)
        if simple is not None:
            words = self.bash_words(simple)
            self.assertNotEqual(tool, basename(words[0]), f"{simple!r} runs {tool}: the case is wrong")
        self.assertIsNone(self.guard["denials"][program], repr(program))


class RefusalTests(GuardVsBash):
    """A command nested too deeply, or brace-expanding too wide, to read is refused, not passed."""

    def check_refused(self, program):
        self.parses(program)
        got = self.guard["denials"][program]
        self.assertIsNotNone(got, repr(program))
        self.assertEqual("command-guard", got["pattern"])
        self.assertRegex(got["reason"], "too deeply|more than 1024 words")


def add(cls, name, method, note=""):
    if note.startswith("BUG:"):
        method = unittest.expectedFailure(method)
    method.__doc__ = note or None
    assert not hasattr(cls, name), name
    setattr(cls, name, method)


def build():
    for i, (source, note) in enumerate(WORDS):
        add(WordTests, f"test_{i:03d}_{slug(source)}", lambda self, s=source: self.check_words(s), note)
    for i, (source, note) in enumerate(ESCAPES):
        add(EscapeTests, f"test_{i:03d}_{slug(source)}", lambda self, s=source: self.check_words(s), note)
    for i, (name, program, sa, sb, expect) in enumerate(STRUCTURE):
        add(StructureTests, f"test_{i:03d}_{name}",
            lambda self, p=program, a=sa, b=sb, e=expect: self.check_structure(p, a, b, e))
    for i, (name, program, tool, spelled, note) in enumerate(DENY):
        add(DeniedSpellingTests, f"test_{i:03d}_{slug(name)}",
            lambda self, p=program, t=tool, s=spelled: self.check_denied(p, t, s), note)
    for i, (name, program) in enumerate(REFUSE):
        add(RefusalTests, f"test_{i:03d}_{name}", lambda self, p=program: self.check_refused(p))
    for i, (name, program, tool, simple, note) in enumerate(MENTION):
        add(MentionTests, f"test_{i:03d}_{slug(name)}",
            lambda self, p=program, t=tool, s=simple: self.check_not_denied(p, t, s), note)


build()


if __name__ == "__main__":
    unittest.main()
