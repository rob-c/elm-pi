---
name: batch-jobs
description: "Running work on a university cluster's batch system - which scheduler it is, a job script, resource requests, job arrays, scratch, checkpoints, and reading what a finished job used."
disable-model-invocation: true
---

# Batch jobs on a shared cluster

What goes wrong, most often first: one scheduler's directives or syntax
written for another (they are comments, so nothing complains and the
defaults are used); a threaded program never told how many cores it has;
work run on the login node; a loop of submissions where one array would do;
memory or time guessed.

## First: which scheduler - then read its skill

Do not assume: look, at the commands on the machine or in the site's guide.
Then read that scheduler's skill before writing a line -
`@AGENT_DIR@/skills/<name>/SKILL.md` - because the dialects differ in
exactly the lines a job script is made of:

| Commands | Scheduler: skill | N tasks, M at once | C cores, one node | Cores given |
|---|---|---|---|---|
| `sbatch`, `squeue` | Slurm: `batch-slurm` | `--array=1-N%M` | `--cpus-per-task=C` | `$SLURM_CPUS_PER_TASK` |
| `qsub`, `qconf`, `qacct` | Grid Engine (SGE, Univa): `batch-grid-engine` | `-t 1-N`, `-tc M` | `-pe <site's> C` | `$NSLOTS` |
| `qsub`, `pbsnodes` | PBS Pro, OpenPBS, Torque: `batch-pbs` | `-J 1-N%M` | `-l select=1:ncpus=C` | `$NCPUS` |
| `bsub`, `bjobs` | LSF: `batch-lsf` | `-J "name[1-N]%M"` | `-n C -R "span[hosts=1]"` | `$LSB_DJOB_NUMPROC` |
| `condor_submit`, `condor_q` | HTCondor: `batch-htcondor` | `queue ... from`, `max_materialize = M` | `request_cpus = C` | set for the job |

**Porting a script to another scheduler: rewrite it, do not translate.**
Look every old line up afresh in the new row and the new scheduler's skill;
a line that survives unchanged is suspect. Grid Engine and PBS share `qsub`
and little else: Grid Engine wants `-cwd` (not `cd $PBS_O_WORKDIR`), `-j y`
(not `-j oe`), `-tc M` (no `%M`) and memory per slot. HTCondor has no job
script at all: a submit file, and nothing shared with the node unless the
site says so. Others: Moab (`msub`), OAR (`oarsub`), Flux (`flux batch`),
DIRAC, ARC. Every site-specific name - queue, account or project, parallel
environment, GPU resource, scratch path, module - comes from the cluster's
guide or the scheduler. Never invent one.

## The rules every scheduler shares

1. **Login nodes are for editing and submitting.** Anything over a minute
   or one core goes through the scheduler.
2. **One small job first.** Read what it used (time, peak memory) from the
   accounting and size the real request from that, plus 20-50%. Requests
   are limits: over memory or time, the job is killed.
3. **Tell the program its cores.** A threaded program (OpenMP, numpy's BLAS)
   told nothing starts a thread for every core of the node, not of the job:
   every job script sets `OMP_NUM_THREADS`, or the program's own option,
   from the last column above. A serial program given 16 cores uses one;
   MPI needs tasks and the site's launcher; a GPU job the GPU requested.
4. **Many similar jobs are one array job**, capped, not a loop of
   submissions. Map the index to line N of a file list, so a failed index
   can be rerun alone.
5. **Say where output goes, and make the folder before submitting.** Most
   schedulers fail or hold a job whose log directory does not exist.
6. **Start clean**: modules loaded in the script, the working directory
   set explicitly.
7. **Heavy I/O on node-local scratch**, results copied back at the end and
   in a `trap` on the termination signal.
8. **Long work checkpoints**: a chain of restartable jobs.
9. **Be a neighbour.** Poll the queue once a minute at most.

## A job script, whatever the dialect

In this order: shebang; every directive, in one block, before any command -
`set -euo pipefail` included, since Slurm and PBS stop reading at the first
command; then strict mode, modules, the work directory, the thread count,
and the command.

## Check before reporting

- The scheduler was identified from its commands, and site names (queue,
  account, GPU resource) were read from the site, not guessed.
- Directives are this scheduler's, all before the first command.
- Cores, memory and time from a measured test job; memory per core or
  per job is the scheduler's choice - they differ.
- An array with a cap for repeated work; log folder exists; thread count set.
- After the run: state, exit code, elapsed time and peak memory from the
  accounting command, for every array task - not "it was submitted".
- Nothing was run on the login node; nothing is left queued by mistake.

## Related

- Skills here: `batch-slurm`, `batch-grid-engine`, `batch-pbs`, `batch-lsf`,
  `batch-htcondor`, `installing-software`, `containers`, `scientific-python`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `nextflow`, `dask`.
