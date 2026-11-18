"""The reference solution: run in the project folder, writes job.sh and submit.sh.

PBS Professional's own resource line (one chunk of four cores and 12 GB), its
-J array with a throttle, $PBS_ARRAY_INDEX for the line of inputs.txt, the
queue and account string the guide gives, cd to $PBS_O_WORKDIR because a PBS
job starts in the home directory, and the log folder made before qsub.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]

Path("job.sh").write_text("""#!/bin/bash
#PBS -N reco
#PBS -q std-d
#PBS -A NUCS0421
#PBS -l select=1:ncpus=4:mem=12gb
#PBS -l walltime=01:30:00
#PBS -J 1-%d%%10
#PBS -j oe
#PBS -o logs/
set -euo pipefail

cd "$PBS_O_WORKDIR"
module purge
module load python/3.11-sci

file=$(sed -n "${PBS_ARRAY_INDEX}p" inputs.txt)
python reco.py --threads "$NCPUS" "$file"
""" % len(inputs))

Path("submit.sh").write_text("""#!/bin/bash
# Run from the project folder: the job changes to the folder it was submitted from.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
qsub job.sh
""")
Path("job.sh").chmod(0o755)
Path("submit.sh").chmod(0o755)
print("job.sh: an array of %d sub-jobs, 10 at once; submit.sh makes logs/ and submits" % len(inputs))
