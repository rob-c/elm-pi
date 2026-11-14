"""The claim guard on Mistral: the same 17 tasks, with agent/extensions/claim-guard.ts installed.

    python3 ab3.py PI_LAUNCHER WORKDIR OUT.json APPEND_SYSTEM.md GUIDANCE.md REPS

Arms: Mistral with the guard, and Mistral with the guard and the written guidance.
Everything else is ab2.py's: fixture, tasks, checks, scoring.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ns = {"__name__": "ab3", "__file__": str(HERE / "ab2.py")}
exec(compile((HERE / "ab2.py").read_text().replace("\nmain()\n", "\n"), "ab2.py", "exec"), ns)
APPEND, GUIDANCE = ns["APPEND"], ns["GUIDANCE"]
ns["ARMS"].clear()
ns["ARMS"].update({
    "mistral+guard": ["--mistral", "--append-system-prompt", str(APPEND)],
    "mistral+md+guard": ["--mistral", "--append-system-prompt", str(APPEND), "--append-system-prompt", str(GUIDANCE)],
})
ns["main"]()
