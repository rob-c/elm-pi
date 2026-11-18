# ECAL prototype, module 3: electron energy scan in the H4 beam

- Electrons at 5, 10, 20, 50, 100, 150 and 200 GeV. The beam momentum spread is below
  0.1% and is neglected.
- testbeam.csv: one row per electron, with the beam energy and the energy
  reconstructed in the 5 x 5 crystal matrix around the impact point after the
  standard intercalibration and containment correction.
- 2000 electrons per energy after the beam-quality cuts (one track in the beam
  chambers, impact within 2 mm of the crystal centre).
- The beam line has scintillators and a wire chamber in front of the module. A
  few per cent of the electrons start to shower there and are reconstructed
  low; the selection does not remove them. As in the note on module 2, the
  resolution we quote is that of the Gaussian core of the response.
