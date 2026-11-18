"""What the task is built to catch: an LSF script submitted the way sbatch and qsub take theirs.

`bsub job.sh` runs the script as a command: not one #BSUB line is read, and
the job gets the defaults. And in the script: eight slots that may land on
several hosts (no span[hosts=1]) for a program that threads on one, memory
reserved with no limit (the queue's 2 GB applies), the queue called what it
is called elsewhere, and no project.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]

Path("job.sh").write_text("""#!/bin/bash
#BSUB -J "spectra[1-%d]%%4"
#BSUB -q normal
#BSUB -n 8
#BSUB -R "rusage[mem=32GB]"
#BSUB -W 06:00
#BSUB -o logs/%%J_%%I.out

module load python
export OMP_NUM_THREADS=8
label=$(sed -n "${LSB_JOBINDEX}p" inputs.txt)
python spectra.py "$label"
""" % len(inputs))

Path("submit.sh").write_text("""#!/bin/bash
mkdir -p logs
bsub job.sh
""")
