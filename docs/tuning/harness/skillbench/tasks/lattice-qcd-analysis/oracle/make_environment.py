"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A zero-momentum pseudoscalar two-point function on 1000 configurations of a
lattice with T = 32, periodic in time:

    C(t) = A0 [exp(-m0 t) + exp(-m0 (T - t))] + A1 [exp(-m1 t) + exp(-m1 (T - t))]

times (1 + noise). The noise is what makes the task:
- its relative size grows with the distance from the source, 3.5% exp(0.085 t);
- it is correlated between time slices, exp(-|t - t'| / 6);
- it is correlated along the Monte Carlo history: an AR(1) process with
  coefficient 0.85, so tau_int = (1 + 0.85) / (2 (1 - 0.85)) = 6.2 and the true
  error of any mean is sqrt(2 tau_int) = 3.5 times the naive one.
The excited state (a m1 = 0.92, A1/A0 = 0.7) is gone from the effective mass
within errors from about t = 8.
"""
import sys
from pathlib import Path

import h5py
import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

N, T = 1000, 32
AM0, AM1 = 0.2985, 0.92            # a m0 is what the task asks for
A0, A1 = 0.0412, 0.7 * 0.0412
RHO = 0.85                         # AR(1) coefficient between successive configurations
SIGMA0, GROWTH, XI = 0.035, 0.085, 6.0
A_FM, A_FM_ERR = 0.0847, 0.0012    # lattice spacing: m0 = 0.2985 * 197.327 / 0.0847 = 695.4 MeV

t = np.arange(T)
back = T - t
exact = A0 * (np.exp(-AM0 * t) + np.exp(-AM0 * back)) + A1 * (np.exp(-AM1 * t) + np.exp(-AM1 * back))
distance = np.minimum(np.abs(t[:, None] - t[None, :]), T - np.abs(t[:, None] - t[None, :]))
sigma = SIGMA0 * np.exp(GROWTH * np.minimum(t, back))
chol = np.linalg.cholesky(np.exp(-distance / XI) + 1e-12 * np.eye(T))
BURN = 200                         # the chain is stationary before the first stored configuration
eta = rng.standard_normal((N + BURN, T)) @ chol.T
eps = np.empty_like(eta)
eps[0] = eta[0]
for i in range(1, N + BURN):
    eps[i] = RHO * eps[i - 1] + np.sqrt(1 - RHO ** 2) * eta[i]
data = exact[None, :] * (1.0 + sigma[None, :] * eps[BURN:])

with h5py.File(out / "corr.h5", "w") as handle:
    c2pt = handle.create_dataset("c2pt", data=data)
    c2pt.attrs["ensemble"] = "S16"
    c2pt.attrs["channel"] = "pseudoscalar, strange-strange, connected, zero momentum"
    c2pt.attrs["axes"] = "configuration, t/a"
    handle.create_dataset("trajectory", data=(2000 + 4 * np.arange(N)).astype(np.int32))

(out / "notes.md").write_text("""# Ensemble S16: strange-strange pseudoscalar two-point function

- N_f = 2+1 clover fermions, 16^3 x 32 (L/a = 16, T/a = 32), periodic in space;
  the meson correlator is periodic in time.
- Lattice spacing a = %.4f(%d) fm, from the gradient-flow scale.
- hbar c = 197.3269804 MeV fm.

## corr.h5

- `c2pt`, shape (%d, %d): the zero-momentum two-point function C(t) of the
  connected strange-strange pseudoscalar, one row per gauge configuration,
  columns t/a = 0 .. %d (source at t = 0, point source and point sink).
- `trajectory`, shape (%d,): the molecular-dynamics trajectory each
  configuration was saved at. One Markov chain, every 4th trajectory, in the
  order they were generated; the thermalisation (trajectories below 2000) is
  already cut.
""" % (A_FM, round(A_FM_ERR * 1e4), N, T, T - 1, N))
print("a m0 = %.4f, m0 = %.1f MeV; corr.h5 %d bytes" % (AM0, AM0 * 197.3269804 / A_FM, (out / "corr.h5").stat().st_size))
