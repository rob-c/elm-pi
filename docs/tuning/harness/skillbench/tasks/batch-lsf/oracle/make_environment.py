"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

An LSF cluster's user guide, a threaded program and 24 inputs. Nothing can be
submitted where the task runs, so what is asked for is the job script and the
script that submits it, and the check reads them.

What the guide fixes, and a session can only get by reading it:

- the queue is `medium-x` (the others refuse this job) and there is no default;
- the project is `nustruct-25`, required;
- memory: a number without a unit is megabytes, and both the reservation and
  the limit are for the whole job; a job has to give both (nothing reserved is
  scheduled as 1 GB, no limit is the queue's 2 GB);
- LSB_BSUB_PARSE_SCRIPT is at its default, N: bsub reads #BSUB lines only
  from a script on its standard input.

What LSF fixes, and the guide does not spell out: `bsub < job.sh`,
span[hosts=1] to keep a threaded job's slots on one host, the array in the
job name with %N, -W as [hours:]minutes, $LSB_JOBINDEX and $LSB_DJOB_NUMPROC.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

ISOTOPES = ["Ca48", "Ti50", "Cr52", "Fe54", "Ni56", "Ni58", "Zn64", "Ge70"]
INTERACTIONS = ["gxpf1a", "kb3g", "jun45"]
labels = ["%s_%s" % (isotope, interaction) for isotope in ISOTOPES for interaction in INTERACTIONS]
N_INPUTS = len(labels)
assert N_INPUTS == 24
(out / "inputs.txt").write_text("\n".join(labels) + "\n")

(out / "spectra.py").write_text('''#!/usr/bin/env python3
"""Low-lying spectrum of one isotope with one effective interaction.

    python spectra.py Ca48_gxpf1a

The argument is a label, <isotope>_<interaction>, as listed one to a line in
inputs.txt. Builds the Hamiltonian matrix in the valence space, finds its
lowest states and writes results/<label>.json (the folder is made if it is
not there). Paths are taken relative to the directory the program is started
in.

The matrix work is numpy's and is multithreaded: it runs on as many threads
as OMP_NUM_THREADS says, and on every core of the machine if that is not set.
At production dimension an isotope takes about four hours on 8 cores and
peaks near 27 GB.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

SCALE = {"gxpf1a": 1.00, "kb3g": 0.96, "jun45": 1.07}


def main(label, size=80):
    match = re.fullmatch(r"([A-Z][a-z]?)(\\d+)_(\\w+)", label)
    if not match or match.group(3) not in SCALE:
        sys.exit("not a label: %r" % label)
    mass = int(match.group(2))
    index = np.arange(size)
    matrix = np.diag(0.35 * index * (mass / 48.0) ** -0.3)
    matrix = matrix - SCALE[match.group(3)] * np.cos(0.4 * (index[:, None] - index[None, :])) / (1.0 + np.abs(index[:, None] - index[None, :]))
    levels = np.linalg.eigvalsh(matrix)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (label + ".json")
    target.write_text(json.dumps({"label": label, "excitation_mev": [round(float(v - levels[0]), 4) for v in levels[:6]]}, indent=1) + "\\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
''')

(out / "cluster.md").write_text("""# Skua user guide

Skua is the School of Physics cluster. This copy of the guide is the nuclear
structure group's: the group's own details are filled in where the public
page says "ask your group's computing contact".

- Login: `ssh skua.physics.example.ac.uk`.
- Scheduler: IBM Spectrum LSF Standard Edition 10.1 (Fix Pack 13).
- The login node is for editing, compiling and submitting. Anything that has
  run for more than ten minutes there is killed.

## Queues

| Queue | Longest job | Limits | What it is for |
|---|---|---|---|
| `test-x` | 15 minutes | One job per user | Tests. |
| `medium-x` | 24 hours | Up to 400 slots per group | Production work on the standard hosts. |
| `long-x` | 7 days | Jobs with a run limit of 24 hours or less are rejected | Work that cannot be restarted. Ask first. |
| `gpu-x` | 24 hours | Jobs that ask for no GPU are rejected | The four GPU hosts. |

There is no default queue: a job that names none is rejected. `bqueues`
shows the queues; `bqueues -l <queue>` everything about one.

## Hosts

Standard hosts (`sk001` to `sk064`) have 36 cores and 192 GB each. One slot
is one core.

## Projects

Every job must name the project it is accounted to; the submission check
rejects one that does not (`Project name is required`). The nuclear structure
group's project is `nustruct-25`.

## Memory

- A memory figure given without a unit is in megabytes.
- The memory a job reserves and the memory limit it is given are both for the
  whole job, not for each slot.
- Give both. A job that reserves nothing is scheduled as if it needed 1 GB,
  so hosts fill up and somebody's job is killed for it; a job with no limit
  of its own gets the queue's, which is 2 GB in every queue.
- A job that goes over its limit is killed.

## Run time

A job that gives no run limit gets 30 minutes.

## How this site's LSF is set

For those who know LSF from elsewhere, the settings that differ from site to
site:

| Parameter | Here |
|---|---|
| `LSF_UNIT_FOR_LIMITS` | `MB` |
| `LSB_JOB_MEMLIMIT` | `Y` |
| `RESOURCE_RESERVE_PER_TASK` | `N` |
| `LSB_BSUB_PARSE_SCRIPT` | `N` (the default) |
| `MAX_JOB_ARRAY_SIZE` | `2000` |
| `LSB_STDOUT_DIRECT` | `N` (the default) |

## Storage

| Path | What | Notes |
|---|---|---|
| `/home/$USER` | 30 GB, backed up | Visible on every host. |
| `/data/<group>` | Group space | Visible on every host. Jobs are normally run from here. |
| `$TMPDIR` | Host-local scratch | Made for each job and removed when it ends. |

## Software

Software is provided through environment modules (`module avail`). The
hosts' own Python has no numpy; the scientific Python stack is
`python/3.11-sci`.

## Getting help

`skua-help@example.ac.uk`, with the job ID and the path of the job script.
""")
print("wrote cluster.md, spectra.py and inputs.txt with %d labels" % N_INPUTS)
