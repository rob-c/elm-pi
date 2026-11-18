"""The community skill library in agent/skills/kdense.

K-Dense's scientific-agent-skills: 167 skills for scientific libraries,
databases and research methods, which the fifty physics skills in
templates/skills refer to (user request, 2026-11-17).

Everything it decides is in scripts/skill_library.py - the pinned commit and
checksum, what is unpacked, which skills are left out, hiding them from the
system prompt - and bootstrap.bash runs the same script, so the two installers
print one text. It never fails the run: a download that does not arrive is a
warning, and the next run tries again.

    --no-skill-library       leave it out, or take it out
    ELM_PI_TOOL_CACHE=/path  where the verified archive is kept (tools.py)
"""

import os

from elmboot import console

SCRIPT = os.path.join("scripts", "skill_library.py")


def install(run):
    """Phase 3b1."""
    console.say("skill library")
    script = [run.path(SCRIPT), "--root", run.root]
    if not run.options.skill_library:
        run.call(run.python(script + ["remove"]))
        console.note("skipped (--no-skill-library): agent/skills/kdense is not installed")
        return
    env = run.env
    cache = env.get("ELM_PI_TOOL_CACHE") or os.path.join(
        env.get("XDG_CACHE_HOME") or os.path.join(env.get("HOME", ""), ".cache"),
        "elm-pi", "tools")
    sync = ["sync", "--cache", cache] + (["--force"] if run.options.force else [])
    if run.call(run.python(script + sync + ["--", "curl", "-q", "-fsSL"] + run.retry)) != 0:
        console.warn("the skill library step failed - agent/skills/kdense is as it was")
