"""The reference solution: run in the project folder, writes job.sh and submit.sh.

The new cluster's commands (qconf, qacct, qlogin; `qw` and `Eqw`; slots and
parallel environments) are Grid Engine's, so the old script's #PBS lines are
rewritten as `#$` lines, not kept: the resources are read from them and put
in Grid Engine's terms. ppn=12 becomes 12 slots in the site's single-host
parallel environment, mem=24gb for the job becomes h_vmem per slot, -t 1-36%4
becomes -t 1-36 with -tc 4, cd $PBS_O_WORKDIR becomes -cwd, and the $PBS_
variables become $SGE_TASK_ID and $NSLOTS. Queue, project and module are the
new guide's.
"""
import re
from pathlib import Path

old = Path("old_job.sh").read_text()
cores = int(re.search(r"ppn=(\d+)", old).group(1))
total_gb = int(re.search(r"mem=(\d+)gb", old).group(1))
walltime = re.search(r"walltime=([\d:]+)", old).group(1)
first, last, at_once = re.search(r"#PBS -t (\d+)-(\d+)%(\d+)", old).groups()
name = re.search(r"#PBS -N (\S+)", old).group(1)
inputs = [line for line in Path("inputs.txt").read_text().splitlines() if line.strip()]
assert int(first) == 1 and int(last) == len(inputs) and total_gb % cores == 0

Path("job.sh").write_text("""#!/bin/bash
# Transport scan on Marten: one array task for each line of inputs.txt.
#$ -N %s
#$ -S /bin/bash
#$ -cwd
#$ -q work-s.q
#$ -P qcd-lat24
#$ -pe onehost %d
#$ -l h_rt=%s
#$ -l h_vmem=%dG
#$ -t 1-%d
#$ -tc %s
#$ -j y
#$ -o logs/
set -euo pipefail

module purge
module load sci-python/2025a

export OMP_NUM_THREADS=$NSLOTS
config=$(sed -n "${SGE_TASK_ID}p" inputs.txt)
python transport.py "$config"
""" % (name, cores, walltime, total_gb // cores, len(inputs), at_once))

Path("submit.sh").write_text("""#!/bin/bash
# Run from the project folder: -cwd starts the job where it is submitted from.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
qsub job.sh
""")
Path("job.sh").chmod(0o755)
Path("submit.sh").chmod(0o755)
print("job.sh: %d tasks, %s at once, %d slots x %dG, %s" % (len(inputs), at_once, cores, total_gb // cores, walltime))
