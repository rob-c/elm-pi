"""One Mistral arm, the install as it stands (e.g. with samplingParams set): ab2.py's tasks and checks.

    python3 ab4.py PI_LAUNCHER WORKDIR OUT.json APPEND_SYSTEM.md GUIDANCE.md REPS ARM_NAME [--md]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
name, with_md = sys.argv[7], "--md" in sys.argv[8:]
sys.argv = sys.argv[:7]
ns = {"__name__": "ab4", "__file__": str(HERE / "ab2.py")}
exec(compile((HERE / "ab2.py").read_text().replace("\nmain()\n", "\n"), "ab2.py", "exec"), ns)
args = ["--mistral", "--append-system-prompt", str(ns["APPEND"])]
if with_md:
    args += ["--append-system-prompt", str(ns["GUIDANCE"])]
ns["ARMS"].clear()
ns["ARMS"][name] = args
ns["main"]()
