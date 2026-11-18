"""The reference solution: run in the project folder, writes job.sh and submit.sh.

Six slots in the site's single-host parallel environment, h_vmem per slot
(24 GB over 6 slots is 4G), the array over the lines of inputs.txt with -tc,
-cwd so that the job and its relative log path start from the project folder,
the project the guide gives and no queue, and the log folder made before
qsub - a job whose log folder is missing goes to Eqw.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]
slots, total_gb = 6, 24
assert total_gb % slots == 0

Path("job.sh").write_text("""#!/bin/bash
#$ -N fit_bands
#$ -S /bin/bash
#$ -cwd
#$ -P hadron-th
#$ -pe sharedmem %d
#$ -l h_rt=04:00:00
#$ -l h_vmem=%dG
#$ -t 1-%d
#$ -tc 5
#$ -j y
#$ -o logs/
set -euo pipefail

module purge
module load anaconda/2024.02

export OMP_NUM_THREADS=$NSLOTS
label=$(sed -n "${SGE_TASK_ID}p" inputs.txt)
python fit_bands.py "$label"
""" % (slots, total_gb // slots, len(inputs)))

Path("submit.sh").write_text("""#!/bin/bash
# Run from the project folder: -cwd starts the job where it is submitted from.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
qsub job.sh
""")
Path("job.sh").chmod(0o755)
Path("submit.sh").chmod(0o755)
print("job.sh: %d tasks, 5 at once, %d slots x %dG; submit.sh makes logs/ and submits" % (len(inputs), slots, total_gb // slots))
