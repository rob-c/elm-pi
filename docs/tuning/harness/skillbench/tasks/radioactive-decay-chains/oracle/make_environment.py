"""Writes environment/ for this task: the batch notes. Nothing is random.

    python make_environment.py <environment dir>

The chain is Mo-99 -> Tc-99m (87.6%) -> Tc-99, with 12.4% of Mo-99 decays going
straight to the Tc-99 ground state. The irradiation is long enough (2.2
half-lives) that rate times time overstates the Mo-99 by a factor 1.9.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

RATE = 2.60e11            # Mo-99 atoms made per second
T_IRRADIATION_H = 144.0
T_COOLING_H = 30.0

(out / "notes.md").write_text("""# Mo-99 batch 26-47

## Irradiation

- Enriched Mo-98 target, position C4, constant flux.
- In: 2026-11-02 08:00 UTC. Out: 2026-11-08 08:00 UTC (%.1f h).
- Mo-99 production rate in the target, from the flux monitor: %.2e atoms
  per second, constant over the irradiation (burn-up of the target and of the
  Mo-99 is negligible).

## Chemistry and loading

- 2026-11-09 14:00 UTC, %.1f h after the end of irradiation: the molybdenum
  was dissolved and purified and the generator column loaded. All of the
  molybdenum went onto the column; the purification removed all technetium,
  so the column starts with none.
- Nothing is eluted before the first elution, which we want at the Tc-99m
  maximum.

## Decay data (ENSDF)

| nuclide | half-life | decay |
|---|---|---|
| Mo-99 | 65.924 h | beta-minus: 87.6%% of decays feed Tc-99m, the other 12.4%% go to the Tc-99 ground state |
| Tc-99m | 6.0067 h | isomeric transition to the Tc-99 ground state |
| Tc-99 | 2.111e5 y | beta-minus to Ru-99 (stable) |
""" % (T_IRRADIATION_H, RATE, T_COOLING_H))
print("wrote notes.md")
