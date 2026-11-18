"""The reference solution: run in the project folder, writes job.sub, run.sh and submit.sh.

One submit file whose queue statement makes a job for each line of
inputs.txt; the program, its calibration and the job's own run file sent by
file transfer, and used by run.sh where they land - the job's scratch
directory; cores and memory requested; the pool's accounting group and
MaxRuntime; max_materialize to keep ten going; and the log folder made before
condor_submit.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]
assert all(Path(name).is_file() for name in inputs)

Path("job.sub").write_text("""# One job for each run file listed in inputs.txt.
executable              = run.sh
arguments               = $(infile)

should_transfer_files   = YES
when_to_transfer_output = ON_EXIT
transfer_input_files    = analyse.py, calib.json, $(infile)

output                  = logs/$(Cluster).$(Process).out
error                   = logs/$(Cluster).$(Process).err
log                     = logs/$(Cluster).log

request_cpus            = 4
request_memory          = 8GB

accounting_group        = group_physics.nuosc
+MaxRuntime             = 7200

max_materialize         = 10
max_retries             = 2

queue infile from inputs.txt
""")

Path("run.sh").write_text("""#!/bin/bash
# Runs on the execute node, in the job's scratch directory: analyse.py, calib.json
# and the run file named in $1 were transferred there, and the result is written there.
set -euo pipefail
python3 analyse.py "$1"
""")

Path("submit.sh").write_text("""#!/bin/bash
# Run on the submit node, from the project folder.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
condor_submit job.sub
""")
Path("run.sh").chmod(0o755)
Path("submit.sh").chmod(0o755)
print("job.sub: one job for each of %d inputs, 10 at once; submit.sh makes logs/ and submits" % len(inputs))
