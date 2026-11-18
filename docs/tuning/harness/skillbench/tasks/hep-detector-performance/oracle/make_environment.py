"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A test-beam energy scan of a calorimeter module. The response is a Gaussian
core whose relative width is a/sqrt(E) (+) b/E (+) c, plus 4% of electrons that
shower upstream and are reconstructed 12 to 45% low. That tail is 6% of E in
the r.m.s. at every energy, so an r.m.s. taken over everything gives a
"constant term" eight times the real one.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

STOCHASTIC, NOISE, CONSTANT = 0.105, 0.28, 0.0075     # sqrt(GeV), GeV, fraction: what the task asks for
ENERGIES = [5, 10, 20, 50, 100, 150, 200]             # GeV
EVENTS = 2000
TAIL_FRACTION, LOSS = 0.04, (0.12, 0.45)


def resolution(energy):
    return np.sqrt(STOCHASTIC**2 / energy + (NOISE / energy) ** 2 + CONSTANT**2)


rows = []
for energy in ENERGIES:
    scale = 1.0 + 0.003 * np.log(energy / 50.0) / np.log(40.0)          # non-linearity of 0.3% over the scan
    reco = energy * scale * (1 + resolution(energy) * rng.standard_normal(EVENTS))
    upstream = rng.random(EVENTS) < TAIL_FRACTION
    reco = np.where(upstream, reco * (1 - rng.uniform(*LOSS, EVENTS)), reco)
    rows += ["%d,%.3f\n" % (energy, e) for e in reco]
    print("%3d GeV: core %.4f, r.m.s. over mean of everything %.4f" % (energy, resolution(energy), reco.std() / reco.mean()))
(out / "testbeam.csv").write_text("beam_energy_gev,e_reco_gev\n" + "".join(rows))

(out / "notes.md").write_text("""# ECAL prototype, module 3: electron energy scan in the H4 beam

- Electrons at %s GeV. The beam momentum spread is below
  0.1%% and is neglected.
- testbeam.csv: one row per electron, with the beam energy and the energy
  reconstructed in the 5 x 5 crystal matrix around the impact point after the
  standard intercalibration and containment correction.
- %d electrons per energy after the beam-quality cuts (one track in the beam
  chambers, impact within 2 mm of the crystal centre).
- The beam line has scintillators and a wire chamber in front of the module. A
  few per cent of the electrons start to shower there and are reconstructed
  low; the selection does not remove them. As in the note on module 2, the
  resolution we quote is that of the Gaussian core of the response.
""" % (", ".join(str(e) for e in ENERGIES[:-1]) + " and %d" % ENERGIES[-1], EVENTS))
print("truth: a = %.3f sqrt(GeV), b = %.2f GeV, c = %.4f; at 300 GeV %.5f" % (STOCHASTIC, NOISE, CONSTANT, resolution(300.0)))
