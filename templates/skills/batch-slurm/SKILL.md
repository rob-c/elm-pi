---
name: batch-slurm
description: "Slurm jobs - sbatch scripts, tasks versus cpus-per-task, memory per node or per CPU, GPUs, job arrays with a throttle, dependencies, and squeue, sacct and seff to see what happened."
disable-model-invocation: true
---

# Slurm

The usual mistakes: `--ntasks=8` for an 8-thread program (it gets one core
and seven idle tasks); `--mem` taken as per core (it is per node); an array
without a throttle; a log path whose folder does not exist; and "submitted"
reported as "ran". Site names (partition, account, QOS, GPU type) come from
`sinfo -s`, `sacctmgr show assoc user=$USER` and the cluster's guide.

## A script

```bash
#!/bin/bash
#SBATCH --job-name=fit
#SBATCH --partition=<from sinfo>
#SBATCH --account=<if the site needs one>
#SBATCH --time=02:00:00              # D-HH:MM:SS also; minutes if a bare number
#SBATCH --nodes=1
#SBATCH --ntasks=1                   # MPI ranks
#SBATCH --cpus-per-task=8            # threads per rank
#SBATCH --mem=16G                    # per node; or --mem-per-cpu=2G, never both
#SBATCH --array=1-200%20             # 200 tasks, at most 20 at once
#SBATCH --output=logs/%x_%A_%a.out   # %x name, %A array job, %a index; %j for a plain job
set -euo pipefail
module purge; module load <what the job needs>
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
input=$(sed -n "${SLURM_ARRAY_TASK_ID}p" inputs.txt)
srun --cpus-per-task="$SLURM_CPUS_PER_TASK" ./analyse "$input"
```

- All `#SBATCH` lines come before the first command; later ones are ignored.
- The job starts in the directory it was submitted from, with the submitting
  shell's environment unless `--export=NONE`: hence `module purge`.
- `mkdir -p logs` before `sbatch`: a missing output folder fails the job at
  once with no log to say why.
- Threads: `--cpus-per-task`. MPI: `--ntasks` (and `--nodes` or
  `--ntasks-per-node`), launched with `srun`. Since Slurm 22.05 `srun` does
  not inherit `--cpus-per-task` from `sbatch`: pass it, as above.
- GPUs: `--gres=gpu:1` or `--gpus=1`, with the type if the site has several
  (`--gres=gpu:a100:1`); check with `nvidia-smi` in the job.
- Memory with a unit (`16G`); a bare number is megabytes.

## Submitting and following

- `sbatch job.sh` prints the job ID; `sbatch --parsable` prints only it, for
  chaining: `sbatch --dependency=afterok:<id> next.sh`.
- Interactive: `salloc` with the same options, or
  `srun --pty --time=30 --cpus-per-task=2 bash`.
- `squeue --me` (states PD pending, R running; the last column says why it is
  pending). `scontrol show job <id>` for everything about a queued or running
  job. `scancel <id>`, `scancel <id>_<index>` for one array task.
- When it has finished - this is the report, not the submission:
  `sacct -j <id> --format=JobID,State,ExitCode,Elapsed,ReqMem,MaxRSS,AllocCPUS,TotalCPU`.
  States to act on: FAILED (read the log), TIMEOUT (more time, or
  checkpoint), an out-of-memory state (more memory: MaxRSS was near ReqMem),
  CANCELLED. `seff <id>`, where installed, gives CPU and memory efficiency.
- Rerun only the failed array tasks: `sbatch --array=7,31,58 job.sh`.

## Pitfalls

- A step that runs longer than `--time` is killed with TERM then KILL: trap
  the signal to copy results off scratch, or ask for a warning with
  `--signal=B:USR1@120`.
- `--exclusive` and whole-node requests wait far longer than they need to.
- Arrays have a site limit on size (MaxArraySize): split, or pack several
  short inputs into each task.
- Do not loop `squeue` every second; `sacct` or `--wait` for scripts.
- Local scratch is the site's choice of variable (often TMPDIR): look.

## Check before reporting

- Every directive is before the first command; partition, account and GPU
  names were read from the site.
- Threads, ranks and memory match what the program does; `srun` was given
  the CPU count.
- `sacct` shows COMPLETED with exit code 0:0 for every task, and MaxRSS and
  Elapsed are quoted against what was requested.

## Related

- Skills here: `batch-jobs`, `batch-grid-engine`, `batch-pbs`, `batch-lsf`,
  `batch-htcondor`, `containers`, `installing-software`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `optimize-for-gpu`, `nextflow`.
