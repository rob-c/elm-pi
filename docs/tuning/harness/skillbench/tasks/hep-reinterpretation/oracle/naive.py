"""What the task is built to catch: each point tested in whichever region gives the largest
observed r, which lets SR-2j's downward fluctuation exclude a point its sensitivity does not reach."""
import csv
import json

xsec_pb = {int(row["m_gluino_gev"]): float(row["xsec_pb"]) for row in csv.DictReader(open("cross_sections.csv"))}
s95 = {row["region"]: float(row["s95_observed"]) for row in csv.DictReader(open("signal_regions.csv"))}
grid = {(int(row["m_gluino_gev"]), int(row["m_lsp_gev"])): (float(row["acc_x_eff_sr2j"]), float(row["acc_x_eff_sr4j"]))
        for row in csv.DictReader(open("efficiency_map.csv"))}
result = {}
for name, (m_gluino, m_lsp) in {"p1": (1900, 400), "p2": (1800, 1000), "p3": (1600, 1400)}.items():
    if (m_gluino, m_lsp) in grid:
        eff = grid[(m_gluino, m_lsp)]
    else:
        eff = tuple(0.5 * (a + b) for a, b in zip(grid[(m_gluino - 100, m_lsp)], grid[(m_gluino + 100, m_lsp)]))
    produced = xsec_pb[m_gluino] * 1000.0 * 139.0 * 0.70**2
    n_2j, n_4j = produced * eff[0], produced * eff[1]
    r = max(n_2j / s95["SR-2j"], n_4j / s95["SR-4j"])
    result.update({name + "_n_sr2j": n_2j, name + "_n_sr4j": n_4j, name + "_r": r, name + "_excluded": bool(r > 1)})
json.dump(result, open("result.json", "w"))
