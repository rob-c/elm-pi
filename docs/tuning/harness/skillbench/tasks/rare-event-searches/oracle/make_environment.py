"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Two on/off counting measurements with unequal exposures. Target A's excess is
5.0 as excess / sqrt(background) and 4.1 once the OFF count's own fluctuation
is counted. Target B has 2 events on a background of 3.0: its Feldman-Cousins
limit (3.04, the published table's value) is far from the classical one-sided
limit (2.32), from CLs (3.52) and from n - b + 1.28 sqrt(n) (0.81). Nothing is
random here: the counts are chosen.
"""
import sys
from pathlib import Path

import numpy as np
from scipy import stats

out = Path(sys.argv[1])

TARGETS = {"A": (112, 12.5, 350, 62.5), "B": (2, 9.0, 24, 72.0)}      # n_on, t_on [h], n_off, t_off [h]
AREA_M2 = 5.2e4                  # effective area after cuts
CONTAINMENT = 0.70               # share of a point source's photons inside the ON region
CL = 0.90

(out / "counts.csv").write_text("target,n_on,t_on_h,n_off,t_off_h\n" + "".join(
    "%s,%d,%.1f,%d,%.1f\n" % (name, *row) for name, row in TARGETS.items()))
(out / "notes.md").write_text("""# 2026 campaign: targets A and B

counts.csv: gamma-like events above 200 GeV after all cuts, in the ON region
and in the OFF data, with the live time of each. OFF data are taken on empty
fields at the same zenith angles, with the same cuts and a region of the same
size, so ON and OFF have the same background rate.

## Analysis plan (frozen on 3 March, before the ON regions were opened)

- A target is claimed as detected if the significance of its ON excess over
  the background estimated from OFF reaches 5 sigma.
- For a target that is not detected: an upper limit on the number of signal
  events in the ON region at %(cl).0f%% CL, by the unified approach of Feldman and
  Cousins, with the ON background taken as known and equal to its OFF
  estimate.
- The median limit expected for background only is quoted beside the observed
  one.
- Flux limit: the limit on the signal events divided by the exposure, as an
  integral photon flux above 200 GeV.

## Exposure, target B

- Effective area after cuts, averaged over an E^-2 spectrum above 200 GeV:
  %(area).1e m^2.
- Live time: the ON live time in counts.csv.
- A point source puts %(contain).0f%% of its gamma rays inside the ON region; this is
  not in the effective area.
""" % dict(cl=100 * CL, area=AREA_M2, contain=100 * CONTAINMENT))


def li_ma(n_on, n_off, alpha):
    total = n_on + n_off
    return np.sqrt(2 * (n_on * np.log((1 + alpha) / alpha * n_on / total) + n_off * np.log((1 + alpha) * n_off / total)))


def feldman_cousins_upper(n_obs, background, step=0.001):
    """Upper end of the unified interval: the largest signal whose acceptance region holds n_obs."""
    n = np.arange(100)
    best = stats.poisson.pmf(n, np.maximum(n, background))          # likelihood at the best physical signal
    upper = 0.0
    for signal in np.arange(0.0, 20.0, step):
        p = stats.poisson.pmf(n, signal + background)
        order = np.argsort(-p / best, kind="stable")
        accepted = order[: np.searchsorted(np.cumsum(p[order]), CL) + 1]
        if n_obs in accepted:
            upper = signal
    return upper


n_on, t_on, n_off, t_off = TARGETS["A"]
alpha = t_on / t_off
print("A: alpha %.3f, background %.1f; Li-Ma %.3f; binomial %.3f; excess/sqrt(b) %.3f; excess/sqrt(on) %.3f"
      % (alpha, alpha * n_off, li_ma(n_on, n_off, alpha),
         stats.norm.isf(stats.binom.sf(n_on - 1, n_on + n_off, alpha / (1 + alpha))),
         (n_on - alpha * n_off) / np.sqrt(alpha * n_off), (n_on - alpha * n_off) / np.sqrt(n_on)))
n_on, t_on, n_off, t_off = TARGETS["B"]
background = n_off * t_on / t_off
limit = feldman_cousins_upper(n_on, background)
median_n = int(stats.poisson.ppf(0.5, background))
exposure = AREA_M2 * 1e4 * t_on * 3600 * CONTAINMENT
print("B: background %.2f; Feldman-Cousins limit %.3f; median n %d, median limit %.3f" % (
    background, limit, median_n, feldman_cousins_upper(median_n, background)))
print("B: exposure %.4e cm^2 s; flux limit %.4e cm^-2 s^-1" % (exposure, limit / exposure))
