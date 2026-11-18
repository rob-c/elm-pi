# Physics computing pool: user guide

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
