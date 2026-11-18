"""Writes environment/ for this task: one file of notes, no generated data.

    python make_environment.py <environment dir>

What the task turns on, none of it said in the notes: the flux is the Maxwellian
integral of n(v) v while the cross section is the 2200 m/s one, so the matching cross
section is (sqrt(pi)/2) sigma0; the irradiation, the wait and the count are each
comparable to the half-life and are given in hours, minutes and seconds; the TDC has an
arbitrary offset, so time zero comes from the gamma flash, which itself took L/c to
arrive; and the neutron is fast enough (14 MeV) that the non-relativistic energy is 2% low.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])
(out / "notes.md").write_text("""# Neutron lab log, 17 November

## Tomorrow: manganese foil in the thermal position T2

- Foil: Mn-Ni alloy, 88.0% manganese by mass, 50 um thick, mass 38.40 mg.
  Thin enough that self-shielding is below 0.5%: ignore it.
- Irradiation: 3 h 20 min at constant beam current.
- Then 47 min to get the foil out, over to the counting room and onto the
  detector.
- Count: 5400 s on HPGe 1, 25 cm shelf. The dead time will be under 1%: take
  live time = real time.
- Thermal flux at T2 at the nominal beam current, from the facility's
  characterisation report: 6.0e7 cm^-2 s^-1. The report defines it as the
  integral of n(v) v over the Maxwellian thermal spectrum, neutron temperature
  293.6 K. The cadmium ratio there is above 300: epithermal activation is
  negligible.

Data:

- Mn-55: isotopic abundance 100%, molar mass 54.938 g/mol.
- Mn-55(n,gamma)Mn-56: sigma0 = 13.36 b at 2200 m/s (0.0253 eV), 1/v through
  the thermal range (Westcott g = 1.000).
- Mn-56: half-life 2.5789 h. 846.8 keV gamma ray, emission probability 0.9885.
- HPGe 1, 25 cm shelf: full-energy-peak efficiency 8.62e-4 at 846.8 keV.
  Coincidence summing is negligible at that distance.
- Avogadro constant 6.02214e23 per mol.

## Today: time-of-flight check on the fast line

- Flight path, neutron-producing target to detector: 20.00 m (surveyed).
- TDC time spectrum, calibrated in ns, later arrival = larger time; the scale
  has an arbitrary offset from the cable delays. Centroid of the gamma flash
  from the target: 118.4 ns. Centroid of the neutron peak: 437.1 ns.
- Neutron rest energy 939.565 MeV; c = 0.299792 m/ns.
""")
print("notes.md written")
