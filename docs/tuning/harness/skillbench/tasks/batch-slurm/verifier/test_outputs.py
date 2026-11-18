"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is submitted and nothing the session wrote is run: job.sh and
submit.sh are read. What sbatch would be given is the #SBATCH lines before
the first command of job.sh, with any options on the sbatch command line of
submit.sh over them. Equivalent spellings are the same answer:

    --cpus-per-task=8 / -c 8 / -c8            --partition=x / -p x      --account=x / -A x
    --mem=16G / 16000M / 16384 / --mem-per-cpu=2G (with 8 CPUs)
    --time=02:00:00 / 2:00:00 / 120 / 0-02:00:00 / 0-2
    --array=1-48%6 / -a 1-48%6 / 0-47%6 with the index shifted in the script
    an array bound taken from `wc -l < inputs.txt` on the sbatch command line

What the site fixes is in oracle/make_environment.py: the partition, the
account, and Slurm 23.11 (srun does not inherit --cpus-per-task).
"""
import re
import shlex
from pathlib import Path

N_INPUTS = 48
CORES = 8
MEMORY_MB = (16000, 16384)      # 16 GB, decimal or binary
SECONDS = 2 * 3600
AT_ONCE = 6
PARTITION = "compute-b"
ACCOUNT = "phys-neutrino"
PROGRAM = "analyse.py"


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


# --- Slurm ---------------------------------------------------------------------------

SHORT = {"c": "cpus-per-task", "n": "ntasks", "N": "nodes", "p": "partition", "A": "account", "t": "time",
         "a": "array", "o": "output", "e": "error", "J": "job-name", "D": "chdir", "q": "qos", "d": "dependency",
         "C": "constraint", "w": "nodelist", "x": "exclude", "G": "gpus", "M": "clusters", "L": "licenses",
         "m": "distribution", "b": "begin", "i": "input", "S": "core-spec", "k": "no-kill"}
FLAGS = {"exclusive", "requeue", "no-requeue", "parsable", "wait", "hold", "overcommit", "oversubscribe",
         "test-only", "verbose", "quiet", "contiguous", "spread-job", "use-min-nodes", "help", "usage", "version"}
SHORT_FLAGS = set("HQvWsOhVu")


def slurm_options(tokens):
    options, index = {}, 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token.startswith("--") and len(token) > 2:
            key, equals, value = token[2:].partition("=")
            if not equals:
                if key in FLAGS or index >= len(tokens) or tokens[index].startswith("-"):
                    value = True
                else:
                    value = tokens[index]
                    index += 1
            options[key] = value
        elif token.startswith("-") and len(token) > 1 and token != "--":
            letter = token[1]
            if letter in SHORT_FLAGS:
                options[letter] = True
            elif len(token) > 2:
                options[SHORT.get(letter, letter)] = token[2:].lstrip("=")
            elif index < len(tokens):
                options[SHORT.get(letter, letter)] = tokens[index]
                index += 1
        else:
            break               # the script: what follows it are the script's own arguments
    return options


def megabytes(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGT]?)B?", str(value).strip(), re.I)
    assert match, "not a Slurm memory size: %r" % value
    return float(match.group(1)) * {"K": 1 / 1024, "": 1, "M": 1, "G": 1024, "T": 1024 ** 2}[match.group(2).upper()]


def seconds(value):
    """Slurm's time formats: M, M:S, H:M:S, D-H, D-H:M, D-H:M:S."""
    value = str(value).strip()
    days, dash, rest = value.rpartition("-")
    assert re.fullmatch(r"\d*", days) and re.fullmatch(r"\d+(:\d+){0,2}", rest), "not a Slurm time: %r" % value
    parts = [int(part) for part in rest.split(":")]
    if dash:
        hours, minutes, secs = (parts + [0, 0])[:3]
        return int(days) * 86400 + hours * 3600 + minutes * 60 + secs
    if len(parts) == 1:
        return parts[0] * 60
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def array(spec):
    """(the set of indices, the throttle or None) of an --array value."""
    spec, _, throttle = str(spec).strip().partition("%")
    indices = set()
    for part in spec.split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+)(?::(\d+))?)?", part.strip())
        assert match, "not an array range: %r" % spec
        first = int(match.group(1))
        last = int(match.group(2) or first)
        indices.update(range(first, last + 1, int(match.group(3) or 1)))
    return indices, int(throttle) if throttle.strip().isdigit() else None


def job():
    """(job.sh, the options sbatch would act on, #SBATCH lines it would ignore, the commands, submit.sh)."""
    text = text_of("job.sh")
    head, late, body = script_parts(text, r"#SBATCH(\s+|$)")
    options = {}
    for line in head:
        options.update(slurm_options(words(line)))
    submit = expanded(Path("submit.sh").read_text(encoding="utf-8", errors="replace")) if Path("submit.sh").is_file() else ""
    options.update(slurm_options(command_words(submit, "sbatch") or []))
    return text, options, late, expanded("\n".join(body)), submit


# --- the tests -----------------------------------------------------------------------

def test_job_sh_is_a_slurm_script_with_its_directives_before_the_first_command():
    text, options, late, _, _ = job()
    assert text.startswith("#!"), "sbatch refuses a script with no interpreter line"
    assert re.search(r"^#SBATCH\s", text, re.M), "job.sh has no #SBATCH line"
    assert not late, "sbatch ignores #SBATCH lines after the first command: %s" % late


def test_partition_and_account_are_the_ones_the_guide_gives():
    _, options, _, _, _ = job()
    assert options.get("partition") == PARTITION
    assert options.get("account") == ACCOUNT


def test_one_task_with_eight_cpus_on_one_node():
    _, options, _, body, _ = job()
    assert str(options.get("cpus-per-task")) == str(CORES), "a threaded program is one task with %d CPUs" % CORES
    assert str(options.get("ntasks", 1)) == "1", "--ntasks counts MPI ranks: this program is one"
    assert str(options.get("ntasks-per-node", 1)) == "1"
    assert str(options.get("nodes", 1)) in ("1", "1-1")
    for line in body.splitlines():
        if re.search(r"(^|[\s;&|(])srun\s", line):
            # Slurm 22.05 and later (the guide: 23.11): srun does not inherit --cpus-per-task from sbatch.
            assert re.search(r"\s(-c\s*\S|--cpus-per-task)", line) or "SRUN_CPUS_PER_TASK" in body, \
                "srun is not given the CPU count: " + line.strip()


def test_sixteen_gigabytes_for_the_job_in_slurms_own_terms():
    _, options, _, _, _ = job()
    per_node, per_cpu = options.get("mem"), options.get("mem-per-cpu")
    assert (per_node is None) != (per_cpu is None), "one of --mem (per node) and --mem-per-cpu, not both and not neither"
    cpus = int(options.get("cpus-per-task", 1)) if str(options.get("cpus-per-task", 1)).isdigit() else 1
    total = megabytes(per_node) if per_node is not None else megabytes(per_cpu) * cpus
    assert MEMORY_MB[0] <= total <= MEMORY_MB[1], "%.0f MB for the job, not 16 GB" % total


def test_time_limit_is_two_hours():
    _, options, _, _, _ = job()
    assert "time" in options, "no time limit: the site's default is 10 minutes"
    assert seconds(options["time"]) == SECONDS


def test_an_array_over_the_48_inputs_with_six_at_once():
    _, options, _, body, _ = job()
    assert "array" in options, "no job array"
    indices, throttle = array(options["array"])
    assert indices in (set(range(1, N_INPUTS + 1)), set(range(N_INPUTS))), "the array is not one task per line of inputs.txt"
    assert throttle == AT_ONCE, "the array is not held to %d running tasks" % AT_ONCE
    if 0 in indices:
        assert re.search(r"\+\s*1\b|mapfile|readarray|\[\s*\"?\$|python", body), "index 0 is not a line of inputs.txt"


def test_each_task_runs_the_program_on_its_own_line_of_inputs():
    _, _, _, body, _ = job()
    assert "SLURM_ARRAY_TASK_ID" in body, "the task's index is $SLURM_ARRAY_TASK_ID"
    assert "inputs.txt" in body
    assert PROGRAM in body


def test_thread_count_is_what_the_job_was_given():
    _, _, _, body, _ = job()
    settings = re.findall(r"\bOMP_NUM_THREADS:?=(\S+)", body)
    assert settings, "OMP_NUM_THREADS is not set: the program would start a thread for every core of the node"
    for value in settings:
        value = value.strip("\"';")
        # nproc counts the cores the job is confined to (the guide: cgroups), which is what it was given.
        assert value == str(CORES) or re.search(r"SLURM_CPUS_PER_TASK|SLURM_JOB_CPUS_PER_NODE|SLURM_CPUS_ON_NODE|nproc", value), value


def test_logs_go_to_a_folder_that_exists_when_the_job_is_submitted():
    _, options, _, _, submit = job()
    output = str(options.get("output", ""))
    assert re.match(r"(\./)?logs/.", output), "the output file is not in logs/: %r" % output
    assert re.search(r"%\d*[ajJ]", output), "every array task would write the same file: %r" % output
    if "error" in options:
        assert re.match(r"(\./)?logs/.", str(options["error"]))
    command = command_words(submit, "sbatch")
    assert command is not None, "submit.sh does not run sbatch"
    assert any(word.endswith("job.sh") for word in command), "submit.sh does not submit job.sh"
    # A job whose output folder is missing fails at once, with no log to say why. mkdir in job.sh is too late.
    assert Path("logs").is_dir() or made_before(submit, "sbatch"), "nothing makes logs/ before sbatch"
