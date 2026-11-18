---
name: hep-data-formats
description: "Particle-physics data formats and open data - ROOT TTree and RNTuple, NanoAOD, PHYSLITE, HepMC, LHE, YODA, HEPData, Parquet; good-run lists, XRootD, sample metadata, MeV versus GeV."
disable-model-invocation: true
---

# Particle-physics data formats and open data

Three slips account for most wrong first plots: MeV read as GeV; data used
without its good-run list, so the luminosity quoted does not match the events;
and simulation normalised by the number of entries in a skimmed file instead
of the sum of generator weights of everything that was generated.

## Know the file before analysing it

1. **List it.** Trees, branches, types and entries (`uproot.open(...).keys()`
   and `.show()`, or `TTree::Print`). Take branch meanings from the format's
   documentation, not from their names.
2. **Units.** ATLAS stores MeV and mm; CMS GeV and cm; LHCb MeV. HepMC
   declares its units in the file; LHE is in GeV. Confirm with a known mass
   peak (Z, J/ψ) before anything else. Luminosity: 1 /pb = 1000 /nb =
   10⁶ /μb (brilcalc's /ub ÷ 1e6). One luminosity section (23 s) holds
   well under 1 /pb: more means a unit slip.
3. **Simulation metadata.** Cross section (pb, fb or nb - check), filter
   efficiency, k-factor, and the sum of generator weights over all generated
   events, before any skim: NanoAOD keeps it as `genEventSumw` in the `Runs`
   tree, ATLAS derivations in the `CutBookkeepers`. The event weight is
   σ × L × w / Σw: predicted events = σ L × Σ(generator weights of the
   selected events) / Σ(`genEventSumw` over all `Runs` entries) - weights
   summed, not events counted. If the result looks absurd, suspect L's unit,
   not this formula.
4. **Data quality.** Apply the good-run list (CMS: a JSON of run to
   luminosity-block ranges; ATLAS: an XML list). The luminosity to quote is
   the one computed for exactly that list and that trigger, prescale
   included.
5. **Duplicates.** Two primary datasets of the same runs hold many of the
   same events. Put all the data files together first, then keep each (run,
   luminosity block, event number) once - one set across the files, not one
   per file - and print how many were dropped. The data count is the size of that
   set; n(A) + n(B) is wrong.

## The formats

- **ROOT TTree**: columns (branches) with jagged arrays; many files as one
  TChain. **RNTuple** is its successor and needs a recent ROOT or uproot.
- **NanoAOD** (CMS): a flat `Events` tree, per-object arrays such as `Jet_pt`
  counted by `nJet`, about a kilobyte per event; `Runs` and
  `LuminosityBlocks` trees beside it.
- **PHYSLITE** (ATLAS): calibrated objects in xAOD containers, readable with
  uproot and coffea schemas.
- **HepMC** (2 and 3): the generator event record - particles, vertices,
  status codes (1 is a stable final-state particle; other codes are
  generator-specific), weights. ASCII, so large.
- **LHE**: parton-level events before showering, with the run's beams and
  cross sections in its init block. Not a physical final state.
- **YODA**: Rivet's histograms. **HEPData**: published tables with each
  uncertainty separately, exportable as YAML, CSV, ROOT or YODA.
- **Parquet** keeps jagged structure (awkward arrays round-trip); **HDF5**
  wants fixed shapes: pad and carry a mask.

## Open data and remote files

- The CERN Open Data portal (opendata.cern.ch) publishes each dataset as a
  record with a DOI, file list, luminosity, triggers and usage notes. Read
  the record; cite its DOI.
- XRootD URLs (`root://host//path`) open directly in uproot and ROOT and
  fetch only the baskets read. That needs the network: a session with web
  access (`pi --remote`) or a host the proxy allows. For repeated
  work copy the files once.
- Read only the branches needed, in chunks (`hep-columnar-analysis`).

## Check before reporting

- Format, release or version, and where the branch definitions came from.
- Units confirmed with a known peak.
- Good-run list applied, and the luminosity that goes with it.
- Sum of weights taken before skimming; cross section with its source.
- Duplicate removal where datasets overlap.

## Related

- Skills here: `hep-columnar-analysis`, `hep-root`, `histogram-analysis`,
  `hep-event-generators`, `hep-literature-and-data`, `scientific-python`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `polars`, `dask`, `zarr-python`.
