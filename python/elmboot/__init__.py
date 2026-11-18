"""The installer.

`bootstrap.sh` in the install root finds an interpreter - downloading a
standalone one where the machine has none it can use - and starts this package
with it, isolated (-E -s -S -B). Everything else an install is, is decided here:
which flags it was made with, the Node, pi, tools and Python it downloads, what
agent/ holds, and every check before "done". The installer it replaced is
bootstrap.bash beside it: the reference, which nothing runs, and which the
tests hold this package to - the same tables of cases, the same blocks compared
output for output and file for file (tests/test_bootstrap_python.py,
tests/test_bootstrap_installer.py).

Nothing here imports anything outside the standard library; elmpi, the
launcher's package beside this one, is asked one question (can this machine
fence a session).

The modules, in the order a run reaches them:

* cli         - the phases, in the order they have to happen
* run         - what a run must undo, and how it runs a command
* usage       - the --help page, byte-identical to the reference's
* console     - say / warn / die
* options     - this run's flags, and agent/install-options
* installenv  - the install-time environment, the interpreter, disk space, modes
* nodejs      - Node in .node, and npm confined to the install
* pirelease   - pi and the extension packages: staged, patched, swapped in
* agentconfig - agent/ rendered from templates/: code refreshed, config kept
* tools       - the command-line tools in agent/bin
* skilllibrary - the community skill library in agent/skills/kdense
* agentpython - the agent's own Python, and the offline PyPI index
* settings    - the keys this repo decides, reapplied over yours
* checks      - the warm-up, what must be present, and the lockdown
"""

__version__ = "1.0.0"
