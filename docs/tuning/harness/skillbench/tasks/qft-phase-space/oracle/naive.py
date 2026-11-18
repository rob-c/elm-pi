"""What the task is built to catch: no 1/2 for the two identical a, and the massless flux 2s for massive beams.

The two-body formulae and the unit conversions are right. The a a final state
is integrated over the whole sphere as if the two particles were different,
in the decay and in the scattering, and the cross section is divided by 2s
although the beams have m_chi = 150 GeV at sqrt(s) = 400 GeV.
"""
import json
import math

M_S, M_A, M_CHI = 600.0, 80.0, 150.0
KAPPA, YUKAWA, LAMBDA = 45.0, 0.12, 2000.0
ROOT_S = 400.0
HBAR, GEV2_TO_PB = 6.582119569e-25, 0.3893793721e9

gamma_aa = math.sqrt(M_S**2 / 4 - M_A**2) * KAPPA**2 / (8 * math.pi * M_S**2)
gamma_chi = math.sqrt(M_S**2 / 4 - M_CHI**2) * 2 * YUKAWA**2 * (M_S**2 - 4 * M_CHI**2) / (8 * math.pi * M_S**2)
total = gamma_aa + gamma_chi
s = ROOT_S**2
msq = (s - 4 * M_CHI**2) / (2 * LAMBDA**2)
sigma = msq * math.sqrt(s / 4 - M_A**2) / (4 * math.pi * ROOT_S) / (2 * s)
json.dump({"width_gev": total, "lifetime_s": HBAR / total, "br_aa": gamma_aa / total, "sigma_pb": sigma * GEV2_TO_PB},
          open("result.json", "w"), indent=1)
