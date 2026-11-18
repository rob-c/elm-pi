"""The reference solution: run in the project folder, writes job.sh and submit.sh.

Eight slots held to one host, 32 GB both reserved and set as the limit (per
job, as the guide says the site counts them), the array in the job name with
its cap, the queue and project the guide gives, and a submit.sh that makes
logs/ and feeds job.sh to bsub on standard input - `bsub job.sh` would run
the script with none of its #BSUB lines read.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]

Path("job.sh").write_text("""#!/bin/bash
#BSUB -J "spectra[1-%d]%%4"
#BSUB -q medium-x
#BSUB -P nustruct-25
#BSUB -n 8
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=32GB]"
#BSUB -M 32GB
#BSUB -W 06:00
#BSUB -o logs/%%J_%%I.out
#BSUB -e logs/%%J_%%I.err
set -euo pipefail

module purge
module load python/3.11-sci

export OMP_NUM_THREADS=$LSB_DJOB_NUMPROC
label=$(sed -n "${LSB_JOBINDEX}p" inputs.txt)
python spectra.py "$label"
""" % len(inputs))

Path("submit.sh").write_text("""#!/bin/bash
# Run from the project folder: the job starts where it is submitted from.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
bsub < job.sh
""")
Path("job.sh").chmod(0o755)
Path("submit.sh").chmod(0o755)
print("job.sh: an array of %d, 4 at once; submit.sh makes logs/ and runs bsub < job.sh" % len(inputs))
