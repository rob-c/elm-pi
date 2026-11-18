---
name: batch-pbs
description: "PBS jobs (PBS Professional, OpenPBS, Torque with or without Moab) - qsub scripts, select and ncpus versus nodes and ppn, walltime, array jobs, and qstat and tracejob to see what happened."
disable-model-invocation: true
---

# PBS (PBS Professional, OpenPBS, Torque)

Two families share the name and the commands, and differ exactly where a
script is written: PBS Professional and OpenPBS use `select` chunks and `-J`
arrays; Torque (often with Moab or Maui) uses `nodes=..:ppn=..` and `-t`
arrays. One family's resource line is rejected or misread by the other. The
other usual mistakes: the job runs in `$HOME` because nothing changed
directory, and Grid Engine options are tried because the command is `qsub`.

Which one: `qstat --version` (`pbs_version = 20...` or `22...` is PBS
Professional or OpenPBS; `Version: 6...` or lower is Torque); `pbsnodes`
exists in both and not in Grid Engine; `msub` or `showq` means Moab.

## A script - PBS Professional / OpenPBS

```bash
#!/bin/bash
#PBS -N fit
#PBS -q <queue>
#PBS -A <account or project, if the site needs one>
#PBS -l select=1:ncpus=8:mem=16gb     # 1 chunk of 8 cores and 16 GB; :ngpus=1 for a GPU
#PBS -l walltime=02:00:00
#PBS -J 1-200                         # array; index in $PBS_ARRAY_INDEX
#PBS -j oe
#PBS -o logs/
set -euo pipefail
cd "$PBS_O_WORKDIR"                   # the job starts in $HOME otherwise
module purge; module load <what the job needs>
export OMP_NUM_THREADS=$NCPUS
input=$(sed -n "${PBS_ARRAY_INDEX}p" inputs.txt)
./analyse "$input"
```

- `select=N:ncpus=C:mpiprocs=M:mem=..` is N chunks, each with C cores; `mem`
  is per chunk. MPI across nodes: `select=4:ncpus=32:mpiprocs=32`, and
  `-l place=scatter` or `pack`.
- Array throttle: `-J 1-200%20` on recent versions; older ones need
  `max_run_subjobs` (`qsub -W max_run_subjobs=20`) - check `man qsub`.

## The same job - Torque

```bash
#PBS -l nodes=1:ppn=8,mem=16gb,walltime=02:00:00
#PBS -t 1-200%20                      # array with throttle; index in $PBS_ARRAYID
```

- `mem` is for the job, `pmem` per process; GPUs are `nodes=1:ppn=8:gpus=1`.
- With Moab, `msub` takes the same script; `checkjob <id>` explains waits.

## Both

- Directives are `#PBS` lines before the first command.
- `-V` exports the whole submitting environment; prefer loading modules in
  the script, or `-v NAME=value`.
- In the job: `$PBS_JOBID`, `$PBS_O_WORKDIR` (where `qsub` was run),
  `$PBS_NODEFILE` (hosts, for MPI launchers), `$TMPDIR` (local scratch).

## Submitting and following

- `mkdir -p logs && qsub job.sh` prints the job ID (`1234.server`, arrays
  `1234[].server`). Chain: `qsub -W depend=afterok:<id> next.sh`.
  Interactive: `qsub -I` with the same `-l` lines.
- `qstat -u "$USER"`: `Q` queued, `R` running, `H` held, `E` exiting;
  `qstat -t` or `qstat -J -t` to see array sub-jobs. `qstat -f <id>` shows
  everything, including the `comment` that says why a job is not running.
- `qdel <id>`; one sub-job is `qdel "1234[7].server"` (Torque: `1234-7`).
- When it has finished - this is the report, not the submission:
  PBS Professional keeps history: `qstat -xf <id>` gives `Exit_status`,
  `resources_used.walltime`, `resources_used.mem`, `resources_used.cput`.
  Torque: `tracejob <id>` (if permitted) or the epilogue in the output file.
  Exit status 271 or -11 is the walltime limit; 137, or a memory figure at
  the request, the memory limit; small positive numbers are the program's.
- `qstat -Q` lists queues and their limits; `pbsnodes -a` the nodes.

## Check before reporting

- The family was identified, and the resource line is that family's.
- Queue, account and GPU names were read from the site (`qstat -Q`, guide).
- The script changes to `$PBS_O_WORKDIR`; the log folder exists; arrays are
  throttled.
- Every sub-job's exit status is 0, with wall time and memory used quoted
  against the request.

## Related

- Skills here: `batch-jobs`, `batch-slurm`, `batch-grid-engine`,
  `batch-lsf`, `batch-htcondor`, `installing-software`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `nextflow`.
