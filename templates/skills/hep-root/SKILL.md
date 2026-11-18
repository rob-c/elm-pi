---
name: hep-root
description: "CERN ROOT 6 - macros under Cling and ACLiC, TFile/TTree/TChain, RDataFrame and implicit multithreading, histogram ownership and Sumw2, batch mode, PyROOT or uproot."
disable-model-invocation: true
---

# ROOT 6

What goes wrong: a histogram that vanishes (or crashes) when its file closes;
errors that are wrong after weights or scaling; a macro that only works
interpreted; and results that change when multithreading reorders the events.

## Running code

- ROOT 6 interprets C++ with Cling. CINT is gone, and what it tolerated
  (missing includes, `.` for `->`, undeclared variables) is now an error.
- Batch, no graphics, quit at the end: `root -l -b -q 'macro.C("arg")'`. In
  PyROOT call `ROOT.gROOT.SetBatch(True)` before the first canvas.
- Compile anything that loops over events: `macro.C+` (ACLiC; `++` forces a
  rebuild). Compiled code needs every include, and its warnings are real. The
  function must be named after the file; an unnamed `{ ... }` macro cannot be
  compiled or take arguments. Standalone builds: `root-config --cflags --libs`
  and `scientific-cpp`.

## Files and ownership

- A histogram or tree belongs to the current directory when it is created or
  read: usually the open TFile. Closing the file deletes it, and the pointer
  dangles. To keep it: `h->SetDirectory(nullptr)` straight after `Get`, or
  `TH1::AddDirectory(kFALSE)` once at the start. TGraph and fitted functions
  are yours from the start.
- After opening check `f->IsZombie()`; `f->Get<TH1D>("name")` is a null
  pointer when the name is wrong. List what is there with `f->ls()`.
- Writing: `obj->Write()` into the output file, then `f->Close()`. A job
  killed before `Close` leaves a file that needs recovery. Writing a tree
  twice makes cycles (`name;1`, `name;2`): pass `TObject::kOverwrite`.
- PyROOT: Python frees objects ROOT still draws or owns. Keep references to
  files, canvases and anything drawn.

## Histograms

- `TH1::SetDefaultSumw2()` at the top of every job. Without the sum of squared
  weights the error is √content, which is wrong after weighted fills, `Scale`,
  `Add` or `Divide`.
- Bin 0 is underflow and bin N+1 overflow. `Integral()` covers bins 1..N;
  `Integral(0, N+1)` includes both; `Integral("width")` multiplies by the bin
  width. `GetEntries()` counts fills, not the sum of weights.
- A ratio of pass to total is not `Divide`: use `TEfficiency`, or
  `Divide(pass, total, 1, 1, "B")` - see `hep-efficiency-measurement`.

## Trees

- `TChain` takes wildcards (`chain.Add("dir/*.root")`); a file with no such
  tree only shows up as a wrong entry count. Compare `GetEntries()` with what
  you expect.
- `SetBranchAddress` with exactly the branch's type (see `tree->Print()`): a
  `Float_t` branch read into a `double` is garbage, silently.
- `TTree::Draw` is for a first look, not for final numbers.

## RDataFrame

- Lazy: `Define`, `Filter`, `Histo1D`, `Sum`, `Count` only book. The event
  loop runs once, when the first result is read. Book everything, then read:
  reading between bookings runs the loop again each time.
- Name the filters (`Filter("pt > 20", "pt")`) and `Report()` is the cut flow.
  A weighted histogram: `Histo1D({"h", ";m [GeV];Events", 60, 60., 120.}, "m", "w")`.
- `ROOT::EnableImplicitMT()` before the frame is built. Entries are then
  processed in no fixed order: `Range` is unavailable, a `Snapshot` is written
  in a different order, and code in `Define` must be thread-safe. Sums agree
  with a single-thread run only to rounding.

## PyROOT or uproot

Reading trees and histograms into arrays needs no ROOT: `uproot`, see
`hep-columnar-analysis`. Use ROOT for RooFit, TEfficiency, classes that need
dictionaries, and RDataFrame's speed. A Python loop over tree entries in
PyROOT is slow: use RDataFrame. If ROOT is missing see `installing-software`
(conda-forge packages it).

## Check before reporting

- Ran from a clean start in batch mode, compiled, with no warning ignored.
- Entries read equal entries expected; no zombie file, no null pointer.
- Sumw2 on; whether integrals include under- and overflow is stated.
- With multithreading, a subset agrees with a single-thread run.
- The output file reopens and lists the objects; the ROOT version is given
  (`root-config --version`).

## Related

- Skills here: `scientific-cpp`, `histogram-analysis`, `hep-columnar-analysis`,
  `hep-roofit-models`, `hep-efficiency-measurement`, `hep-data-formats`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `matplotlib`.
