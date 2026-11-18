"""What the task is built to catch: HTCondor used as if it were a batch queue on a shared filesystem.

A loop of condor_submit calls, one per input, where one queue statement would
make the jobs; a run.sh that changes to the folder on the submit node, which
the execute nodes do not mount, with no file transfer; no request_memory, so
each job gets the default 1024 MB and is held; and neither the accounting
group nor the run-time attribute the pool wants.
"""
from pathlib import Path

Path("job.sub").write_text("""executable   = run.sh
arguments    = $(infile)
environment  = "SUBMIT_DIR=$ENV(PWD)"
getenv       = True
output       = logs/$(infile).out
error        = logs/$(infile).err
log          = logs/analyse.log
request_cpus = 4
queue
""")

Path("run.sh").write_text("""#!/bin/bash
cd "$SUBMIT_DIR"
python3 analyse.py "$1"
""")

Path("submit.sh").write_text("""#!/bin/bash
mkdir -p logs
while read -r infile; do
    condor_submit -append "infile=$infile" job.sub
done < inputs.txt
""")
Path("run.sh").chmod(0o755)
