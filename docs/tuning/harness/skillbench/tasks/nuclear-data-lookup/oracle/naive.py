"""What the task is built to catch: the RI column read as photons per 100 decays (no NR, no BR),
with every other number read correctly."""
import json

GAMMAS = {446.812: 3.87, 620.3553: 2.88, 657.7600: 100.0, 677.6217: 11.19, 687.0091: 6.83, 706.6760: 17.46,
          744.2755: 4.99, 763.9424: 23.64, 818.0244: 7.77, 884.6781: 78.4, 937.485: 36.56, 1384.2931: 26.17,
          1475.7792: 4.27, 1505.0280: 13.94, 1562.294: 1.28}
json.dump({
    "half_life_s": 249.83 * 86400, "half_life_unc_s": 0.04 * 86400,
    "p_885": 0.784, "p_885_unc": 0.003,
    "p_1562": 0.0128, "p_1562_unc_plus": 0.0005, "p_1562_unc_minus": 0.0003,
    "gamma_energy_per_decay_kev": sum(energy * ri / 100 for energy, ri in GAMMAS.items()),
}, open("result.json", "w"), indent=1)
