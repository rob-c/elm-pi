---
skill: batch-htcondor
also: batch-jobs
category: batch
pitfall: a loop of condor_submit calls where one queue statement makes the jobs; paths on the submit node read by a job whose worker cannot see them, with no file transfer; no request_memory; the site's accounting group and run-time attribute left out
timeout_sec: 600
---
cluster.md is the user guide for our cluster. Run analyse.py on each of the 40 run files listed in inputs.txt (it also reads calib.json), one job per file with 4 cores and 8 GB of memory, a run time of up to 2 hours, and no more than 10 of them going at once. Write the submit file job.sub, the run.sh it runs, and a submit.sh that submits it, with the job logs going into logs/.
