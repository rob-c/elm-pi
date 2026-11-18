---
skill: batch-slurm
also: batch-jobs
category: batch
pitfall: eight tasks asked for where one task with eight CPUs is meant; --mem taken as per core; the array not throttled; logs/ not made before sbatch; the partition and account guessed instead of read from the guide
timeout_sec: 600
---
cluster.md is the user guide for our cluster. I need analyse.py run on each of the 48 files listed in inputs.txt, one job per file: 8 cores and 16 GB of memory in total for each, a 2 hour limit, and no more than 6 running at once. Write job.sh and a submit.sh I can run to submit it, with the job logs going into logs/.
