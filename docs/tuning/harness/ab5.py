"""Mistral with the levers the research ranked highest, the claim guard installed for every arm.

    python3 ab5.py PI_LAUNCHER WORKDIR OUT.json APPEND_SYSTEM.md VIBE.md REPS

Arms (models.json: temperature 0.15, 0.7 when thinking is high):
  mistral@0.15+guard        - the 0.15 run again, now with the guard
  mistral-high@0.7+guard    - reasoning_effort high (pi --thinking high)
  mistral@0.15+vibe+guard   - Vibe's working rules appended to the system prompt
Each result records whether the guard fired, so its share is visible.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ns = {"__name__": "ab5", "__file__": str(HERE / "ab2.py")}
exec(compile((HERE / "ab2.py").read_text().replace("\nmain()\n", "\n"), "ab2.py", "exec"), ns)
APPEND, VIBE = ns["APPEND"], ns["GUIDANCE"]
base = ["--mistral", "--append-system-prompt", str(APPEND)]
ns["ARMS"].clear()
ns["ARMS"].update({
    "mistral@0.15+guard": base,
    "mistral-high@0.7+guard": base + ["--thinking", "high"],
    "mistral@0.15+vibe+guard": base + ["--append-system-prompt", str(VIBE)],
})

run = ns["run"]


def run_and_note(arm, task, rep):
    result = run(arm, task, rep)
    project = ns["WORK"] / f"{task}-{arm.replace('+', '_')}-{rep}"
    fired = 0
    for f in (project / ".pi/sessions").glob("*.jsonl"):
        fired += sum(1 for line in f.read_text().splitlines() if '"customType": "claim-guard"' in line
                     or '"customType":"claim-guard"' in line)
    result["guard_fired"] = fired
    return result


ns["run"] = run_and_note
ns["main"]()
