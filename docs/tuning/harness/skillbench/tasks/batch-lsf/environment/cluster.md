# Skua user guide

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
