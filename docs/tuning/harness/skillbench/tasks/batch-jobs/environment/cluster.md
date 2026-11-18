# Marten user guide

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
