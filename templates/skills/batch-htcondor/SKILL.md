---
name: batch-htcondor
description: "HTCondor jobs - submit description files, queue statements for many jobs, file transfer and the scratch directory, resource requests, held jobs, and condor_q and condor_history to see what happened."
disable-model-invocation: true
---

# HTCondor

HTCondor is not a batch queue with different spelling. A job is described in
a submit file, not by comments in a script; it may run on a machine that
shares no filesystem with the one it was submitted from; and when something
is wrong it is held, not failed. The usual mistakes: a script that reads
paths the worker cannot see; a shell loop of submissions where one `queue`
statement would do; no memory request, so the default is too small and the
job is held; and a log folder that does not exist.

## A submit file

```
executable              = run.sh
arguments               = $(infile)
output                  = logs/$(Cluster).$(Process).out
error                   = logs/$(Cluster).$(Process).err
log                     = logs/$(Cluster).log
request_cpus            = 4
request_memory          = 8GB
request_disk            = 10GB
should_transfer_files   = YES
when_to_transfer_output = ON_EXIT
transfer_input_files    = analyse.py, calib.json, $(infile)
max_materialize         = 50
max_retries             = 2
queue infile from inputs.txt
```

`mkdir -p logs && condor_submit job.sub`.

- **`queue` makes the jobs, and is the last line**: a command written after
  it (output, error, log) does not apply to them. `queue 200` runs 200 with
  `$(Process)` from 0 to 199; `queue infile from inputs.txt` one per line;
  `queue infile matching files data/*.root` one per file. One cluster, one
  submission - never a loop of `condor_submit`.
- **Files.** With transfer on, the executable and the listed inputs - the
  program `run.sh` calls is one of them - are copied to a scratch directory
  on the worker, the job runs there, and new
  files in that directory's top level come back (or exactly those in
  `transfer_output_files`). Use paths relative to the scratch directory in
  the script; an absolute path works only on a site with a shared
  filesystem - ask, do not assume. Large inputs come from the site's storage
  (XRootD, a shared mount), not through transfer.
- **Requests.** `request_memory` defaults to megabytes and to a small site
  default; a job that exceeds it is held or evicted. `request_gpus = 1` for
  a GPU. Run-time limits are the site's attribute: `+MaxRuntime` in seconds
  or `+JobFlavour` at CERN, others elsewhere - read the guide. The `+` is
  for such site attributes only: `accounting_group = name` is a submit
  command and takes none.
- **Environment.** The job does not get your login environment. Set it up
  in `run.sh` (strict mode, `source` the setup, then the command), or use a
  container: `universe = container` with `container_image = ...`.
  `getenv = True` copies the submitting shell's environment and breaks as
  soon as the worker differs.
- `max_materialize` caps how many jobs are in the queue at once;
  `max_retries` reruns a job whose executable exits non-zero.

## Following and finishing

- `condor_q` (yours, batched); `condor_q -nobatch` one line per job: `I`
  idle, `R` running, `H` held. `condor_q -hold` prints why a job is held
  (a missing input file, memory over the request, an output folder that is
  not there); fix the cause, then `condor_release <id>` - or
  `condor_qedit <id> RequestMemory 16000` first.
- `condor_q -better-analyze <id>` says why an idle job matches no machine
  (too much memory or disk asked, a requirement nothing satisfies).
- `condor_rm <id>` or `condor_rm <cluster>`; `condor_ssh_to_job <id>` to
  look inside a running job; `condor_wait logs/<cluster>.log` to block until
  all are done; `condor_status -compact` for what the pool has.
- When it has finished - this is the report, not the submission:
  `condor_history <cluster> -af ProcId ExitCode RemoteWallClockTime
  MemoryUsage RequestMemory`. The `log` file has the same per job (return
  value, memory in MB, bytes transferred). An exit code of 0 for every
  process, not the absence of the cluster from `condor_q`, is success.
- Jobs that depend on each other are a DAG: `condor_submit_dag flow.dag`,
  with `RETRY` and a rescue file for restarting where it failed.

## Check before reporting

- One submit file with a `queue` statement; resources requested; logs
  folder made; inputs either transferred or on storage the workers see.
- No job left held: every hold reason read and dealt with.
- `condor_history` shows exit code 0 for every process, with memory and
  wall-clock time quoted against the request.

## Related

- Skills here: `batch-jobs`, `batch-slurm`, `batch-grid-engine`,
  `batch-pbs`, `batch-lsf`, `containers`, `hep-data-formats`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `nextflow`.
