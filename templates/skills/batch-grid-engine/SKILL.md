---
name: batch-grid-engine
description: "Grid Engine jobs (SGE, Son of Grid Engine, Univa and Altair Grid Engine) - qsub scripts, parallel environments, per-slot memory, array jobs, and qstat and qacct to see what happened."
disable-model-invocation: true
---

# Grid Engine (SGE, Son of Grid Engine, Univa/Altair Grid Engine)

The usual mistakes: Slurm or PBS options given to `qsub` (it is not PBS:
check for `qconf`); memory asked for the job when the limit is per slot; a
parallel environment name copied from another site; the job starting in the
home directory because `-cwd` was left out; and a job stuck in `Eqw` because
its log folder did not exist.

## A script

```bash
#!/bin/bash
#$ -N fit
#$ -S /bin/bash
#$ -cwd                      # start where it was submitted, not in $HOME
#$ -q <queue, if the site wants one>
#$ -P <project, if the site needs one>
#$ -pe smp 8                 # 8 slots on one host; the name is the site's
#$ -l h_rt=02:00:00          # hard wall-clock limit
#$ -l h_vmem=2G              # PER SLOT: 8 slots x 2G = 16G for the job
#$ -t 1-200                  # array job
#$ -tc 20                    # at most 20 tasks at once
#$ -o logs/ -e logs/         # or -j y to merge them
set -euo pipefail
module purge; module load <what the job needs>
export OMP_NUM_THREADS=$NSLOTS
input=$(sed -n "${SGE_TASK_ID}p" inputs.txt)
./analyse "$input"
```

- Directives are `#$` lines before the first command.
- **Parallel environments are site-defined.** `qconf -spl` lists them and
  `qconf -sp <name>` shows the allocation rule: one host (often `smp`,
  `threaded`, `shmem`) for threads, several hosts (`mpi`, `orte`) for MPI.
  Without `-pe` the job has one slot whatever the program starts.
- **Memory is per slot and site-specific.** `h_vmem` limits virtual memory
  per slot and kills at the limit; programs that map much more than they use
  (Java, Python with big libraries) need headroom. Univa/Altair sites often
  use `m_mem_free` (enforced on real memory by cgroups) instead. `qconf -sc`
  lists the resources a site defines; its guide says which to request.
- Arrays: `-t first-last:step`; the index is `$SGE_TASK_ID`. `-tc` caps the
  running tasks.
- `-V` copies the whole submitting environment; prefer loading what is
  needed in the script, or `-v NAME=value` for single variables.
- GPUs are a site resource (`-l gpu=1`, `-l gpus=1`, a queue): read the guide.
- In the job: `$JOB_ID`, `$NSLOTS`, `$TMPDIR` (node-local scratch, removed at
  the end), `$PE_HOSTFILE` for MPI launchers.

## Submitting and following

- `mkdir -p logs && qsub job.sh` prints the job ID. Chain with
  `-hold_jid <id>`. Interactive: `qlogin` or `qrsh` with the same `-l`/`-pe`.
- `qstat -u "$USER"`: `qw` waiting, `r` running, `hqw` held, `Eqw` error.
  `qstat -j <id>` says why a job waits or what the error was; after fixing
  the cause, `qmod -cj <id>` clears `Eqw`, or delete and resubmit.
- `qdel <id>`, `qdel <id> -t 7` for one task. `qalter` changes a queued job.
- When it has finished - this is the report, not the submission:
  `qacct -j <id>` (add `-t <n>` for one task) gives `exit_status`, `failed`,
  `ru_wallclock`, `maxvmem`. A non-zero `failed` is the scheduler's doing
  (limits, a lost host), a non-zero `exit_status` the program's: 137 or a
  `maxvmem` at the request means the memory limit, wall clock at `h_rt`
  means the time limit.
- `qhost` and `qconf -sql` show hosts and queues; `qstat -g c` their load.

## Pitfalls

- Univa/Altair add options (`-binding`, `m_mem_free`, `-l gpu` handling)
  that open-source SGE lacks; `qstat -help` prints the product and version.
- `s_rt` (soft limit, sends USR1 first) set below `h_rt` gives time to copy
  results off `$TMPDIR`; trap it.
- A reservation (`-R y`) keeps large parallel jobs from starving.
- The default shell may be csh unless `-S` or the queue says otherwise.

## Check before reporting

- It is Grid Engine (`qconf` exists), and the PE, queue, project and memory
  resource names were read from this site.
- Memory request times slots is what the job needs; `-cwd` and the log
  folder are in place; arrays have `-tc`.
- `qacct` shows `failed 0` and `exit_status 0` for every task, with
  `maxvmem` and wall clock quoted against the request.

## Related

- Skills here: `batch-jobs`, `batch-slurm`, `batch-pbs`, `batch-lsf`,
  `batch-htcondor`, `installing-software`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `nextflow`.
