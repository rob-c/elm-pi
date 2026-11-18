"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is submitted and nothing the session wrote is run: job.sh and
submit.sh are read. What qsub would be given is the `#$` lines of job.sh,
wherever they are, with any options on the qsub command line of
submit.sh after them. Equivalent spellings are the same answer:

    -l h_vmem=4G / 4g / 4096M / 4000M, in one -l with h_rt or its own
    -l h_rt=04:00:00 / 4:0:0 / 14400
    -t 1-30 / 1-30:1, with -tc 5 on its own line, the same line or the command line
    -j y with -o logs/, or -o and -e both in logs/ (a folder or a file name in it)
    -cwd, or -wd with the folder
    an array bound taken from `wc -l < inputs.txt` on the qsub command line

What the site fixes is in oracle/make_environment.py: the parallel
environment `sharedmem`, the project `hadron-th`, no queue to be named, and
h_vmem per slot.
"""
import re
import shlex
from pathlib import Path

N_INPUTS = 30
SLOTS = 6
MEMORY_GB = 24
SECONDS = 4 * 3600
AT_ONCE = 5
PARALLEL_ENVIRONMENT = "sharedmem"
PROJECT = "hadron-th"
PROGRAM = "fit_bands.py"


# --- reading a shell script ----------------------------------------------------------

def text_of(name):
    path = Path(name)
    assert path.is_file(), "%s was not written" % name
    return path.read_text(encoding="utf-8", errors="replace")


def uncommented(line):
    """A shell line without its trailing comment (a # that starts a word)."""
    return re.sub(r"(^|\s)#.*$", "", line)


def flattened(text):
    """A shell script with its continuation lines joined and its comments removed."""
    return "\n".join(uncommented(line) for line in re.sub(r"\\\n", " ", text).splitlines())


def expanded(text):
    """The script with what a reader would do in their head done: a count of the lines of
    inputs.txt replaced by the number, plain NAME=value assignments substituted where $NAME or
    ${NAME} is used, and $(( )) of numbers worked out."""
    def count(match):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        if "inputs.txt" in inner and re.search(r"wc\s+-l|grep\s+-c|END\s*\{\s*print\s+NR", inner):
            return str(N_INPUTS)
        return match.group(0)

    text = re.sub(r"\$\(([^()]*)\)|`([^`]*)`", count, text)
    assignment = r"^[ \t]*(?:export[ \t]+|readonly[ \t]+|local[ \t]+)?([A-Za-z_]\w*)=(\"[^\"\n]*\"|'[^'\n]*'|[^\s;&|()]*)"
    for _ in range(4):
        values = {}
        for name, value in re.findall(assignment, text, re.M):
            value = value.strip("\"'")
            if re.fullmatch(r"[\w./%:,=+\-\[\]${}@]*", value) and not value.endswith("$"):
                values[name] = value

        def sum_of(match):
            inner = re.sub(r"[A-Za-z_]\w*", lambda m: values[m.group(0)] if values.get(m.group(0), "").isdigit() else m.group(0),
                           match.group(1))
            if re.fullmatch(r"\s*\d[\d\s+\-*]*", inner) and "**" not in inner:
                try:
                    return str(int(eval(inner, {"__builtins__": {}})))
                except SyntaxError:
                    pass
            return match.group(0)

        text = re.sub(r"\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)",
                      lambda m: values.get(m.group(1) or m.group(2), m.group(0)), text)
        text = re.sub(r"\$\(\(([^()]*)\)\)", sum_of, text)
    return text


def script_parts(text, prefix):
    """(directives before the first command, directives after it, the commands)."""
    head, late, body = [], [], []
    for line in re.sub(r"\\\n", " ", text).splitlines():
        stripped = line.strip()
        match = re.match(prefix, stripped)
        if match:
            (late if body else head).append(stripped[match.end():])
        elif stripped and not stripped.startswith("#"):
            body.append(uncommented(line))
    return head, late, body


def words(line):
    try:
        return shlex.split(line, comments=True)
    except ValueError:
        return line.split()


def runs_of(text, command, script):
    """[(where in flattened(text), the words after the command to the end of it)] for each time a shell
    script runs `command`: the lines that name the script first, so `command -v sbatch` is not taken for the submission."""
    found, offset = [], 0
    for line in flattened(text).splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        try:
            tokens = list(lexer)
        except ValueError:
            tokens = line.split()
        for index, token in enumerate(tokens):
            if token == command or token.endswith("/" + command):
                rest = []
                for word in tokens[index + 1:]:
                    if re.fullmatch(r"[();<>|&]+", word):
                        break
                    rest.append(word)
                at = re.search(r"(^|[\s;&|(/])%s(\s|$)" % re.escape(command), line)
                found.append((script not in line, offset + (at.start() if at else 0), rest))
                break
        offset += len(line) + 1
    return [(where, rest) for _, where, rest in sorted(found, key=lambda item: item[0])]


def command_words(text, command, script="job.sh"):
    """The words after `command` where a shell script runs it on the script; None if it never does."""
    found = runs_of(text, command, script)
    return found[0][1] if found else None


def made_before(text, command, script="job.sh", folder="logs"):
    """Is the folder made (mkdir, install -d) earlier in the script than the command is run?"""
    found = runs_of(text, command, script)
    made = re.search(r"\b(mkdir|install\s+-d)\b[^\n;&|]*\b%s\b" % re.escape(folder), flattened(text))
    return bool(found and made and made.start() < found[0][0])

def dash_options(lines):
    """{option: [the arguments of each time it is given]} for options of the form `-name arg ...`."""
    options = {}
    for tokens in lines:
        current = None
        for token in tokens:
            if re.match(r"-[A-Za-z]", token):
                current = token[1:]
                options.setdefault(current, []).append([])
            elif current is not None:
                options[current][-1].append(token)
    return options


def given(options, name):
    """The first argument of the last time an option is given; None if it is not given, "" if it has no argument."""
    if name not in options:
        return None
    return options[name][-1][0] if options[name][-1] else ""


def resources(options, name="l"):
    """{resource: value} over every `-l a=1,b=2`."""
    found = {}
    for arguments in options.get(name, []):
        for item in (arguments[0] if arguments else "").split(","):
            key, _, value = item.partition("=")
            if key.strip():
                found[key.strip()] = value.strip()
    return found


def index_range(spec):
    """(the set of indices, the cap after % or None) of n[-m[:step]][%cap]."""
    spec, _, cap = str(spec).strip().partition("%")
    indices = set()
    for part in spec.split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+)(?::(\d+))?)?", part.strip())
        assert match, "not an index range: %r" % spec
        first = int(match.group(1))
        last = int(match.group(2) or first)
        indices.update(range(first, last + 1, int(match.group(3) or 1)))
    return indices, int(cap) if cap.strip().isdigit() else None


def clock_seconds(value):
    """[[hours:]minutes:]seconds."""
    value = str(value).strip()
    assert re.fullmatch(r"\d+(:\d+){0,2}", value), "not a time: %r" % value
    total = 0
    for part in value.split(":"):
        total = total * 60 + int(part)
    return total

# --- Grid Engine ---------------------------------------------------------------------

def size_bytes(value):
    """Grid Engine's memory sizes: k m g are powers of 1000, K M G of 1024; no letter is bytes."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmMgG]?)", str(value).strip())
    assert match, "not a Grid Engine memory size: %r" % value
    scale = {"": 1, "k": 1e3, "K": 2 ** 10, "m": 1e6, "M": 2 ** 20, "g": 1e9, "G": 2 ** 30}[match.group(2)]
    return float(match.group(1)) * scale


def job():
    """(job.sh, the options qsub would act on, the `#$` lines after a command, the commands, submit.sh)."""
    text = text_of("job.sh")
    head, late, body = script_parts(text, r"#\$(\s+|(?=-))")
    submit = expanded(Path("submit.sh").read_text(encoding="utf-8", errors="replace")) if Path("submit.sh").is_file() else ""
    # Grid Engine reads `#$` lines "from top to bottom of the script file" (qsub(1)), so one after a
    # command still counts: the first run with the skill put strict mode above them and was failed for it.
    options = dash_options([words(line) for line in head + late] + [command_words(submit, "qsub") or []])
    return text, options, late, expanded("\n".join(body)), submit


def slots(options):
    environment = options.get("pe", [[]])[-1]
    count = environment[1] if len(environment) > 1 else ""
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", count)
    return int(match.group(1)) if match and match.group(2) in (None, match.group(1)) else None


def in_logs(path):
    return path is not None and re.match(r"(\./|\S*/)?logs(/|$)", path) is not None


# --- the tests -----------------------------------------------------------------------

def test_job_sh_is_a_grid_engine_script():
    text, options, late, _, _ = job()
    assert re.search(r"^#\$\s*-", text, re.M), "job.sh has no #$ line: other schedulers' directives are comments to qsub here"


def test_project_is_the_one_the_guide_gives_and_no_queue_is_named():
    _, options, _, _, _ = job()
    assert given(options, "P") == PROJECT
    assert "q" not in options, "the guide: do not name a queue; the submission check rejects a job that does"


def test_six_slots_in_the_sites_single_host_parallel_environment():
    _, options, _, _, _ = job()
    assert "pe" in options, "without -pe the job has one slot"
    assert options["pe"][-1][:1] == [PARALLEL_ENVIRONMENT], "the parallel environment is the site's: %s" % options["pe"][-1][:1]
    assert slots(options) == SLOTS


def test_memory_per_slot_times_slots_is_24_gigabytes():
    _, options, _, _, _ = job()
    requested = resources(options)
    assert "h_vmem" in requested, "no h_vmem: the default is 1G per slot"
    total = size_bytes(requested["h_vmem"]) * (slots(options) or 1)
    assert 0.99 * MEMORY_GB * 1e9 <= total <= 1.01 * MEMORY_GB * 2 ** 30, \
        "h_vmem is per slot: %.1f GB for the job, not %d" % (total / 1e9, MEMORY_GB)


def test_time_limit_is_four_hours():
    _, options, _, _, _ = job()
    requested = resources(options)
    assert "h_rt" in requested, "no h_rt: the job is rejected"
    assert clock_seconds(requested["h_rt"]) == SECONDS


def test_an_array_over_the_30_inputs_with_five_at_once():
    _, options, _, _, _ = job()
    assert given(options, "t"), "no array (-t)"
    indices, _ = index_range(given(options, "t"))
    assert indices == set(range(1, N_INPUTS + 1)), "the array is not one task per line of inputs.txt"
    assert given(options, "tc") == str(AT_ONCE), "the array is not held to %d running tasks (-tc)" % AT_ONCE


def test_each_task_runs_the_program_on_its_own_line_of_inputs():
    _, _, _, body, _ = job()
    assert "SGE_TASK_ID" in body, "the task's index is $SGE_TASK_ID"
    assert "inputs.txt" in body
    assert PROGRAM in body


def test_thread_count_is_the_slots_the_job_was_given():
    _, _, _, body, _ = job()
    settings = re.findall(r"\bOMP_NUM_THREADS:?=(\S+)", body)
    assert settings, "OMP_NUM_THREADS is not set: the program would start a thread for every core of the node"
    for value in settings:
        value = value.strip("\"';")
        assert value == str(SLOTS) or "NSLOTS" in value, value


def test_the_job_starts_in_the_folder_it_was_submitted_from():
    _, options, _, _, _ = job()
    # Without -cwd a job starts in the home directory: inputs.txt is not there, and logs/ is taken from there too.
    assert "cwd" in options or "wd" in options, "no -cwd"


def test_logs_go_to_a_folder_that_exists_when_the_job_is_submitted():
    _, options, _, _, submit = job()
    assert in_logs(given(options, "o")), "the output is not put in logs/: %r" % given(options, "o")
    merged = (given(options, "j") or "").lower() in ("y", "yes")
    assert merged or in_logs(given(options, "e")), "the error output is not put in logs/"
    command = command_words(submit, "qsub")
    assert command is not None, "submit.sh does not run qsub"
    assert any(word.endswith("job.sh") for word in command), "submit.sh does not submit job.sh"
    # A job whose log folder is missing goes to Eqw. mkdir in job.sh is too late.
    assert Path("logs").is_dir() or made_before(submit, "qsub"), "nothing makes logs/ before qsub"
