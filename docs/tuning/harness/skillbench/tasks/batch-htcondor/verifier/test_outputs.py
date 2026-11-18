"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is submitted and nothing the session wrote is run: job.sub, run.sh
and submit.sh are read. The queue statement of job.sub is worked out the way
condor_submit would - `from` a file or an inline list, `matching` a glob,
`in` a list - into the jobs it makes, and each job's macros are put into its
arguments, transfer list and log names. Equivalent spellings are the same
answer:

    queue infile from inputs.txt / queue f matching files run_*.dat / queue f in (run_4100.dat ...)
    request_memory = 8GB / 8 GB / 8G / 8192 / 8000 / 8192MB
    +MaxRuntime = 7200 / MY.MaxRuntime = 7200 / 2 * 3600
    should_transfer_files = YES / IF_NEEDED, or left out with a transfer list given
    the run file named to the job through arguments or environment, any macro name
    output and error named with $(Process), $(ProcId), the queue variable, or $Fn() of it
    max_materialize in job.sub, or as -append / key=value on the condor_submit command line

What the site fixes is in oracle/make_environment.py: no filesystem shared
with the execute nodes, the accounting group `group_physics.nuosc`, and the
run time in the pool's own MaxRuntime attribute, in seconds.
"""
import glob
import re
import shlex
from pathlib import Path, PurePosixPath

N_INPUTS = 40
RUNS = [4100 + 7 * i + (i * i) % 5 for i in range(N_INPUTS)]      # as in oracle/make_environment.py
INPUTS = ["run_%04d.dat" % run for run in RUNS]
CORES = 4
MEMORY_MB = (8000, 8192)        # 8 GB, decimal or binary
SECONDS = 2 * 3600
AT_ONCE = 10
ACCOUNTING_GROUP = "group_physics.nuosc"
PROGRAM = "analyse.py"
CALIBRATION = "calib.json"


# --- reading the files ---------------------------------------------------------------

def text_of(name):
    path = Path(name)
    assert path.is_file(), "%s was not written" % name
    return path.read_text(encoding="utf-8", errors="replace")


def uncommented(line):
    """A shell line without its trailing comment (a # that starts a word)."""
    return re.sub(r"(^|\s)#.*$", "", line)


def expanded(text):
    """A shell script with its plain NAME=value assignments substituted where $NAME or ${NAME} is used."""
    values = {}
    assignment = r"^[ \t]*(?:export[ \t]+|readonly[ \t]+|local[ \t]+)?([A-Za-z_]\w*)=(\"[^\"\n]*\"|'[^'\n]*'|[^\s;&|()]*)"
    for name, value in re.findall(assignment, text, re.M):
        value = value.strip("\"'")
        if re.fullmatch(r"[\w./%:,=+\-\[\]${}@]*", value):
            values[name] = value
    for _ in range(4):
        text = re.sub(r"\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)",
                      lambda m: values.get(m.group(1) or m.group(2), m.group(0)), text)
    return text


def shell_words(line):
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return line.split()


def flattened(text):
    """A shell script with its continuation lines joined and its comments removed."""
    return "\n".join(uncommented(line) for line in re.sub(r"\\\n", " ", text).splitlines())


def submissions(text):
    """[(the words after condor_submit, was it inside a loop, where in flattened(text))] for every time a shell
    script runs condor_submit on something: `command -v condor_submit` is not a submission."""
    found, depth, offset = [], 0, 0
    for line in flattened(text).splitlines():
        if re.match(r"\s*(for|while|until)\b", line):
            depth += 1
        tokens = shell_words(line)
        for index, token in enumerate(tokens):
            if token == "condor_submit" or token.endswith("/condor_submit"):
                rest = []
                for word in tokens[index + 1:]:
                    if re.fullmatch(r"[();<>|&]+", word):
                        break
                    rest.append(word)
                if any(not word.startswith("-") for word in rest):
                    found.append((rest, depth > 0 or bool(re.search(r"\b(xargs|parallel)\b", line)), offset + line.index("condor_submit")))
        if re.search(r"(^|[;\s])done\b", line):
            depth = max(0, depth - 1)
        offset += len(line) + 1
    return found


def description(text, appended=()):
    """({command in lower case: value} up to the first queue statement, [the queue statements])."""
    settings, queues = {}, []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line.startswith("#"):
            continue
        while line.endswith("\\") and index < len(lines):
            line = line[:-1].rstrip() + " " + lines[index].strip()
            index += 1
        if re.match(r"queue(\s|$)", line, re.I):
            if line.endswith("("):                  # an inline list, one item to a line, closed by a line that is ")"
                items = []
                while index < len(lines) and lines[index].strip() != ")":
                    items.append(lines[index].strip())
                    index += 1
                index += 1
                line = line + "\n" + "\n".join(items) + "\n)"
            queues.append(line)
            continue
        match = re.match(r"([+\w.]+)\s*=\s*(.*)$", line)
        if match and not queues:                    # what comes after the queue statement does not apply to its jobs
            settings[match.group(1).lower()] = match.group(2).strip()
    for extra in appended:
        match = re.match(r"([+\w.]+)\s*=\s*(.*)$", extra.strip())
        if match:
            settings[match.group(1).lower()] = match.group(2).strip()
    return settings, queues


def substituted(value, variables):
    """A submit-file value with its $(name) and $Fnx(name) macros put in."""
    def replace(match):
        function, inner = match.group(1), match.group(2)
        name = inner.split(":", 1)[0].strip().lower()
        if name not in variables:
            return inner.split(":", 1)[1] if ":" in inner and not function else match.group(0)
        text = variables[name]
        if not function:
            return text
        path = PurePosixPath(text.strip('"'))
        if function.upper() == "BASENAME":
            return path.name
        if function.upper() == "DIRNAME":
            return str(path.parent)
        if re.fullmatch(r"F[fpduwnxbqa]*", function, re.I):
            flags = function[1:].lower()
            parts = ""
            if "p" in flags or "d" in flags:
                parts += "" if str(path.parent) == "." else str(path.parent) + "/"
            if "n" in flags:
                parts += path.stem
            if "x" in flags:
                parts += path.suffix
            return parts if set(flags) & set("pdnx") else text
        return match.group(0)

    for _ in range(4):
        value = re.sub(r"\$(\w*)\(([^()]*)\)", replace, value)
    return value


def jobs_made(settings, queues):
    """One {macro: value} for each job the queue statement makes."""
    assert len(queues) == 1, "job.sub has %d queue statements, not one" % len(queues)
    rest = queues[0][5:].strip()
    match = re.match(r"(.*?)\b(in|from|matching)\b(.*)$", rest, re.I | re.S)
    if not match:
        count = substituted(rest or "1", settings)
        assert count.isdigit(), "not a queue statement this check can read: %r" % queues[0]
        rows, names, repeat = [[]] * int(count), [], 1
    else:
        before, keyword, after = match.group(1), match.group(2).lower(), match.group(3).strip()
        names = [word for word in re.split(r"[\s,]+", before.strip()) if word]
        repeat = int(names.pop(0)) if names and names[0].isdigit() else 1
        names = [name.lower() for name in names] or ["item"]
        if keyword == "matching":
            after = re.sub(r"^(files|dirs|any)\b\s*", "", after, flags=re.I)
        after = re.sub(r"^\[[^\]]*\]\s*", "", after)
        if keyword == "matching":
            rows = [[name] for pattern in re.split(r"[\s,]+", after.strip("() \n")) if pattern
                    for name in sorted(glob.glob(substituted(pattern, settings)))]
        elif keyword == "in":
            rows = [[item] for item in re.split(r"[\s,]+", after.strip("() \n")) if item]
        else:
            if after.startswith("("):
                lines = after.strip("()").splitlines()
            else:
                source = Path(substituted(after, settings))
                assert source.is_file(), "queue ... from %s: there is no such file" % after
                lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
            rows = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    rows.append([line] if len(names) == 1 else
                                [field.strip() for field in (line.split(",") if "," in line else line.split())])
    made = []
    for number, row in enumerate(rows):
        for step in range(repeat):
            variables = dict(settings)
            variables.update(zip(names, row))
            process = str(len(made))
            variables.update(item=row[0] if row else "", step=str(step), row=str(number), itemindex=str(number),
                             process=process, procid=process, cluster="4242", clusterid="4242")
            made.append(variables)
    return made


def megabytes(value):
    """request_memory: megabytes unless a unit is written."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGT]?)B?", value.strip().strip('"'), re.I)
    assert match, "not a memory request: %r" % value
    return float(match.group(1)) * {"K": 1 / 1024, "": 1, "M": 1, "G": 1024, "T": 1024 ** 2}[match.group(2).upper()]


def job():
    """(what job.sub says, the jobs it makes, the condor_submit calls of submit.sh)."""
    submit = expanded(Path("submit.sh").read_text(encoding="utf-8", errors="replace")) if Path("submit.sh").is_file() else ""
    calls = submissions(submit)
    appended = []
    for words, _, _ in calls[:1]:
        for index, word in enumerate(words):
            if word in ("-a", "-append") and index + 1 < len(words):
                appended.append(words[index + 1])
            elif re.fullmatch(r"[+\w.]+=.*", word):
                appended.append(word)
    settings, queues = description(text_of("job.sub"), appended)
    return settings, queues, calls


def of(job_variables, command):
    """A submit command's value for one job, macros put in; "" if it is not given."""
    return substituted(job_variables.get(command, ""), job_variables)


def transferred(job_variables):
    """The names, as they land in the job's scratch directory, of what is transferred to it."""
    names = [PurePosixPath(entry.strip('"')).name for entry in re.split(r"[,\s]+", of(job_variables, "transfer_input_files")) if entry]
    if job_variables.get("transfer_executable", "true").strip().lower() != "false":
        names.append(PurePosixPath(of(job_variables, "executable")).name)
    return names


def inputs_named(job_variables):
    """The run files a job is told about, by its arguments, environment or transfer list."""
    told = " ".join(of(job_variables, command) for command in ("arguments", "environment", "transfer_input_files"))
    return set(re.findall(r"run_\d{4}\.dat", told))


# --- the tests -----------------------------------------------------------------------

def test_job_sub_is_a_submit_description_that_runs_run_sh():
    settings, queues, _ = job()
    assert len(queues) == 1, "job.sub has %d queue statements, not one" % len(queues)
    assert PurePosixPath(substituted(settings.get("executable", ""), settings)).name == "run.sh", \
        "the executable is %r, not run.sh" % settings.get("executable")
    assert text_of("run.sh").startswith("#!"), "run.sh has no interpreter line: the execute node cannot start it"


def test_the_queue_statement_makes_one_job_for_each_run_file():
    settings, queues, _ = job()
    made = jobs_made(settings, queues)
    assert len(made) == N_INPUTS, "the queue statement makes %d jobs, not %d" % (len(made), N_INPUTS)
    named = [inputs_named(variables) for variables in made]
    assert all(len(names) == 1 for names in named), "a job is not told which one run file is its own"
    assert set().union(*named) == set(INPUTS), "the jobs do not cover the files in inputs.txt, each once"


def test_cores_and_memory_are_requested():
    settings, _, _ = job()
    assert settings.get("request_cpus", "").strip() == str(CORES)
    assert "request_memory" in settings, "no request_memory: the job gets 1024 MB and is held when it goes over"
    assert MEMORY_MB[0] <= megabytes(settings["request_memory"]) <= MEMORY_MB[1], settings["request_memory"]


def test_accounting_group_and_run_time_are_given_as_the_pool_wants():
    settings, _, _ = job()
    assert settings.get("accounting_group", "").strip('"') == ACCOUNTING_GROUP
    runtime = settings.get("+maxruntime", settings.get("my.maxruntime"))
    assert runtime is not None, "no MaxRuntime attribute: the job is removed after 20 minutes"
    assert re.fullmatch(r"\d[\d\s*+]*", runtime) and "**" not in runtime, "MaxRuntime is a number of seconds: %r" % runtime
    product = 0
    for term in runtime.split("+"):                 # 7200, 2 * 3600, 2*60*60
        factors = [int(factor) for factor in term.split("*") if factor.strip()]
        value = 1
        for factor in factors:
            value *= factor
        product += value if factors else 0
    assert product == SECONDS, "MaxRuntime is in seconds: %r" % runtime


def test_what_the_job_reads_is_transferred_to_it():
    settings, queues, _ = job()
    assert settings.get("should_transfer_files", "yes").strip().lower() in ("yes", "if_needed", "true"), \
        "file transfer is off, and the execute nodes mount nothing from the submit node"
    for variables in jobs_made(settings, queues):
        landed = transferred(variables)
        for needed in [PROGRAM, CALIBRATION] + sorted(inputs_named(variables)):
            assert needed in landed, "%s is not transferred to the job that needs it (it gets %s)" % (needed, landed)


def test_the_job_uses_its_files_where_they_land_in_its_scratch_directory():
    settings, queues, _ = job()
    script = "\n".join(uncommented(line) for line in text_of("run.sh").splitlines())
    here = str(Path.cwd())
    variables = jobs_made(settings, queues)[0]
    arguments, environment = of(variables, "arguments"), of(variables, "environment")
    # Transfer puts each file in the top of the scratch directory under its own name: that is where the job finds it.
    for word in re.findall(r"[^\s\"'=;]+", arguments + " " + environment):
        if PurePosixPath(word).name in INPUTS + [PROGRAM, CALIBRATION]:
            assert "/" not in word.replace("./", "", 1), "the job is given %s, which is not where the file lands" % word
    for where in (script, arguments, environment):
        assert not re.search(r"\$ENV\((PWD|HOME)\)|\$\{?HOME\}?/|(^|[\s\"':])~/|(^|[\s\"'=:])/(home|data)(/|\b)", where, re.M), \
            "a path on the submit node, which the execute nodes do not mount"
        assert here not in where and str(Path.cwd().resolve()) not in where, "a path on the submit node"
    assert not re.search(r"\bcd\s+[\"']?(/|\$\{?(SUBMIT|INITIAL|ORIG|PROJECT|WORK)\w*)", script, re.I), "run.sh leaves the scratch directory"
    for prefix, _ in re.findall(r"(\S*?)(analyse\.py|calib\.json)", script.replace('"', "").replace("'", "")):
        assert not prefix.startswith("/"), "run.sh reads %s... from an absolute path" % prefix
    assert PROGRAM in script or PROGRAM in arguments, "nothing runs analyse.py"
    if inputs_named(variables) & set(re.findall(r"run_\d{4}\.dat", arguments)):
        assert re.search(r"\$\{?[@*1-9]", script), "run.sh does not use the run file it is given as an argument"


def test_each_job_has_its_own_output_and_error_file_in_logs():
    settings, queues, _ = job()
    made = jobs_made(settings, queues)
    for command in ("output", "error"):
        paths = [of(variables, command) for variables in made]
        assert all(re.match(r"(\./)?logs/.", path) for path in paths), "%s is not in logs/: %r" % (command, paths[:1])
        assert len(set(paths)) == len(made), "the jobs share one %s file: %r" % (command, paths[:1])


def test_no_more_than_ten_jobs_are_going_at_once():
    settings, _, _ = job()
    assert settings.get("max_materialize", "").strip() == str(AT_ONCE), \
        "max_materialize is %r: nothing keeps it to %d jobs at once" % (settings.get("max_materialize"), AT_ONCE)


def test_submit_sh_makes_logs_and_submits_once():
    _, _, calls = job()
    assert calls, "submit.sh does not run condor_submit"
    assert len(calls) == 1 and not calls[0][1], "one condor_submit of one submit file makes all the jobs: not a loop of them"
    assert any(word.endswith("job.sub") for word in calls[0][0]), "submit.sh does not submit job.sub"
    made = re.search(r"\b(mkdir|install\s+-d)\b[^\n;&|]*\blogs\b", flattened(expanded(text_of("submit.sh"))))
    # A job whose output folder is missing is put on hold.
    assert Path("logs").is_dir() or (made and made.start() < calls[0][2]), "nothing makes logs/ before condor_submit"
