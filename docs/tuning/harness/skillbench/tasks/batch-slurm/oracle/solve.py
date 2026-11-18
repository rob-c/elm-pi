"""The reference solution: run in the project folder, writes job.sh and submit.sh.

One task with eight CPUs (the program is threaded), 16G for the node, the
array over the lines of inputs.txt with a throttle of six, the partition and
account the guide gives, and the log folder made before sbatch - Slurm fails
a job at once if the folder of its output file is not there.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]

Path("job.sh").write_text("""#!/bin/bash
#SBATCH --job-name=covariance
#SBATCH --partition=compute-b
#SBATCH --account=phys-neutrino
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --array=1-%d%%6
#SBATCH --output=logs/%%x_%%A_%%a.out
set -euo pipefail

module purge
module load python/3.11-sci

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
input=$(sed -n "${SLURM_ARRAY_TASK_ID}p" inputs.txt)
srun --cpus-per-task="$SLURM_CPUS_PER_TASK" python analyse.py "$input"
""" % len(inputs))

Path("submit.sh").write_text("""#!/bin/bash
# Run from the project folder: the job starts where it is submitted from.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
sbatch job.sh
""")
Path("job.sh").chmod(0o755)
Path("submit.sh").chmod(0o755)
print("job.sh: an array of %d tasks, 6 at once; submit.sh makes logs/ and submits" % len(inputs))
