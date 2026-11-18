"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A counting measurement of Y(1S) -> mu mu. The observed yield is one Poisson
draw around what the true cross-section below gives through the trigger's
prescaled luminosity; the simulation's counts fix the acceptance A and the
correction C, with 4% of the selected events coming from outside the fiducial
region.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

SIGMA_TOTAL_PB = 395_000.0       # pp -> Y(1S) X, |y| < 2.4: the truth
BR, BR_ERR = 0.0248, 0.0005
LUMI_FB, LUMI_REL = 0.800, 0.023
PRESCALE = 60
B, B_ERR = 7250.0, 290.0
C_REL, A_REL = 0.024, 0.065
MC = {                           # sums of weights in the signal simulation
    "generated": 4_000_000.0,                     # Y(1S) -> mu mu, |y| < 2.4
    "fiducial": 1_008_000.0,                      # of those, both muons in the fiducial region (particle level)
    "selected": 612_400.0,                        # reconstructed and selected
    "selected_and_fiducial": 586_300.0,           # of the selected, those in the fiducial region at particle level
}

A = MC["fiducial"] / MC["generated"]
C = MC["selected"] / MC["fiducial"]
lumi_pb = LUMI_FB * 1000.0 / PRESCALE
sigma_fid_true = SIGMA_TOTAL_PB * A * BR
n_obs = int(rng.poisson(sigma_fid_true * lumi_pb * C + B))

(out / "mc_counts.csv").write_text("stage,sum_of_weights\n" + "".join("%s,%.1f\n" % item for item in MC.items()))
(out / "notes.md").write_text("""# Y(1S) -> mu+ mu- cross-section at 13 TeV, dimuon stream

## What is measured

- Fiducial region, at particle level: both muons (dressed) with pT > 4.5 GeV
  and abs(eta) < 2.4, from a Y(1S) with abs(y) < 2.4.
- Fiducial cross-section: sigma(pp -> Y(1S) X) x B(Y(1S) -> mu+ mu-) with the
  muons in the fiducial region.
- Total cross-section: sigma(pp -> Y(1S) X) for abs(y) < 2.4, all decays.

## Data

- Trigger: HLT_Dimuon0_Upsilon. It ran with a prescale of %(prescale)d for the whole period.
- Luminosity recorded for the good-run list: %(lumi).3f fb^-1, relative uncertainty %(lumi_rel).1f%%.
- Events in the Y(1S) mass window after the full selection: %(n)d.
- Background in the window, from the sideband fit: %(b).0f +- %(b_err).0f. The
  uncertainty is the spread over the background shapes tried.

## Signal simulation

mc_counts.csv has sums of event weights in the Y(1S) -> mu mu sample
(unpolarised) at four stages:

| stage | |
|---|---|
| generated | Y(1S) -> mu mu with abs(y) < 2.4 |
| fiducial | of those, the events in the fiducial region at particle level |
| selected | events reconstructed and passing the full selection, with the trigger decision as simulated (no prescale) |
| selected_and_fiducial | of the selected events, those in the fiducial region at particle level |

The simulation's statistical uncertainty is negligible. The muon
reconstruction, identification and trigger scale factors are applied; their
uncertainty on the selected yield is %(c_rel).1f%%.

## Extrapolation to the total

- Acceptance: %(a_rel).1f%% relative uncertainty (polarisation and the pT spectrum).
- B(Y(1S) -> mu+ mu-) = (%(br).2f +- %(br_err).2f)%% (PDG).
""" % dict(prescale=PRESCALE, lumi=LUMI_FB, lumi_rel=100 * LUMI_REL, n=n_obs, b=B, b_err=B_ERR,
           c_rel=100 * C_REL, a_rel=100 * A_REL, br=100 * BR, br_err=100 * BR_ERR))

# What the verifier holds.
signal = n_obs - B
fid = signal / (lumi_pb * C)
total = fid / (A * BR)
syst = np.hypot(B_ERR / signal, C_REL)
extrap = np.hypot(A_REL, BR_ERR / BR)
print("N = %d, A = %.5f, C = %.5f, L = %.4f pb^-1" % (n_obs, A, C, lumi_pb))
print("fiducial %.2f pb: stat %.2f, syst %.2f, lumi %.2f   (truth %.2f, %.2f stat sigma away)"
      % (fid, fid * np.sqrt(n_obs) / signal, fid * syst, fid * LUMI_REL, sigma_fid_true,
         (fid - sigma_fid_true) / (fid * np.sqrt(n_obs) / signal)))
print("total %.0f pb: stat %.0f, syst %.0f, lumi %.0f, extrapolation %.0f   (truth %.0f)"
      % (total, total * np.sqrt(n_obs) / signal, total * syst, total * LUMI_REL, total * extrap, SIGMA_TOTAL_PB))
print("relative: stat %.5f (sqrt(N-B) would give %.5f), syst %.5f (with lumi folded in %.5f), extrapolation %.5f"
      % (np.sqrt(n_obs) / signal, 1 / np.sqrt(signal), syst, np.hypot(syst, LUMI_REL), extrap))
