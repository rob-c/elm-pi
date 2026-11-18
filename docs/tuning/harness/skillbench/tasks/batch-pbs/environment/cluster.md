# Osprey user guide

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
