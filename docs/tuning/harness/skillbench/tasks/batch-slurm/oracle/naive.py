"""What the task is built to catch: a Slurm script written from habit.

Eight tasks for an eight-thread program, --mem taken as per core (2G, for
"8 x 2 = 16"), an array with no throttle, a partition name that is not this
site's and no account, and a log folder nobody made.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]

Path("job.sh").write_text("""#!/bin/bash
#SBATCH --job-name=covariance
#SBATCH --partition=compute
#SBATCH --time=02:00:00
#SBATCH --ntasks=8
#SBATCH --mem=2G
#SBATCH --array=1-%d
#SBATCH --output=logs/%%A_%%a.out

module load python
input=$(sed -n "${SLURM_ARRAY_TASK_ID}p" inputs.txt)
python analyse.py "$input"
""" % len(inputs))

Path("submit.sh").write_text("""#!/bin/bash
sbatch job.sh
""")
