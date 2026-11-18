"""What the task is built to catch: a Grid Engine script written from another site's habits.

h_vmem set to the job's 24 GB (the limit is per slot: 6 x 24G is asked for,
and no node has it), the parallel environment called smp as it was somewhere
else, no -cwd, no project, and a log folder nobody made.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]

Path("job.sh").write_text("""#!/bin/bash
#$ -N fit_bands
#$ -pe smp 6
#$ -l h_vmem=24G
#$ -l h_rt=04:00:00
#$ -t 1-%d
#$ -tc 5
#$ -o logs/
#$ -e logs/

module load python
export OMP_NUM_THREADS=$NSLOTS
label=$(sed -n "${SGE_TASK_ID}p" inputs.txt)
python fit_bands.py "$label"
""" % len(inputs))

Path("submit.sh").write_text("""#!/bin/bash
qsub job.sh
""")
