"""Writes environment/ for this task. The truth is in oracle/solve.py and the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

# The tau, not the muon, is the second lepton so that "mu" in the notes is only ever a Lorentz index.
(out / "notes.md").write_text("""# Heavy Z' and its contact interactions: model and EFT conventions

## Full theory

QED plus a heavy neutral vector boson Z' of mass M = 3 TeV with vector
couplings to electrons and taus. Metric (+,-,-,-).

    L = L_QED - 1/4 Z'_{mu nu} Z'^{mu nu} + 1/2 M^2 Z'_mu Z'^mu
        + Z'_mu ( g_e ebar gamma^mu e + g_tau taubar gamma^mu tau )

    g_e = 0.40,   g_tau = 0.60

L_QED couples the photon as - e Q_f fbar gamma^mu f A_mu with Q = -1 for the
electron and the tau, and alpha = e^2 / (4 pi) = 1/128 at the energies we
look at.

## EFT

Below M the Z' is removed at tree level, keeping dimension six only:

    L_EFT = L_QED + (C_ee / Lambda^2)     (ebar gamma^mu e)(ebar gamma_mu e)
                  + (C_etau / Lambda^2)   (ebar gamma^mu e)(taubar gamma_mu tau)
                  + (C_tautau / Lambda^2) (taubar gamma^mu tau)(taubar gamma_mu tau)

with Lambda = 1 TeV, so that the C are dimensionless. No running: the
coefficients matched at M are used at every energy.

## Observable

Total unpolarised cross section for e+ e- -> tau+ tau-, lepton masses
neglected. "SM" here is photon exchange alone (no Z boson: this is a toy
estimate). In the EFT

    sigma = sigma_SM (1 + r_lin + r_quad)

where r_lin is the interference of the contact term with the photon (linear
in C_etau) and r_quad the contact term squared.

## Validity

We use the dimension-six EFT only up to the sqrt(s) at which |r_quad| reaches
20% of |r_lin|.
""")
print("wrote notes.md")
