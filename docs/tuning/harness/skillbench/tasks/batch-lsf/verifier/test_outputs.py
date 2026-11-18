"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is submitted and nothing the session wrote is run: job.sh and
submit.sh are read. What bsub would be given is the #BSUB lines of job.sh,
wherever they are, with any options on the bsub command line of
submit.sh after them. Equivalent spellings are the same answer:

    bsub < job.sh / bsub < ./job.sh / cat job.sh | bsub, with or without options before the <
    -R "span[hosts=1] rusage[mem=32GB]" in one string or two -R options, quoted or not
    mem=32GB / 32G / 32000 / 32768 / 32000MB, and the same for -M (the site's bare unit is MB)
    -W 6:00 / 06:00 / 360
    -J "name[1-24]%4" / name[1-24:1]%4
    -o / -oo, with -e / -eo or without (LSF then puts both in the -o file)
    threads from $LSB_DJOB_NUMPROC or $LSB_MAX_NUM_PROCESSORS, or the number asked for

What the site fixes is in oracle/make_environment.py: the queue `medium-x`,
the project `nustruct-25`, memory per job with both a reservation and a
limit, and bsub reading #BSUB lines only from standard input.
"""
import re
import shlex
from pathlib import Path

N_INPUTS = 24
SLOTS = 8
MEMORY_MB = (32000, 32768)      # 32 GB, decimal or binary
MINUTES = 6 * 60
AT_ONCE = 4
QUEUE = "medium-x"
PROJECT = "nustruct-25"
PROGRAM = "spectra.py"


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

# --- LSF -----------------------------------------------------------------------------

def megabytes(number, unit):
    """This site: a number without a unit is megabytes (LSF_UNIT_FOR_LIMITS=MB)."""
    scale = {"": 1, "K": 1 / 1024, "KB": 1 / 1024, "M": 1, "MB": 1, "G": 1024, "GB": 1024, "T": 1024 ** 2, "TB": 1024 ** 2}
    assert unit.upper() in scale, "not a memory unit: %r" % unit
    return float(number) * scale[unit.upper()]


def job():
    """(job.sh, the options bsub would act on, the #BSUB lines after a command, the commands, submit.sh)."""
    text = text_of("job.sh")
    head, late, body = script_parts(text, r"#BSUB(\s+|$)")
    submit = expanded(Path("submit.sh").read_text(encoding="utf-8", errors="replace")) if Path("submit.sh").is_file() else ""
    # IBM's guide: options can be "anywhere in the standard input" of bsub, so a #BSUB line after a
    # command still counts; some sites say otherwise, and a script is not failed for either reading.
    options = dash_options([words(line) for line in head + late] + [command_words(submit, "bsub") or []])
    return text, options, late, expanded("\n".join(body)), submit


def requirement(options):
    """Every -R string, as one."""
    return " ".join(" ".join(arguments) for arguments in options.get("R", []))


def in_logs(path):
    return path is not None and re.match(r"(\./|\S*/)?logs/.", path) is not None


# --- the tests -----------------------------------------------------------------------

def test_job_sh_is_an_lsf_script():
    text, options, late, _, _ = job()
    assert re.search(r"^#BSUB\s", text, re.M), "job.sh has no #BSUB line"


def test_submit_sh_gives_job_sh_to_bsub_on_standard_input():
    _, _, _, _, submit = job()
    flat = "\n".join(uncommented(line) for line in re.sub(r"\\\n", " ", submit).splitlines())
    assert re.search(r"(^|[\s;&|(/])bsub(\s|$)", flat, re.M), "submit.sh does not run bsub"
    redirected = re.search(r"\bbsub\b[^\n|;&]*<\s*[\"']?(\./|[^\s\"'<>]*/)?job\.sh", flat)
    piped = re.search(r"\bcat\s+[\"']?\S*job\.sh[\"']?\s*\|\s*bsub\b", flat)
    # `bsub job.sh` runs the script as a command: this site's bsub reads #BSUB lines only from standard input.
    assert redirected or piped, "bsub is not given job.sh on standard input, so its #BSUB lines are not read"


def test_queue_and_project_are_the_ones_the_guide_gives():
    _, options, _, _, _ = job()
    assert given(options, "q") == QUEUE
    assert given(options, "P") == PROJECT


def test_eight_slots_all_on_one_host():
    _, options, _, _, _ = job()
    assert given(options, "n") in (str(SLOTS), "%d,%d" % (SLOTS, SLOTS)), "-n is %s, not %d" % (given(options, "n"), SLOTS)
    assert re.search(r"span\[\s*hosts\s*=\s*1\s*\]", requirement(options)), \
        "nothing keeps the slots on one host (span[hosts=1]): a threaded program cannot use slots on another"


def test_32_gigabytes_both_reserved_and_set_as_the_limit():
    _, options, _, _, _ = job()
    reserved = re.search(r"rusage\[[^\]]*?\bmem\s*=\s*(\d+(?:\.\d+)?)\s*([A-Za-z]*)", requirement(options))
    assert reserved, "no memory is reserved (rusage[mem=..]): the job is scheduled as if it needed 1 GB"
    assert MEMORY_MB[0] <= megabytes(*reserved.groups()) <= MEMORY_MB[1], "reserved: %s%s" % reserved.groups()
    limit = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([A-Za-z]*)!?", given(options, "M") or "")
    assert limit, "no memory limit (-M): the queue's 2 GB applies and the job is killed at it"
    assert MEMORY_MB[0] <= megabytes(*limit.groups()) <= MEMORY_MB[1], "limit: %s%s" % limit.groups()


def test_run_limit_is_six_hours():
    _, options, _, _, _ = job()
    value = given(options, "W")
    assert value, "no run limit (-W): the default is 30 minutes"
    match = re.fullmatch(r"(?:(\d+):)?(\d+)", value)
    assert match, "-W takes [hours:]minutes: %r" % value
    assert int(match.group(1) or 0) * 60 + int(match.group(2)) == MINUTES


def test_an_array_over_the_24_inputs_with_four_at_once():
    _, options, _, _, _ = job()
    name = given(options, "J") or ""
    match = re.fullmatch(r"[^\[\]]*\[([^\]]+)\](?:%(\d+))?", name.strip())
    assert match, "the job name does not make an array: %r" % name
    indices, _ = index_range(match.group(1))
    assert indices == set(range(1, N_INPUTS + 1)), "the array is not one job per line of inputs.txt"
    assert match.group(2) == str(AT_ONCE), "the array is not held to %d running jobs" % AT_ONCE


def test_each_job_runs_the_program_on_its_own_line_of_inputs():
    _, _, _, body, _ = job()
    assert "LSB_JOBINDEX" in body, "the array index is $LSB_JOBINDEX"
    assert "inputs.txt" in body
    assert PROGRAM in body


def test_thread_count_is_the_slots_the_job_was_given():
    _, _, _, body, _ = job()
    settings = re.findall(r"\bOMP_NUM_THREADS:?=(\S+)", body)
    assert settings, "OMP_NUM_THREADS is not set: the program would start a thread for every core of the host"
    for value in settings:
        value = value.strip("\"';")
        assert value == str(SLOTS) or re.search(r"LSB_DJOB_NUMPROC|LSB_MAX_NUM_PROCESSORS", value), value


def test_logs_go_to_a_folder_that_exists():
    _, options, _, body, submit = job()
    output = given(options, "o") or given(options, "oo")
    assert output, "no -o: LSF mails the output, which on a cluster means it is lost"
    assert in_logs(output), "the output file is not in logs/: %r" % output
    error = given(options, "e") or given(options, "eo")
    assert error is None or in_logs(error), "the error file is not in logs/: %r" % error
    assert Path("logs").is_dir() or made_before(submit, "bsub") or re.search(r"\bmkdir\b[^\n;&|]*\blogs\b", body), \
        "nothing makes logs/"
