---
name: scientific-python
description: "Working conventions for scientific Python: choosing the right Python environment, numpy/scipy/pandas idioms, physics-quality plots, reproducible analysis scripts, and reading ROOT/HDF5/CSV data. Use whenever writing or running Python for analysis, simulation or plotting."
---

# Scientific Python

## Which Python

Use the environment the project uses: an activated conda env, a `.venv`, a
`pyproject.toml`/`environment.yml`/`requirements.txt` in the project. Without
one, `python3` is this install's own environment (`$ELM_PI_AGENT_PYTHON`):
numpy, scipy, pandas, matplotlib, h5py, uproot, iminuit, sympy, openpyxl,
xlsxwriter, pyarrow, jupytext, nbformat, nbconvert and ipykernel are already
in it. Check before writing code:
`python3 -c "import sys, numpy, scipy; print(sys.executable, numpy.__version__, scipy.__version__)"`.

A package that is missing can be installed: the egress proxy lets PyPI
through. Into this install's environment: `pip install <package>` (or the
faster `uv pip install --python "$ELM_PI_AGENT_PYTHON" <package>`); into a
project's `.venv`: `uv pip install --python .venv/bin/python <package>`. Say in
the report what you installed and where. **Never** install into the system
Python or a conda base environment, never with `sudo`, and do not create a new
environment the user did not ask for. Packages come from PyPI only: a download
from any other host is refused by the proxy.

## Code

- One script per result, kept in the working directory, runnable top to
  bottom: `python3 analysis.py` reproduces every number and figure it reports.
  Paths relative to the script, inputs read from files, no notebook-only state.
- Vectorise with numpy; avoid Python loops over array elements.
- `rng = np.random.default_rng(seed)` with the seed printed or saved.
- Print the versions of numpy/scipy (and anything else that matters) in the
  output of a result-producing script.
- Constants: `scipy.constants` rather than typed-in values; its CODATA
  release depends on the installed scipy, so record `scipy.__version__` (see
  `physical-constants`).

## Plots

Axis labels with units (`r"$E$ [MeV]"`), error bars on data, the model as a
line, a residual or pull panel under fits, a legend only when there is more
than one series, log scales stated. Save as PDF/PNG next to the script
(`fig.savefig("spectrum.pdf", bbox_inches="tight")`) and name the file in the
report. Never rely on an interactive window - `matplotlib.use("Agg")` in
scripts.

## Data

- CSV/text: `np.loadtxt`/`np.genfromtxt` or `pandas.read_csv`; check the shape,
  units and a few rows before use, and say what the columns are.
- ROOT: `uproot` (`uproot.open(path)["tree"].arrays(["px", "py"], library="np")`),
  awkward arrays for jagged data; `uproot` writes histograms too.
- HDF5: `h5py`. Large data: read only the columns needed.
- Never modify the user's input data in place; write derived data to a new file.
