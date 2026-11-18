"""The reference solution: run in the project folder, writes result.json.

Yield in a region = sigma x L x BR^2 x (acceptance x efficiency): both gluinos
must decay as in the simplified model the map was made for. With only counts
and limits per region, each point is tested in the one region whose expected
limit is the most sensitive to it, and r there is the yield over the observed
limit.
"""
import csv
import json
import re

notes = open("notes.md").read()
lumi_fb = float(re.search(r"([0-9.]+) fb\^-1", notes).group(1))
branching = float(re.search(r"branching fraction of\s+(\d\.\d+)", notes).group(1))
points = {name: (int(m1), int(m2)) for name, m1, m2 in re.findall(r"(p\d) \((\d+), (\d+)\)", notes)}
xsec_pb = {int(row["m_gluino_gev"]): float(row["xsec_pb"]) for row in csv.DictReader(open("cross_sections.csv"))}
regions = {row["region"]: (float(row["s95_observed"]), float(row["s95_expected"])) for row in csv.DictReader(open("signal_regions.csv"))}
grid = {(int(row["m_gluino_gev"]), int(row["m_lsp_gev"])): {"SR-2j": float(row["acc_x_eff_sr2j"]), "SR-4j": float(row["acc_x_eff_sr4j"])}
        for row in csv.DictReader(open("efficiency_map.csv"))}
gluino_masses = sorted({masses[0] for masses in grid})


def from_map(m_gluino, m_lsp):
    """The map at this point: on a node, or linear in gluino mass between the two neighbouring nodes."""
    if (m_gluino, m_lsp) in grid:
        return grid[(m_gluino, m_lsp)]
    low = max(m for m in gluino_masses if m < m_gluino)
    high = min(m for m in gluino_masses if m > m_gluino)          # raises outside the grid: no limit there
    weight = (m_gluino - low) / (high - low)
    return {name: (1 - weight) * grid[(low, m_lsp)][name] + weight * grid[(high, m_lsp)][name] for name in regions}


result = {}
for name, (m_gluino, m_lsp) in sorted(points.items()):
    produced = xsec_pb[m_gluino] * 1000.0 * lumi_fb * branching**2          # 1 pb x 1 fb^-1 = 1000 events
    yields = {region: produced * value for region, value in from_map(m_gluino, m_lsp).items()}
    chosen = max(regions, key=lambda region: yields[region] / regions[region][1])        # best expected
    r = yields[chosen] / regions[chosen][0]                                              # observed, in that region
    result.update({name + "_n_sr2j": yields["SR-2j"], name + "_n_sr4j": yields["SR-4j"], name + "_r": r, name + "_excluded": bool(r > 1)})
    print("%s (%d, %d): SR-2j %.2f, SR-4j %.2f events; %s has the best expected limit; r = %.2f, %s"
          % (name, m_gluino, m_lsp, yields["SR-2j"], yields["SR-4j"], chosen, r, "excluded" if r > 1 else "not excluded"))
json.dump(result, open("result.json", "w"), indent=1)
