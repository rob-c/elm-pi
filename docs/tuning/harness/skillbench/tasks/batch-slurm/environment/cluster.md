# Kestrel user guide

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
