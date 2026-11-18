---
name: batch-lsf
description: "IBM Spectrum LSF jobs - bsub scripts read from standard input, slots and span, memory reservation versus limit, job arrays, and bjobs, bhist and bacct to see what happened."
disable-model-invocation: true
---

# LSF (IBM Spectrum LSF)

The usual mistakes: `bsub job.sh` instead of `bsub < job.sh`, so every
`#BSUB` line is ignored and the job runs with the defaults; `-n 8` without
`span[hosts=1]`, so a threaded program gets its eight slots on three hosts;
memory reserved but not limited, or the other way round; and memory given in
the wrong unit, which is the site's choice.

## A script

```bash
#!/bin/bash
#BSUB -J "fit[1-200]%20"             # array of 200, at most 20 at once
#BSUB -q <queue, from bqueues>
#BSUB -P <project, if the site needs one>
#BSUB -n 8                           # slots
#BSUB -R "span[hosts=1]"             # ... all on one host
#BSUB -R "rusage[mem=2GB]"           # reserve: what the scheduler sets aside
#BSUB -M 2GB                         # limit: what the job is killed at
#BSUB -W 02:00                       # HH:MM; a bare number is minutes
#BSUB -o logs/%J_%I.out              # %J job ID, %I array index
#BSUB -e logs/%J_%I.err
set -euo pipefail
module purge; module load <what the job needs>
export OMP_NUM_THREADS=$LSB_DJOB_NUMPROC
input=$(sed -n "${LSB_JOBINDEX}p" inputs.txt)
./analyse "$input"
```

Submit with `mkdir -p logs && bsub < job.sh`. The redirect is what makes LSF
read the `#BSUB` lines.

- **Memory.** `rusage[mem=..]` reserves and `-M` limits: give both. Whether
  the number is per slot or per job, and the unit of a bare number (MB, KB or
  GB), are set by the site (`LSF_UNIT_FOR_LIMITS`; `bqueues -l <queue>` and
  the guide say which). Write the unit; if the site's LSF is too old to take
  one, convert to its unit.
- **Slots.** `-n 8` is eight slots anywhere; `span[hosts=1]` for threads,
  `span[ptile=N]` for N per host with MPI. MPI is launched with the site's
  integrated launcher (`mpirun` built for LSF, or `jsrun` on some systems).
- **GPUs.** `-gpu "num=1"` on current versions; older sites use a resource
  requirement (`rusage[ngpus_physical=1]`) or a queue.
- **Time.** Without `-W` the queue's default applies; `-We` is an estimate,
  not a limit.
- The job starts in the submission directory with the submitting
  environment (`-env "none"` starts clean): hence `module purge`.
- In the job: `$LSB_JOBID`, `$LSB_JOBINDEX`, `$LSB_DJOB_NUMPROC` (slots),
  `$LSB_HOSTS`.

## Submitting and following

- `bsub < job.sh` prints `Job <id> is submitted to queue <q>`. Chain with
  `-w "done(<id>)"`. Interactive: `bsub -Is -n 2 -W 30 bash`.
- `bjobs -u "$USER"`: PEND, RUN, DONE, EXIT, and the suspended states.
  `bjobs -l <id>` gives the pending reasons and the resource usage so far;
  `bjobs -A` summarises arrays; one task is `<id>[7]` (quote it in a shell).
- `bpeek <id>` shows a running job's output. `bkill <id>`, `bkill "<id>[7]"`,
  `bkill 0` for all of yours. `bmod` changes a pending job.
- When it has finished - this is the report, not the submission:
  `bhist -l <id>` (what happened, in order) and `bacct -l <id>` (CPU time,
  wall time, `MAX MEM`, exit code). EXIT with code 130 or a "memory limit"
  termination reason means the limit was hit; "run limit" means `-W`; other
  codes are the program's. The summary appended to the `-o` file gives the
  same figures per task.
- `bqueues` and `bqueues -l <queue>` list queues and limits; `bhosts` and
  `lshosts` the nodes and their resources.

## Pitfalls

- An `-o` file is appended to, not replaced; `-oo` overwrites.
- Without `-o` the output is mailed, which on most clusters means lost.
- Array size and the number of pending jobs have site limits.
- Job names over the array syntax need quotes: `"name[1-200]%20"`.

## Check before reporting

- The script went in through `bsub <`, and `bjobs -l` shows the requested
  slots, span, memory and limit - not the defaults.
- Queue, project, GPU syntax and the memory unit were read from this site.
- `bacct` shows every task DONE with the wall time and maximum memory quoted
  against the request; EXIT tasks have their reason.

## Related

- Skills here: `batch-jobs`, `batch-slurm`, `batch-grid-engine`,
  `batch-pbs`, `batch-htcondor`, `installing-software`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `nextflow`.
