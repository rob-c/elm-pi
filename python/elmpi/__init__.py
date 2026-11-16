"""The launcher.

`pi` in this install is a wrapper around pi: it keeps the session on the
University's ELM gateway, gives pi this install's configuration and paths,
starts the egress proxy, and hands pi its arguments. This package is that
wrapper. `pi` in the install root finds the install and hands over to
`python/pi`, which starts Python here; the reference implementation the wrapper
replaced - the bash `pi` that used to be - is `pi.bash` beside them, and
tests/test_python_launcher.py runs both on the same install and compares what
they decide.

Nothing in this package imports anything outside the standard library, and
nothing is expected to be installed: `python/pi` starts the interpreter with
-E -s -S -B, so no site-packages, no .pth file, no PYTHON* variable and no
`__pycache__` inside the install can change what is imported. The modules are
laid out by the job each one does - see README.md beside this package for the
map.
"""

__version__ = "1.0.0"
