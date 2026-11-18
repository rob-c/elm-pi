"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is submitted and nothing the session wrote is run: job.sh and
submit.sh are read. What qsub would be given is the #PBS lines before the
first command of job.sh, with any options on the qsub command line of
submit.sh after them. Equivalent spellings are the same answer:

    -l select=1:ncpus=4:mem=12gb (with ompthreads or mpiprocs=1 if wanted), or the
       older job-wide -l ncpus=4 -l mem=12gb, which PBS Professional turns into that chunk
    mem=12gb / 12GB / 12G / 12288mb / 12000mb
    walltime=01:30:00 / 1:30:00 / 90:00 / 5400, on its own -l or after a comma
    -J 1-60%10, or -J 1-60 with -W max_run_subjobs=10; 0-59 with the index shifted
    -j oe with -o logs/, or -o and -e both in logs/
    --threads from $NCPUS, from $OMP_NUM_THREADS (PBS sets it), from nproc, or the number asked for

What the site fixes is in oracle/make_environment.py: PBS Professional
2022.1 (not Torque), the queue `std-d`, the account string `NUCS0421`.
"""
import re
import shlex
from pathlib import Path

N_INPUTS = 60
CORES = 4
MEMORY_GB = 12
SECONDS = 90 * 60
AT_ONCE = 10
QUEUE = "std-d"
ACCOUNT = "NUCS0421"
PROGRAM = "reco.py"


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

# --- PBS -----------------------------------------------------------------------------

def size_bytes(value):
    """PBS sizes: kb mb gb tb are powers of 1024; no suffix is bytes."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmgtp]?)[bw]?", str(value).strip(), re.I)
    assert match, "not a PBS memory size: %r" % value
    return float(match.group(1)) * 1024 ** " kmgtp".index(match.group(2).lower() or " ")


def chunks(select):
    """[(how many, {resource: value})] of a select statement."""
    found = []
    for part in select.split("+"):
        fields = part.split(":")
        count = int(fields.pop(0)) if fields and fields[0].strip().isdigit() else 1
        found.append((count, {key.strip(): value.strip() for key, _, value in (field.partition("=") for field in fields)}))
    return found


def one_chunk(requested):
    """The resources of the job's single chunk, from select or from the older job-wide form; None if it is not one chunk."""
    if "select" in requested:
        parts = chunks(requested["select"])
        return parts[0][1] if len(parts) == 1 and parts[0][0] == 1 else None
    return {key: requested[key] for key in ("ncpus", "mem") if key in requested}


def job():
    """(job.sh, the options qsub would act on, #PBS lines it would ignore, the commands, submit.sh)."""
    text = text_of("job.sh")
    head, late, body = script_parts(text, r"#PBS(\s+|$)")
    submit = expanded(Path("submit.sh").read_text(encoding="utf-8", errors="replace")) if Path("submit.sh").is_file() else ""
    options = dash_options([words(line) for line in head] + [command_words(submit, "qsub") or []])
    return text, options, late, expanded("\n".join(body)), submit


def in_logs(path):
    return path is not None and re.match(r"(\./|\S*/)?logs(/|$)", path) is not None


# --- the tests -----------------------------------------------------------------------

def test_job_sh_is_a_pbs_script_with_its_directives_before_the_first_command():
    text, options, late, _, _ = job()
    assert re.search(r"^#PBS\s", text, re.M), "job.sh has no #PBS line"
    assert not late, "qsub ignores #PBS lines after the first command: %s" % late


def test_queue_and_account_are_the_ones_the_guide_gives():
    _, options, _, _, _ = job()
    assert given(options, "q") == QUEUE
    assert given(options, "A") == ACCOUNT


def test_one_chunk_of_four_cores_in_pbs_professionals_own_terms():
    _, options, _, _, _ = job()
    requested = resources(options)
    assert not any(key in requested for key in ("nodes", "ppn", "procs", "pmem")), \
        "nodes=..:ppn=.. is Torque's resource line; this site is PBS Professional: %s" % sorted(requested)
    chunk = one_chunk(requested)
    assert chunk is not None, "a threaded program needs its cores in one chunk: %s" % requested.get("select")
    assert chunk.get("ncpus") == str(CORES), "ncpus is %s, not %d" % (chunk.get("ncpus"), CORES)


def test_twelve_gigabytes_for_the_chunk():
    _, options, _, _, _ = job()
    chunk = one_chunk(resources(options)) or {}
    assert "mem" in chunk, "no mem in the chunk: the default is 2 GB"
    assert 0.99 * MEMORY_GB * 1e9 <= size_bytes(chunk["mem"]) <= 1.01 * MEMORY_GB * 2 ** 30, chunk["mem"]


def test_walltime_is_ninety_minutes():
    _, options, _, _, _ = job()
    requested = resources(options)
    assert "walltime" in requested, "no walltime: the default is one hour"
    assert clock_seconds(requested["walltime"]) == SECONDS, "a bare number is seconds: %s" % requested["walltime"]


def test_an_array_over_the_60_inputs_with_ten_at_once():
    _, options, _, body, _ = job()
    assert given(options, "J"), "no -J array: -t is Torque's"
    indices, cap = index_range(given(options, "J"))
    assert indices in (set(range(1, N_INPUTS + 1)), set(range(N_INPUTS))), "the array is not one sub-job per line of inputs.txt"
    for arguments in options.get("W", []):
        match = re.search(r"max_run_subjobs\s*=\s*(\d+)", " ".join(arguments))
        cap = int(match.group(1)) if match else cap
    assert cap == AT_ONCE, "the array is not held to %d running sub-jobs" % AT_ONCE
    if 0 in indices:
        assert re.search(r"\+\s*1\b|mapfile|readarray|\[\s*\"?\$|python", body), "index 0 is not a line of inputs.txt"


def test_each_sub_job_runs_the_program_on_its_own_line_of_inputs():
    _, _, _, body, _ = job()
    assert "PBS_ARRAY_INDEX" in body, "the sub-job's index is $PBS_ARRAY_INDEX; $PBS_ARRAYID is Torque's and is not set here"
    assert "inputs.txt" in body
    assert PROGRAM in body


def test_thread_count_is_the_cores_the_job_was_given():
    _, _, _, body, _ = job()
    settings = re.findall(r"--threads[=\s]+(\S+)", body)
    assert settings, "reco.py is not given --threads"
    for value in settings:
        value = value.strip("\"';")
        # PBS Professional sets NCPUS and OMP_NUM_THREADS in the job; nproc counts the cores it is confined to.
        assert value == str(CORES) or re.search(r"NCPUS|OMP_NUM_THREADS|nproc", value), value


def test_the_script_changes_to_the_folder_it_was_submitted_from():
    _, _, _, body, _ = job()
    lines = body.splitlines()
    changes = [index for index, line in enumerate(lines) if re.search(r"\b(cd|pushd)\b.*PBS_O_WORKDIR", line)]
    runs = [index for index, line in enumerate(lines) if PROGRAM in line or "inputs.txt" in line]
    assert changes, "a PBS job starts in the home directory: nothing changes to $PBS_O_WORKDIR"
    assert runs and changes[0] < runs[0], "the change of directory comes after the files are used"


def test_logs_go_to_a_folder_that_exists():
    _, options, _, body, submit = job()
    assert in_logs(given(options, "o")), "the output is not put in logs/: %r" % given(options, "o")
    merged = (given(options, "j") or "") in ("oe", "eo")
    assert merged or in_logs(given(options, "e")), "the error output is not put in logs/"
    command = command_words(submit, "qsub")
    assert command is not None, "submit.sh does not run qsub"
    assert any(word.endswith("job.sh") for word in command), "submit.sh does not submit job.sh"
    # The logs are copied to logs/ when a sub-job ends: the folder has to be there by then.
    assert Path("logs").is_dir() or made_before(submit, "qsub") or re.search(r"\bmkdir\b[^\n;&|]*\blogs\b", body), \
        "nothing makes logs/"
