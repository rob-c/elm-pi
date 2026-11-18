---
name: hep-columnar-analysis
description: "Array-at-a-time HEP analysis with uproot, awkward, vector, hist and coffea - jagged arrays, event and object masks, combinatorics, flattening, None, chunks, weights."
disable-model-invocation: true
---

# Columnar analysis: uproot, awkward, coffea

What goes wrong: a flattened array filled against weights of another length;
a cut applied to objects where an event cut was meant; events with no
candidate dropped or crashing without anyone counting them; a whole dataset
read into memory.

## Reading

- `uproot.open("f.root:Events")`, then `tree.arrays([...], library="ak")` with
  only the branches needed. Note `tree.num_entries`.
- Many or large files: `uproot.iterate(files, branches, step_size="100 MB")`
  and fill histograms chunk by chunk (they add). Do not concatenate arrays.
- Remote `root://` paths need an XRootD client - `hep-data-formats`.

## Two levels, and every mask lives at one

Muons are `N * var * {pt, eta, ...}`: axis 0 is events, axis 1 objects.

- Object level: `good = (mu.pt > 20) & (abs(mu.eta) < 2.4)`; `mu[good]` keeps
  every event and shortens its list.
- Event level: `sel = ak.num(mu[good]) >= 2`, one boolean per event. Apply it
  to every per-event array, the weights included.
- `&`, `|`, `~` with brackets round each comparison; never `and` / `or`.
- `vector.register_awkward()` and `ak.zip({...}, with_name="Momentum4D")` give
  `.mass`, `.deltaR()` and `+`. Name the components (`pt, eta, phi, mass`) -
  `hep-kinematics`.

## Combinations

- Within a collection: `ak.combinations(mu, 2, fields=["a", "b"])`, each
  unordered pair once. Between collections:
  `ak.cartesian({"mu": mu, "jet": jets}, nested=True)`; `nested=True` keeps
  the jets grouped per muon, so `ak.min(..., axis=-1)` is per muon.
- Best candidate per event:
  `i = ak.argmin(abs(pair_mass - target), axis=1, keepdims=True)`, then
  `ak.firsts(pairs[i])`. Without `keepdims=True` the index is applied along
  the wrong axis.
- An event with no pair gives `None`. Decide what happens to it
  (`ak.is_none`, `ak.fill_none`, `ak.drop_none`) and count how many there were.

## Flattening and weights

- `ak.flatten(x)` removes one level: one entry per object. Broadcast the event
  weight first, `w_obj = ak.broadcast_arrays(w, mu.pt)[0]`, and flatten both.
  `ak.flatten(x, axis=None)` removes every level - know which you called.
- Leading object: `mu.pt[:, 0]` fails on an empty event. Use
  `ak.firsts(mu.pt)` (None where empty) or select `ak.num(mu) >= 1` first.
  Collections are usually sorted by pT, not always:
  `mu[ak.argsort(mu.pt, ascending=False)]`.
- NumPy needs rectangular data: `ak.pad_none(x, n, clip=True)`, then
  `ak.fill_none`.

## Histograms

`hist.Hist(hist.axis.Regular(60, 60, 120, name="m", label="m [GeV]"),
storage=hist.storage.Weight())`, then `h.fill(m=..., weight=...)`. Weight
storage keeps the sum of squared weights (`h.variances()`) - see
`histogram-analysis`. A `StrCategory` axis with `growth=True` holds datasets,
regions or systematic variations. `uproot.recreate("out.root")["h"] = h`
writes it for ROOT.

## Scaling out

- coffea: a processor's `process(events)` returns accumulators that add;
  NanoEvents with a schema gives `events.Muon.pt`. Its API changed between
  major versions: read the docs for `coffea.__version__`, do not assume.
- dask-awkward is lazy: build every output, then one `dask.compute(...)`.
- Per dataset, keep the number of events and the sum of generator weights
  before any cut: the normalisation needs them (`hep-event-generators`), and a
  skim has lost them unless it stored them.

## Check before reporting

- Events read equal the trees' entries, over all files and chunks.
- A cut flow: events and sum of weights after each cut.
- Arrays filled together have one length and came through the same masks.
- One selected event printed and its candidate recomputed by hand.
- A known peak (Z, J/ψ) sits at its mass: units and four-vectors are right.
- How many events had no candidate, and what was done with them.

## Related

- Skills here: `scientific-python`, `histogram-analysis`, `hep-root`,
  `hep-data-formats`, `hep-kinematics`, `hep-event-selection`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `dask`, `matplotlib`, `get-available-resources`.
