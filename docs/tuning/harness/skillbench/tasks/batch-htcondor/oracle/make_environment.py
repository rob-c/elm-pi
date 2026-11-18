"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

An HTCondor pool's user guide, a program, its calibration file and 40 run
files. Nothing can be submitted where the task runs, so what is asked for is
the submit file, the script the job runs and the script that submits, and the
check reads them.

What the guide fixes, and a session can only get by reading it:

- the execute nodes share no filesystem with the submit node: everything a
  job reads has to be sent by HTCondor's file transfer, and the job has to
  use the files where they land, in its scratch directory;
- the accounting group is `group_physics.nuosc`, required;
- the run time is the custom job attribute MaxRuntime, in seconds;
- a job that asks for no memory gets 1024 MB and is held over it.

What HTCondor fixes, and the guide does not spell out: one submit file with
one queue statement over the inputs (not a loop of condor_submit),
max_materialize to cap how many are going, request_memory in megabytes
unless a unit is written, and a log folder that has to exist.
"""
import json
import random
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
rng = random.Random(20261117)

N_INPUTS = 40
RUNS = [4100 + 7 * i + (i * i) % 5 for i in range(N_INPUTS)]      # the verifier has the same line
names = []
for run in RUNS:
    name = "run_%04d.dat" % run
    (out / name).write_text("".join("%d %d\n" % (channel, rng.randrange(0, 400)) for channel in range(16)))
    names.append(name)
(out / "inputs.txt").write_text("\n".join(names) + "\n")
(out / "calib.json").write_text(json.dumps({"gain_kev_per_channel": 2.5, "offset_kev": 1.2, "valid_from_run": 4000}, indent=1) + "\n")

(out / "analyse.py").write_text('''#!/usr/bin/env python3
"""Calibrated spectrum of one run.

    python3 analyse.py run_4100.dat

Reads the run file named on the command line and the calibration, calib.json,
which it looks for in the directory it is started in. Writes
<run>.result.json into that same directory.

Needs Python 3 with numpy. At full size a run takes about 80 minutes on 4
cores and peaks near 6 GB.
"""
import json
import sys
from pathlib import Path

import numpy as np


def main(path):
    calibration = json.loads(Path("calib.json").read_text())
    table = np.loadtxt(path)
    energy = calibration["offset_kev"] + calibration["gain_kev_per_channel"] * table[:, 0]
    counts = table[:, 1]
    mean = float((energy * counts).sum() / counts.sum())
    target = Path(Path(path).stem + ".result.json")
    target.write_text(json.dumps({"run": Path(path).stem, "counts": int(counts.sum()), "mean_energy_kev": mean}, indent=1) + "\\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
''')

(out / "cluster.md").write_text("""# Physics computing pool: user guide

The Department of Physics pool: about 1,900 cores on machines in the server
room and, overnight, on the teaching laboratories' desktops. This copy of the
guide is the neutrino oscillation group's: the group's own details are
filled in where the public page says "ask your group's computing contact".

- Submit node: `ssh pool-submit.physics.example.ac.uk`. Jobs are submitted
  from there and nowhere else.
- Scheduler: HTCondor 23.0.12.
- The submit node is for editing, small tests and submitting. Anything that
  has used more than ten minutes of CPU there is killed.

## The execute nodes

- They share no filesystem with the submit node. `/home` and `/data` are not
  mounted on them, and they cannot reach the submit node by `scp` or `rsync`.
  What a job needs has to be sent with it, and what it produces brought
  back, by HTCondor itself.
- Rocky Linux 9, with `/usr/bin/python3` (Python 3.11 with numpy, scipy and
  pandas) and a C++ compiler. There are no environment modules, and nothing
  of your login environment is there: no home directory, no shell start-up
  files, none of your variables.
- The largest slot a job can have is 16 cores and 64 GB.

## What every job must say

- **Its accounting group.** A job with none is rejected at submission
  (`accounting_group is required`). The neutrino oscillation group's is
  `group_physics.nuosc`.
- **How long it may run**, in seconds, in the job attribute `MaxRuntime`.
  This is the pool's own attribute, not one of HTCondor's. A job that does
  not set it is removed after 20 minutes, and one that sets more than 72
  hours is rejected.

## What a job gets if it does not ask

| | If not asked for | Over the request |
|---|---|---|
| Cores | 1 | The job is held to what it asked for. |
| Memory | 1024 MB | The job is put on hold. |
| Disk | 4 GB of scratch | The job is put on hold. |

## Being a good neighbour

The desktops leave the pool at 08:00 and whatever is running on them is
evicted and starts again elsewhere. Please keep the number of your jobs
that are idle or running in the hundreds, not the tens of thousands:
`condor_q` is slow for everybody when the queue is long.

## Storage

| Path | Where | Notes |
|---|---|---|
| `/home/$USER` | Submit node only | 20 GB, backed up. |
| `/data/<group>` | Submit node only | Group space. Jobs are normally submitted from here. |
| The job's scratch directory | Execute node | Made for each job, removed when it ends. |

## Getting help

`pool-help@physics.example.ac.uk`, with the cluster ID of the job and the
path of the submit file.
""")
print("wrote cluster.md, analyse.py, calib.json, inputs.txt and %d run files" % N_INPUTS)
