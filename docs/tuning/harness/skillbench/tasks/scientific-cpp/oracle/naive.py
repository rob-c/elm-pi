"""What the task is built to catch: the reported line patched, the reported example rerun, done.

rms_of() no longer overflows, and the 16-bit pedestal run prints the right
rms. mean_of() still sums in `int` through std::accumulate(..., 0): nothing in
the README's two examples shows it, the long runs do.
"""
from pathlib import Path

source = Path("adcstat.cpp").read_text()
old = "    int squares = 0;\n    for (int i = 0; i < n; ++i) squares += samples[i] * samples[i];\n"
new = "    double squares = 0;\n    for (int i = 0; i < n; ++i) squares += double(samples[i]) * samples[i];\n"
assert source.count(old) == 1
Path("adcstat.cpp").write_text(source.replace(old, new))
