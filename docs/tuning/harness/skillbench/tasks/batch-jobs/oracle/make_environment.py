"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A job script from the old cluster (Torque) and the user guide of the new one,
which never says what its scheduler is called: it shows the commands (qsub,
qstat, qconf, qacct, qlogin), a qstat listing and a qconf listing. That is
Grid Engine; qsub and qstat are PBS's names too, and the old script's #PBS
lines are comments to it. Nothing can be submitted where the task runs, so
what is asked for is the job script and the script that submits it, and the
check reads them.

What the guide fixes, and a session can only get by reading it:

- the scheduler, from its commands and listings;
- the queue `work-s.q` (required, no default) and the project `qcd-lat24`;
- the single-host parallel environment `onehost`;
- memory is `h_vmem`, per slot: the old job's mem=24gb is 2G on 12 slots;
- `h_rt` is required; the Python module is `sci-python/2025a`.

What the old script has that does not carry over: #PBS, nodes=1:ppn=12,
-t 1-36%4, $PBS_O_WORKDIR, $PBS_ARRAYID, $PBS_NUM_PPN, the queue `batch`, the
account `nucth`, the module python/3.9.6.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

ENERGIES = [200, 300, 400, 500, 650, 800, 1000, 1250, 1500]
LATTICES = [12, 16, 20, 24]
labels = ["E%04d_L%d" % (energy, lattice) for lattice in LATTICES for energy in ENERGIES]
N_INPUTS = len(labels)
assert N_INPUTS == 36
(out / "inputs.txt").write_text("\n".join(labels) + "\n")

(out / "transport.py").write_text('''#!/usr/bin/env python3
"""Transport coefficient for one configuration.

    python transport.py E0500_L16

The argument is a label, E<energy in MeV>_L<lattice size>, as listed one to a
line in inputs.txt. Builds the collision matrix, solves for the relaxation
spectrum and writes results/<label>.json (the folder is made if it is not
there). Paths are taken relative to the directory the program is started in.

The linear algebra is numpy's and is multithreaded: it runs on as many threads
as OMP_NUM_THREADS says, and on every core of the machine if that is not set.
At production size a configuration takes about two hours on 12 cores and
peaks near 19 GB.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np


def main(label):
    match = re.fullmatch(r"E(\\d{4})_L(\\d+)", label)
    if not match:
        sys.exit("not a label: %r" % label)
    energy, lattice = int(match.group(1)), int(match.group(2))
    index = np.arange(4 * lattice)
    matrix = np.diag(1.0 + index / lattice) + (energy / 1000.0) * np.exp(-np.abs(index[:, None] - index[None, :]) / 2.0)
    rates = np.linalg.eigvalsh(matrix)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (label + ".json")
    target.write_text(json.dumps({"label": label, "slowest_rates": [round(float(v), 5) for v in rates[:5]]}, indent=1) + "\\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
''')

(out / "old_job.sh").write_text('''#!/bin/bash
# Transport scan on Stoat: one array element for each line of inputs.txt.
#PBS -N transport
#PBS -q batch
#PBS -A nucth
#PBS -l nodes=1:ppn=12
#PBS -l mem=24gb
#PBS -l walltime=03:00:00
#PBS -t 1-36%4
#PBS -j oe
#PBS -o logs/
set -euo pipefail

cd "$PBS_O_WORKDIR"
module purge
module load python/3.9.6

export OMP_NUM_THREADS=$PBS_NUM_PPN
config=$(sed -n "${PBS_ARRAYID}p" inputs.txt)
python transport.py "$config"
''')

(out / "cluster.md").write_text("""# Marten user guide

Marten is the College's new cluster; it replaced Stoat, which was switched
off in October. This copy of the guide is the lattice group's: the group's
own details are filled in where the public page says "ask your supervisor".

- Login: `ssh marten.hpc.example.ac.uk`.
- The login nodes are for editing, compiling and submitting. Anything that
  runs for more than a few minutes there is killed.

## The batch system

Work is done by jobs. The commands:

| Command | What it does |
|---|---|
| `qsub job.sh` | Submits a job script and prints the job's number. |
| `qstat -u $USER` | Your jobs. States: `qw` waiting, `r` running, `hqw` held, `Eqw` in error. |
| `qstat -j <job>` | Why a job is waiting, or what its error was. |
| `qdel <job>` | Removes a job. |
| `qacct -j <job>` | What a finished job used: `exit_status`, `failed`, `ru_wallclock`, `maxvmem`. |
| `qconf -sql`, `qconf -spl`, `qconf -sc` | The queues, the parallel environments, the resources. |
| `qlogin` | An interactive session on a compute node. |

What you will see:

```
$ qstat -u $USER
job-ID  prior   name       user     state submit/start at     queue                 slots ja-task-ID
---------------------------------------------------------------------------------------------------
 481223 0.50500 mcprod     ab1234   r     11/16/2026 09:14:02 work-s.q@mn041            8 7
 481223 0.50500 mcprod     ab1234   r     11/16/2026 09:14:02 work-s.q@mn017            8 8
 481223 0.00000 mcprod     ab1234   qw    11/16/2026 09:13:40                           8 9-200:1

$ qconf -spl
mpi-ib
onehost
```

## Queues

| Queue | Longest job | What it is for |
|---|---|---|
| `debug-s.q` | 15 minutes | Tests. One job per user. |
| `work-s.q` | 72 hours | Production work on the standard nodes (`mn001` to `mn160`: 48 cores, 384 GB). |
| `gpu-s.q` | 48 hours | The GPU nodes. Jobs that request no `gpu` are rejected. |

A job has to name its queue: there is no default, and one that names none is
rejected.

## Projects

Every job is accounted to a project, and a job that gives none is rejected
(`job rejected: no project was specified`). The lattice group's project is
`qcd-lat24`.

## Parallel environments

A job that names no parallel environment has one slot, whatever it starts.

| Name | How the slots are placed | For |
|---|---|---|
| `onehost` | All on one node, up to 48 | Threaded programs. |
| `mpi-ib` | Across nodes, whole nodes first | MPI over InfiniBand. |

## Resources to request

| Resource | What it is | If not given |
|---|---|---|
| `h_rt` | Wall-clock limit. | The job is rejected. |
| `h_vmem` | Memory limit, per slot. The job is killed if it goes over. | 1G |
| `gpu` | Number of GPUs (in `gpu-s.q` only). | 0 |

## Other things to know

- A job script is started with the interpreter named on its first line.
- Array jobs may have up to 5000 tasks. Keep the number running at once
  modest: the share calculation is per project.
- `$TMPDIR` is node-local scratch, made for each job (each task of an array)
  and removed when it ends. `/work/<project>` is shared and visible on every
  node, as is `/home`.

## Software

Software is provided through environment modules (`module avail`); Stoat's
module names were not carried over. The compute nodes' own Python has no
numpy; the scientific Python stack (Python 3.12, numpy, scipy, pandas) is
`sci-python/2025a`.

## Getting help

`marten-help@example.ac.uk`, with the job number and the path of the script.
""")
print("wrote cluster.md, old_job.sh, transport.py and inputs.txt with %d labels" % N_INPUTS)
