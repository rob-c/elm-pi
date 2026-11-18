---
skill: batch-grid-engine
also: batch-jobs
category: batch
pitfall: h_vmem set to the job's total where the limit is per slot; a parallel environment name from another site (smp); no -cwd, so the job and its logs start from the home directory; the project left out; logs/ not made before qsub
timeout_sec: 600
---
cluster.md is the user guide for our cluster. Run fit_bands.py once for each of the 30 lines of inputs.txt: each run needs 6 cores, 24 GB of memory in total and up to 4 hours, and at most 5 should run at the same time. Write job.sh and a submit.sh that submits it, with the job logs going into logs/.
