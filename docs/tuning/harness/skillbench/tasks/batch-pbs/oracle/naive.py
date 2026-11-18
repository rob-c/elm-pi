"""What the task is built to catch: the Torque script everybody has a copy of, on a PBS Professional site.

nodes=1:ppn=4 and -t with $PBS_ARRAYID are Torque's; PBS Professional wants
select chunks and -J with $PBS_ARRAY_INDEX. Nothing changes to the folder the
job was submitted from, so it starts in the home directory, where inputs.txt
is not. The queue is the name it had elsewhere, and there is no account.
"""
from pathlib import Path

inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]

Path("job.sh").write_text("""#!/bin/bash
#PBS -N reco
#PBS -q batch
#PBS -l nodes=1:ppn=4,mem=12gb,walltime=01:30:00
#PBS -t 1-%d%%10
#PBS -j oe
#PBS -o logs/

module load python
file=$(sed -n "${PBS_ARRAYID}p" inputs.txt)
python reco.py --threads 4 "$file"
""" % len(inputs))

Path("submit.sh").write_text("""#!/bin/bash
mkdir -p logs
qsub job.sh
""")
