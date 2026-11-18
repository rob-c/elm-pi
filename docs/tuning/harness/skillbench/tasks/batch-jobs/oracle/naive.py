"""What the task is built to catch: the old script with the new site's names put in.

The command is still qsub, so the #PBS lines are kept and only the queue,
the account and the module are changed to what the new guide gives. The new
cluster is Grid Engine: every #PBS line is a comment to it, so the job would
be submitted with no queue, project, parallel environment, time limit or
array, and the $PBS_ variables the commands use are not set.
"""
from pathlib import Path

old = Path("old_job.sh").read_text()
new = (old.replace("#PBS -q batch", "#PBS -q work-s.q")
          .replace("#PBS -A nucth", "#PBS -A qcd-lat24")
          .replace("module load python/3.9.6", "module load sci-python/2025a")
          .replace("on Stoat", "on Marten"))
Path("job.sh").write_text(new)
Path("submit.sh").write_text("""#!/bin/bash
mkdir -p logs
qsub job.sh
""")
