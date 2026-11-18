"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A PBS Professional cluster's user guide, a threaded program and 60 inputs.
Nothing can be submitted where the task runs, so what is asked for is the job
script and the script that submits it, and the check reads them.

What the guide fixes, and a session can only get by reading it:

- it is PBS Professional 2022.1, not Torque: `select` chunks, `-J` arrays
  (with %N to throttle), $PBS_ARRAY_INDEX;
- the queue is `std-d` (the others refuse this job) and there is no default;
- the account string is `NUCS0421`, required.

What PBS fixes, and the guide does not spell out: a job starts in the home
directory, so the script changes to $PBS_O_WORKDIR; `mem` is per chunk; a
bare walltime number is seconds; and the folder of the output path has to
exist for the logs to be delivered.
"""
import random
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
(out / "data").mkdir(exist_ok=True)
rng = random.Random(20261117)

N_INPUTS = 60
names = []
for number in sorted(rng.sample(range(2000, 3000), N_INPUTS)):
    name = "data/evt_%04d.dat" % number
    (out / name).write_text("".join("%d %.2f %.2f\n" % (rng.randrange(1, 9), rng.uniform(-40, 40), rng.uniform(-40, 40))
                                    for _ in range(12)))
    names.append(name)
(out / "inputs.txt").write_text("\n".join(names) + "\n")

(out / "reco.py").write_text('''#!/usr/bin/env python3
"""Track reconstruction for one event file.

    python reco.py --threads 4 data/evt_2417.dat

Fits a straight track to the hits of the file (plane, x, y on each line) and
writes results/<name>.json (the folder is made if it is not there). Paths are
taken relative to the directory the program is started in.

--threads is required: the number of worker threads the fit may use. Give it
the number of cores the job has, no more. A full-size file takes about an
hour on 4 cores and peaks near 9 GB.
"""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Track reconstruction for one event file.")
    parser.add_argument("--threads", type=int, required=True, help="worker threads: the cores the job has")
    parser.add_argument("file")
    options = parser.parse_args()
    if options.threads < 1:
        parser.error("--threads must be at least 1")
    os.environ["OMP_NUM_THREADS"] = str(options.threads)
    import numpy as np

    hits = np.loadtxt(options.file)
    slope_x, offset_x = np.polyfit(hits[:, 0], hits[:, 1], 1)
    slope_y, offset_y = np.polyfit(hits[:, 0], hits[:, 2], 1)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (Path(options.file).stem + ".json")
    target.write_text(json.dumps({"file": options.file, "hits": int(len(hits)), "threads": options.threads,
                                  "x": [float(slope_x), float(offset_x)], "y": [float(slope_y), float(offset_y)]},
                                 indent=1) + "\\n")
    print("wrote", target)


if __name__ == "__main__":
    main()
''')

(out / "cluster.md").write_text("""# Osprey user guide

Osprey is the national facility's mid-range cluster. This copy of the guide
is our group's: the allocation details are filled in where the public page
says "see your award letter".

- Login: `ssh osprey.hpc.example.org` (`osprey-login1` to `osprey-login3`).
- Scheduler: PBS Professional 2022.1.3.
- The login nodes are for editing, compiling and submitting. Processes that
  use more than fifteen minutes of CPU there are killed.

## Queues

| Queue | Longest job | Limits | What it is for |
|---|---|---|---|
| `express-d` | 20 minutes | One job per user, running or queued | Tests. |
| `std-d` | 24 hours | Up to 2000 cores per group | Production work on the standard nodes. |
| `long-d` | 7 days | Jobs asking for 24 hours or less are rejected | Work that cannot be checkpointed. Ask first. |
| `bigmem-d` | 24 hours | Jobs asking for less than 180 GB are rejected | The four 1.5 TB nodes. |
| `gpu-d` | 24 hours | Jobs that ask for no GPU are rejected | The A100 nodes. |

There is no default queue: a job that names none is rejected at submission.
`qstat -Q` shows the queues and what is in them.

## Nodes

Standard nodes (`os0001` to `os0412`) have 40 cores and 192 GB each.
Hyperthreading is off.

## Accounts

Every job must carry the allocation it is charged to as its account string,
and one submitted without is rejected (`qsub: Account_Name is required`).
Our allocation's account string is `NUCS0421`.

## What a job gets

- A job is confined to the cores and memory it asked for (cgroups) and is
  killed if it goes over its memory.
- A job that does not say gets 1 core, 2 GB and a walltime of one hour.
- Job arrays may have up to 1000 sub-jobs. A group's running jobs share its
  2000 cores, so keep a wide array from taking them all.

## Storage

| Path | What | Notes |
|---|---|---|
| `/home/$USER` | 50 GB, backed up | Visible on every node. |
| `/project/<allocation>` | Project space | Visible on every node. Jobs are normally run from here. |
| `$TMPDIR` | Node-local scratch | Made for each job and removed when it ends. |
| `/scratch/$USER` | Shared scratch | Files older than 60 days are deleted. |

## Software

Software is provided through environment modules (`module avail`). The
compute nodes' own Python has no numpy; the scientific Python stack is
`python/3.11-sci`.

## Getting help

`osprey-support@example.org`, with the job ID (`1234567.osprey-pbs`, or
`1234567[].osprey-pbs` for an array) and the path of the job script.
""")
print("wrote cluster.md, reco.py, inputs.txt and %d files in data/" % N_INPUTS)
