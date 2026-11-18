"""The reference solution: run in the project folder, writes result.json.

    Gamma = <|M|^2> Phi_2 / (2 M) / n!        Phi_2 = |p*| / (4 pi sqrt(s)) for an isotropic |M|^2
    sigma = Int <|M|^2> dPhi_2 / F / n!       F = 4 sqrt((p1.p2)^2 - m1^2 m2^2)

with n! = 2 for the two identical a in the final state, F for massive beams,
and GeV^-2 turned into pb at the end. The two-body phase space is checked
against the defining integral with the energy delta function smeared, and the
whole chain against sigma(e+ e- -> mu+ mu-) = 4 pi alpha^2/(3 s) = 86.8 nb GeV^2/s.
"""
import json
import math

from scipy.integrate import quad

M_S, M_A, M_CHI = 600.0, 80.0, 150.0            # notes.md
KAPPA, YUKAWA, LAMBDA = 45.0, 0.12, 2000.0
ROOT_S = 400.0                                  # the request
HBAR = 6.582119569e-25                          # GeV s
GEV2_TO_PB = 0.3893793721e9                     # (hbar c)^2 in GeV^2 pb


def momentum(root_s, m1, m2):
    """|p*| of either particle of a pair with invariant mass root_s."""
    s = root_s**2
    kallen = (s - m1**2 - m2**2) ** 2 - 4 * m1**2 * m2**2
    return math.sqrt(kallen) / (2 * root_s)


def phase_space(root_s, m1, m2):
    """Integrated two-body phase space."""
    return momentum(root_s, m1, m2) / (4 * math.pi * root_s)


def phase_space_from_definition(root_s, m1, m2, width=1e-3):
    """Int d^3p1/((2pi)^3 2E1) d^3p2/((2pi)^3 2E2) (2pi)^4 delta^4, with the momentum delta done
    and the energy delta replaced by a Gaussian of relative width `width`."""
    sigma = width * root_s

    def integrand(p):
        e1, e2 = math.hypot(p, m1), math.hypot(p, m2)
        smeared = math.exp(-0.5 * ((root_s - e1 - e2) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi))
        return p * p / (4 * math.pi * e1 * e2) * smeared

    peak = momentum(root_s, m1, m2)
    return quad(integrand, 0.0, 3 * peak, points=[peak], epsabs=0, epsrel=1e-12, limit=400)[0]


def width(msq, mass, m1, m2, identical):
    return msq * phase_space(mass, m1, m2) / (2 * mass) / (2 if identical else 1)


def cross_section(msq_of_cos, root_s, beam1, beam2, m3, m4, identical):
    """Total cross section in GeV^-2; msq_of_cos(cos theta) is the averaged |M|^2."""
    s = root_s**2
    p1_dot_p2 = (s - beam1**2 - beam2**2) / 2
    flux = 4 * math.sqrt(p1_dot_p2**2 - beam1**2 * beam2**2)
    angular = quad(msq_of_cos, -1, 1, epsabs=0, epsrel=1e-13)[0] / 2          # average over the sphere
    return angular * phase_space(root_s, m3, m4) / flux / (2 if identical else 1)


for pair in ((M_A, M_A), (M_CHI, M_CHI), (M_CHI, M_A)):
    assert abs(phase_space_from_definition(M_S, *pair) / phase_space(M_S, *pair) - 1) < 1e-4
# The known rate, by the same code: massless e+ e- -> mu+ mu-, <|M|^2> = 2 e^4 (t^2 + u^2)/s^2 = e^4 (1 + cos^2).
e2 = 4 * math.pi / 137.035999
qed = cross_section(lambda c: e2**2 * (1 + c * c), 10.0, 0.0, 0.0, 0.0, 0.0, False) * GEV2_TO_PB * 1e-3
assert abs(qed * 100.0 - 86.85) < 0.01, "e+ e- -> mu+ mu- is not 86.8 nb GeV^2 / s"

gamma_aa = width(KAPPA**2, M_S, M_A, M_A, identical=True)
gamma_chi = width(2 * YUKAWA**2 * (M_S**2 - 4 * M_CHI**2), M_S, M_CHI, M_CHI, identical=False)
total = gamma_aa + gamma_chi
sigma = cross_section(lambda c: (ROOT_S**2 - 4 * M_CHI**2) / (2 * LAMBDA**2), ROOT_S, M_CHI, M_CHI, M_A, M_A, identical=True)

result = {"width_gev": total, "lifetime_s": HBAR / total, "br_aa": gamma_aa / total, "sigma_pb": sigma * GEV2_TO_PB}
json.dump(result, open("result.json", "w"), indent=1)
print("Gamma(aa) %.6f GeV, Gamma(chi chibar) %.6f GeV" % (gamma_aa, gamma_chi))
for key, value in result.items():
    print("%-11s %.7g" % (key, value))
