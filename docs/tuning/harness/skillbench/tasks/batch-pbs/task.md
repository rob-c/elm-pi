---
skill: batch-pbs
also: batch-jobs
category: batch
pitfall: Torque's nodes=1:ppn=4 and -t with $PBS_ARRAYID written for a PBS Professional site, which wants select=1:ncpus=4:mem=12gb and -J with $PBS_ARRAY_INDEX; no cd to $PBS_O_WORKDIR, so the job runs in the home directory; the queue and account guessed
timeout_sec: 600
---
cluster.md is the user guide for the cluster we have an allocation on. I want reco.py run on each of the 60 files listed in inputs.txt, one job per file with 4 cores, 12 GB of memory and a 90 minute limit, at most 10 running at once. Write job.sh and a submit.sh that submits it, with the job logs going into logs/.
