"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is statistical: anti-kT with R = 0.4 and four-momentum recombination on the 152 particles
that are not neutrinos has one answer, computed by a plain loop in oracle/make_environment.py and
again, another way, in oracle/solve.py. Moving every momentum component by four times its rounding,
or reading the file as float32, changes the leading jet's pT, rapidity and mass by less than 1e-5,
1e-6 and 2e-4. The tolerances - 0.5% on pT, 0.005 on rapidity, 2% on mass - are far above that.

Jets: 108.80, 91.34, 48.49, 27.12 and 22.80 GeV, then 4 GeV and less. What the wrong routes give
(jets over 25 GeV; leading pT, rapidity, mass):
- pseudorapidity in the distance:      4; 105.63, 1.636, 17.2  (reported as eta: 1.648)
- right jets, pseudorapidity reported: 4; 108.80, 1.666, 23.5
- kT measure:                          3; 110.40, 1.650, 25.3
- Cambridge/Aachen:                    4; 106.96, 1.650, 20.7
- neutrinos left in:                   6; 118.18, 1.646, 24.5
- azimuth not wrapped:                 4; 102.71, 1.650, 22.4
- pT-weighted massless recombination:  4; 109.15, 1.645, 0
- R = 0.5:                             5; 108.80, 1.644, 23.5
- a cone round the hardest particle:   4; 107.11, 1.648, 22.7
"""
import json
import math
from pathlib import Path

N_JETS = 4
LEAD_PT = 108.8006          # GeV
LEAD_RAPIDITY = 1.64437
LEAD_MASS = 23.4940         # GeV


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_four_numbers():
    data = result()
    for key in ("n_jets", "lead_pt_gev", "lead_rapidity", "lead_mass_gev"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_number_of_jets_above_the_cut():
    assert result()["n_jets"] == N_JETS


def test_leading_jet_pt():
    assert abs(result()["lead_pt_gev"] / LEAD_PT - 1) < 0.005


def test_leading_jet_rapidity():
    assert abs(result()["lead_rapidity"] - LEAD_RAPIDITY) < 0.005


def test_leading_jet_mass():
    assert abs(result()["lead_mass_gev"] / LEAD_MASS - 1) < 0.02
