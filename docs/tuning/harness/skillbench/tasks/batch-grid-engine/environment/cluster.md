# Tarn user guide

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
