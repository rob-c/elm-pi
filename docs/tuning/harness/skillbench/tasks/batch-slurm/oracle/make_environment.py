"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A Slurm cluster's user guide, a threaded program and 48 inputs. Nothing can be
submitted where the task runs, so what is asked for is the job script and the
script that submits it, and the check reads them.

What the guide fixes, and a session can only get by reading it:

- the partition is `compute-b` (the other three refuse this job: 30 minutes,
  more than 256 GB only, GPU only) and there is no default partition;
- the account is `phys-neutrino`, and a job without one is rejected;
- Slurm 23.11, so `srun` does not inherit --cpus-per-task from sbatch.

What Slurm fixes, and the guide does not spell out: one task with eight CPUs
for a threaded program (not eight tasks), --mem per node (16G) or
--mem-per-cpu (2G), a throttle on the array (%6), and a log folder that has
to exist before sbatch.
"""
import random
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
(out / "data").mkdir(exist_ok=True)
rng = random.Random(20261117)

N_INPUTS = 48
runs = sorted(rng.sample(range(400, 900), N_INPUTS))
names = []
for run in runs:
    name = "data/run_%04d.csv" % run
    rows = ["ch0,ch1,ch2,ch3"]
    for _ in range(8):
        rows.append(",".join("%.3f" % rng.gauss(100.0, 12.0) for _ in range(4)))
    (out / name).write_text("\n".join(rows) + "\n")
    names.append(name)
(out / "inputs.txt").write_text("\n".join(names) + "\n")

(out / "analyse.py").write_text('''#!/usr/bin/env python3
"""Channel covariance of one run.

    python analyse.py data/run_0412.csv

Reads the run's table, diagonalises the covariance of its channels and writes
results/<run>.json (the folder is made if it is not there). Paths are taken
relative to the directory the program is started in.

The linear algebra is numpy's and is multithreaded: it runs on as many threads
as OMP_NUM_THREADS says, and on every core of the machine if that is not set.
A full-size run takes about 70 minutes on 8 cores and peaks near 12 GB.
"""
import json
import sys
from pathlib import Path

import numpy as np


def main(path):
    table = np.loadtxt(path, delimiter=",", skiprows=1)
    covariance = np.cov(table, rowvar=False)
    values = np.linalg.eigvalsh(covariance)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (Path(path).stem + ".json")
    target.write_text(json.dumps({"run": Path(path).stem, "rows": int(table.shape[0]),
                                  "eigenvalues": [float(v) for v in values]}, indent=1) + "\\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
''')

(out / "cluster.md").write_text("""# Kestrel user guide

Kestrel is the University's general-purpose HPC cluster, run by Research
Computing. This copy of the guide is the neutrino group's: the group's own
details are filled in where the public page says "ask your PI".

- Login: `ssh kestrel.hpc.example.ac.uk` (two login nodes, `kestrel-login1`
  and `kestrel-login2`).
- Scheduler: Slurm 23.11.4.
- The login nodes are for editing, compiling and submitting. A process that
  has used more than ten minutes of CPU there is killed without warning.

## Partitions

| Partition | Nodes | Each node | Longest job | What it is for |
|---|---|---|---|---|
| `short-b` | 4 | 64 cores, 256 GB | 30 minutes | Tests. One running job per user. |
| `compute-b` | 96 | 64 cores, 256 GB | 48 hours | Production work: serial, threaded and MPI jobs. |
| `himem-c` | 6 | 64 cores, 1.5 TB | 48 hours | Jobs that need more than 256 GB on one node. Smaller requests are rejected. |
| `gpu-a` | 12 | 32 cores, 4 x A100, 384 GB | 24 hours | GPU jobs. A job that asks for no GPU is rejected. |

There is no default partition: a job that names none is rejected at
submission. `sinfo -s` shows the state of each.

## Accounts

Every job is charged to an account, and a job submitted without one is
rejected (`Invalid account or account/partition combination specified`).
Accounts belong to research groups; `sacctmgr show assoc user=$USER` lists
the ones you may use. The neutrino group's account is `phys-neutrino`.

## What a job gets

- Hyperthreading is off: one CPU in Slurm is one core.
- A job is confined to the cores and the memory it was given (cgroups). A job
  that goes over its memory is killed by the out-of-memory handler.
- A job that asks for no memory gets 1 GB for each core it was given.
- A job that gives no time limit gets 10 minutes.
- Job arrays may have up to 1000 tasks. Be considerate about how many run
  at once: the fair-share calculation is per account, so a wide array holds
  back everybody else in your group.

## Storage

| Path | What | Notes |
|---|---|---|
| `/home/$USER` | 20 GB, backed up | Visible on every node. |
| `/proj/<group>` | Group space, backed up nightly | Visible on every node. Jobs are normally run from here. |
| `$TMPDIR` | Node-local scratch, `/local/job_<jobid>` | Made for each job and removed when it ends. |
| `/scratch/$USER` | Shared scratch | Files not read for 30 days are deleted. |

## Software

Software is provided through environment modules (`module avail`). Nothing
but the base operating system is on a compute node's default path, and the
system Python has no numpy. The scientific Python stack (Python 3.11 with
numpy, scipy, pandas and matplotlib) is `python/3.11-sci`.

## Getting help

`hpc-support@example.ac.uk`, with the job ID and the path of the job script.
""")
print("wrote cluster.md, analyse.py, inputs.txt and %d files in data/" % N_INPUTS)
