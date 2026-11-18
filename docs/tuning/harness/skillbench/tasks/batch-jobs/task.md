---
skill: batch-jobs
also: batch-grid-engine
category: batch
pitfall: the old scheduler's #PBS directives and $PBS_ variables carried over because the command is still qsub (they are comments to Grid Engine, so the job runs on one slot with the defaults); memory kept as the job's total where the new limit is per slot; the parallel environment guessed
timeout_sec: 600
---
We have moved to a new cluster, and cluster.md is its user guide. old_job.sh is how I ran this on the old one. Port it: the same job array over inputs.txt with the same 12 cores, 24 GB of memory in total, 3 hours and 4 at a time, logs still in logs/. Write job.sh and a submit.sh that submits it.
