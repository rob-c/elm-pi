"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A Grid Engine cluster's user guide, a threaded program and 30 inputs. Nothing
can be submitted where the task runs, so what is asked for is the job script
and the script that submits it, and the check reads them.

What the guide fixes, and a session can only get by reading it:

- the single-host parallel environment is called `sharedmem` (not smp);
- the project is `hadron-th`, required; no queue is to be named;
- memory is `h_vmem`, per slot: 24 GB for a 6-slot job is 4G;
- `h_rt` is required.

What Grid Engine fixes, and the guide does not spell out: `#$` directives,
`-cwd` (a job starts in the home directory without it, and a relative log
path is taken from there), `-t` with `-tc` for the array, $SGE_TASK_ID and
$NSLOTS, and a log folder that has to exist or the job sits in Eqw.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

NUCLEI = ["Ni56", "Ni68", "Ni78", "Zr90", "Zr96", "Sn100", "Sn112", "Sn120", "Sn132", "Pb208"]
FORCES = ["SLy4", "SkM", "UNEDF1"]
labels = ["%s_%s" % (nucleus, force) for force in FORCES for nucleus in NUCLEI]
N_INPUTS = len(labels)
assert N_INPUTS == 30
(out / "inputs.txt").write_text("\n".join(labels) + "\n")

(out / "fit_bands.py").write_text('''#!/usr/bin/env python3
"""Single-particle levels of one nucleus with one interaction.

    python fit_bands.py Sn132_SLy4

The argument is a label, <nucleus>_<interaction>, as listed one to a line in
inputs.txt. Builds the model Hamiltonian in an oscillator basis, diagonalises
it and writes results/<label>.json (the folder is made if it is not there).
Paths are taken relative to the directory the program is started in.

The diagonalisation is numpy's and is multithreaded: it runs on as many
threads as OMP_NUM_THREADS says, and on every core of the machine if that is
not set. At production basis size a nucleus takes about two and a half hours
on 6 cores and peaks near 20 GB.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

STRENGTH = {"SLy4": 1.00, "SkM": 0.93, "UNEDF1": 1.04}


def main(label, size=60):
    match = re.fullmatch(r"([A-Z][a-z]?)(\\d+)_(\\w+)", label)
    if not match or match.group(3) not in STRENGTH:
        sys.exit("not a label: %r" % label)
    mass = int(match.group(2))
    index = np.arange(size)
    hamiltonian = np.diag(41.0 * mass ** (-1 / 3) * (index + 1.5))
    coupling = STRENGTH[match.group(3)] * np.exp(-np.abs(index[:, None] - index[None, :]) / 3.0)
    levels = np.linalg.eigvalsh(hamiltonian - coupling)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (label + ".json")
    target.write_text(json.dumps({"label": label, "lowest_mev": [round(float(v), 4) for v in levels[:8]]}, indent=1) + "\\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
''')

(out / "cluster.md").write_text("""# Tarn user guide

Tarn is the Faculty of Science cluster. This copy of the guide is the hadron
theory group's: the group's own details are filled in where the public page
says "ask your supervisor".

- Login: `ssh tarn.science.example.ac.uk`.
- Scheduler: Son of Grid Engine 8.1.9.
- The login node is for editing, compiling and submitting. Anything that runs
  for more than a few minutes there is killed.

## Nodes

| Hosts | Each | Notes |
|---|---|---|
| `tn001` to `tn120` | 32 cores, 192 GB | Standard nodes. |
| `tb01` to `tb04` | 32 cores, 1.5 TB | For jobs that cannot fit on a standard node. |
| `tg01` to `tg08` | 24 cores, 2 x V100 | Jobs that request `gpu`. |

Do not name a queue. The scheduler places a job from what it asks for, and
the submission check rejects a job that names one.

## Projects

Every job is accounted to a project, and a job that gives none is rejected
(`job rejected: no project was specified`). Your projects are the ones
`qconf -sprjl` lists and your supervisor has added you to; the hadron theory group's
is `hadron-th`.

## Parallel environments

A job that names no parallel environment has one slot, whatever it starts.
`qconf -spl` lists the environments:

| Name | How the slots are placed | For |
|---|---|---|
| `sharedmem` | All on one host, up to 32 | Threaded programs: OpenMP, multithreaded libraries. |
| `mpi-fill` | Host after host, each filled first | MPI. |
| `mpi-rr` | One slot on each host in turn | MPI programs that want memory bandwidth. |

## Resources to request

`qconf -sc` shows every resource the site defines. The ones a job asks for:

| Resource | What it is | If not given |
|---|---|---|
| `h_rt` | Wall-clock limit. The longest allowed is 72 hours. | The job is rejected. |
| `h_vmem` | Memory limit, per slot. The job is killed if it goes over. | 1G |
| `gpu` | Number of GPUs. | 0 |

## Other things to know

- A job script is started with the interpreter named on its first line.
- Array jobs may have up to 2000 tasks. Please do not let more than a few
  dozen run at once: the fair-share calculation is per project.
- `$TMPDIR` is node-local scratch, made for each job (each task of an array)
  and removed when it ends. `/work/$USER` is shared, not backed up, and is
  visible on every node, as is `/home`.

## Software

Software is provided through environment modules (`module avail`). The
compute nodes' own Python has no numpy; the scientific Python stack is
`anaconda/2024.02`.

## Getting help

`tarn-help@example.ac.uk`, with the job number and the path of the script.
""")
print("wrote cluster.md, fit_bands.py and inputs.txt with %d labels" % N_INPUTS)
