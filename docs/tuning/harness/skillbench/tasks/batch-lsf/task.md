---
skill: batch-lsf
also: batch-jobs
category: batch
pitfall: submitted as `bsub job.sh`, so no #BSUB line is read; -n 8 without span[hosts=1], so the threads' slots may be on several hosts; memory reserved but not limited (or the reverse); the queue and project guessed
timeout_sec: 600
---
cluster.md is the user guide for our cluster. Run spectra.py for each of the 24 lines of inputs.txt, one job per line: 8 cores, 32 GB of memory in total and a 6 hour limit for each, and no more than 4 running at once. Write job.sh and a submit.sh that submits it, with the job logs going into logs/.
