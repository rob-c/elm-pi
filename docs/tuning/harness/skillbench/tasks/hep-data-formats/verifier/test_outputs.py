"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/make_environment.py. All three are sums over the files, so a correct answer agrees
# to rounding. No event is within 20 MeV of a mass cut or 5 MeV of the pT cut, so single or
# double precision, and massless or massive muons, select the same events.
LUMI_PB = 0.75276        # recorded, in the golden sections
N_DATA = 795             # Z candidates in golden sections, each event once
N_MC = 891.04            # 6077.22 pb x LUMI_PB x selected weights / the Runs tree's sum of weights
VISIBLE_PB = 1183.70     # N_MC / LUMI_PB


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("n_data", "lumi_pb", "n_mc_expected"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_luminosity_is_that_of_the_golden_sections():
    # The certified runs taken whole give 0.8194 (+8.8%), every section in the table 0.9911,
    # delivered instead of recorded 0.8002 (+6.3%); /ub left as it is, 752759.
    assert abs(result()["lumi_pb"] / LUMI_PB - 1) < 0.005


def test_data_events_are_certified_and_counted_once():
    # 1250 if the two primary datasets are added as they are (725 events are in both),
    # 1033 if every section is used, 1616 with both mistakes.
    assert abs(result()["n_data"] - N_DATA) <= 1


def test_simulation_is_normalised_by_all_generated_weights():
    # Independent of the luminosity used: predicted events per pb^-1. Normalised by the skim's
    # own weights it is 5335 pb; by the number of generated events it is off by the weight, 23641.
    data = result()
    assert abs(data["n_mc_expected"] / data["lumi_pb"] / VISIBLE_PB - 1) < 0.01


def test_predicted_events():
    assert abs(result()["n_mc_expected"] / N_MC - 1) < 0.012
