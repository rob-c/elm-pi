"""A saturated machine is noted, but not stood in the way of.

Each sub-agent is a full node process. On a 12-thread laptop a 32-worker run
drove load average to 104 and made every new pi invocation hang.

This used to refuse to start. It now warns and carries on: a shared login node,
a compute host or simply a busy desktop sits over the threshold most of the
day, and "pi refused to start" is a worse first hour for someone new than a
slow start they were told about.

    PI_FORCE=1        start silently, no warning at all
    PI_STRICT_LOAD=1  restore the old refusal (for unattended or batch use)
"""

import os
import subprocess

from elmpi.errors import Refusal, CANNOT_START
from elmpi.toolchain import run_count

THREADS_FACTOR = 1.5
FALLBACK_THREADS = 8


def _output(argv):
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                universal_newlines=True)
    except OSError:
        return ""
    return result.stdout.strip()


def threads():
    """The machine's CPUs, as the reference launcher reads them."""
    for argv in (["sysctl", "-n", "hw.ncpu"], ["nproc"]):
        value = _output(argv)
        if value.isdigit() and int(value) > 0:
            return int(value)
    return os.cpu_count() or FALLBACK_THREADS


def load_average():
    """The one-minute load average, or None where the system will not say."""
    try:
        return os.getloadavg()[0]
    except OSError:
        return None


def note(env):
    """The lines to print about a busy machine; raises when told to stop.

    Nothing is computed for a forced start or a sub-agent child: those two
    cases start silently, and a pgrep per sub-agent launch is not free.
    """
    if env.get("PI_FORCE") == "1" or env.get("PI_ELM_CHILD"):
        return []
    load = load_average()
    if load is None:
        return []
    cpus = threads()
    runners = run_count()
    if load > cpus * THREADS_FACTOR:
        lines = ["pi: this machine is busy - load %.2f across %d threads, %d sub-agent "
                 "runner(s) live." % (load, cpus, runners)]
        if env.get("PI_STRICT_LOAD") == "1":
            lines.append("    PI_STRICT_LOAD=1 is set, so not starting. Unset it, or set "
                         "PI_FORCE=1.")
            raise Refusal(*lines, code=CANNOT_START)
        lines.append("    Starting anyway; it may take longer than usual to come up.")
        return lines
    if runners > 0:
        return ["pi: note - %d sub-agent runner(s) already running (load %.2f/%d)."
                % (runners, load, cpus)]
    return []
