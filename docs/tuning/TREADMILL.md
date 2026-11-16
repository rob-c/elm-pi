# The testing treadmill, a brief for six areas it has not covered, and the questions it can answer

For an agent picking this up to investigate how well elm-pi does **data
analysis, data modelling, image analysis, plotting, reading plots, and reading
and parsing text and academic papers**. It describes the loop that found and
fixed elm-pi's defects on 2026-11-13 and 14, the tools it runs on (now in this
repository), what it has and has not measured, and how to extend it to those six
areas. Read `AGENTS.md` at the repository root first: where to work, and what
the tests hold every change to.

What is in this file:

| Section | What it answers |
|---|---|
| [What the treadmill is](#what-the-treadmill-is) | the five-step loop, and the three things that make it more than "run it and look" |
| [The tools](#the-tools) | what each script does, the `runs.json` fields, and how a batch is started |
| [What the reports record](#what-the-reports-record) | every heading `analyze.py` writes, every column `summary.py` prints, and the quantities neither reads |
| [Where a batch's files land](#where-a-batchs-files-land) | install, project folders, reports, scores |
| [Rules that were learned the hard way](#rules-that-were-learned-the-hard-way) | seven, each learned from a batch that went wrong |
| [Where the evidence goes](#where-the-evidence-goes) | JSON, the dated README section, the tests that hold it |
| [From a task set to a batch](#from-a-task-set-to-a-batch) | six steps from seeds and checks to a scored table |
| [What is already known about the six areas](#what-is-already-known-about-the-six-areas) | what has run, what happened |
| [The brief: one scored task set per area](#the-brief-one-scored-task-set-per-area) | what to build, per area |
| [Questions the treadmill can answer](#questions-the-treadmill-can-answer) | nine questions, each with its answer as of 2026-11-14 or the run that would settle it |
| [Order of work](#order-of-work) | baseline first, then one fix at a time |

## What the treadmill is

One loop, run until it stops finding things:

1. **Build** a fresh elm-pi install from the working tree, the way a new user's
   would be built (`bootstrap.sh`).
2. **Drive** real sessions against it, on the university's ELM models, with the
   prompts a user would type - no hints, no special flags.
3. **Read** what happened: every tool call, error, refusal and dialog, the
   final reply, and what was left on disk, checked independently of what the
   session said about it.
4. **Fix** what went wrong *in elm-pi* - a guard, a skill, a prompt, the
   launcher - and pin it with a regression test that fails on the old code.
5. **Build again** and rerun the cases that failed, to see the fix act in a
   live session, not only in a unit test.

Three things make it more than "run it and look":

- **The check never trusts the session.** A site is audited with the `view`
  tool's own functions after the session ends; a fit is compared with one
  computed separately; a coding task is scored by a check the session never
  sees. A reply that says "verified" is a claim to test.
- **Every fix has a test that fails without it**, and a line in
  `tests/test_session_regressions.py` naming the session that showed the need.
- **Numbers, with their limits stated.** Two runs a task shows 11 against 16
  and does not rank two prompts a point apart. Say which you have.

### What it has found

In about 150 driven sessions - 50 website sessions in six batches, about 40 earlier one-at-a-time sessions, and 56 scored coding runs - plus the checks on each:

| Kind of defect | Examples (all fixed, all tested) |
|---|---|
| A guard that loops or kills | `claim-guard` sent the same note 189 times to a sub-agent retried after a 429; `wait-guard` ended a turn with an abort, which pi-subagents reads as the user's Esc - three sessions of three never ran again |; the end-of-run page check sent 45 of 210 sub-agents back over their siblings' unfinished pages, 19 of them for more than 20 turns
| Cost with nothing failing | Two sub-agents took 140 and 98 turns of small edits, 21M of a session's 26M tokens; a parent ran the same `ls` 91 times while its children worked |
| A confident wrong answer | A half-life of 145.1 ± 1.3 s from a minimiser that had stopped short (the minimum was 151.5 ± 2.7); a peak time in a reply that was in no output, past a truncated preview |
| "Verified" over something broken | "100% self-consistent" with a stylesheet asking for a missing picture; a gallery of placeholder-service photos called complete; "validated all image paths" on a site whose every picture was in the session's hidden scratch folder |
| The machine, not the model | `pip install --break-system-packages` into Homebrew's Python; `view a.jpg` typed into bash opening vi for 14 minutes |
| Fixes that stop at the example | 5 of 16 harder coding runs: a copy that still shared what was nested in it, a parser that took 25:00:00 |

Two of the guard defects were regressions from earlier fixes. Unit tests did not
catch them; a batch of real sessions did. **A change to a guard is not finished
until a batch has run on it.**

## The tools

All under `docs/tuning/harness/`. Nothing here needs the network beyond what a
session itself uses.

| File | What it does |
|---|---|
| `treadmill/batch.sh <name> <runs.json> [jobs]` | Builds one fresh install from the working tree, then drives every run in `runs.json` against it, `jobs` at a time, each in its own project folder; writes a report per run and a summary table |
| `treadmill/drive.mjs` | Drives one session over `pi --mode rpc` as a user at the keyboard would: sends the prompts in order, answers each permission dialog once, waits for background sub-agents to report before calling the session done |
| `treadmill/analyze.py` | One report per session from its transcript: cost and shape, session facts (the floor, the largest request, compactions, skills routed, what it viewed), errors and refusals, extension messages, dialogs, the final reply, and an audit of any site left on disk |
| `treadmill/audit.mjs` | That audit: every folder of pages compared, every page's resources, every image file's bytes - with `view-outputs.ts`'s own functions |
| `treadmill/summary.py <out dir>` | One line per run - finish, time, tokens, sub-agents, errors, dialogs, pages, images, whether navigation and footer match, how the last turn ended - and every error and refusal grouped by kind |
| `treadmill/score.py <name> <dir with checks/>` | For scored tasks: runs each task's hidden check in its project folder with the install's own Python; a table, and `scores.json` |
| `coding/make_tasks.py <dir>` | The harder coding benchmark: writes `seeds/`, hidden `checks/`, reference `solutions/` and `tasks.json`. The model for a task set in any area below |

A run in `runs.json`:

```json
{"id": "fit-halflife.1",
 "flags": ["--auto", "--no-computer-use"],
 "prompts": ["Fit the half-life from counts.csv, with an uncertainty, and plot the data and the fit."],
 "seed": "/path/to/seeds/fit-halflife",
 "max": 1500}
```

`seed` is copied into the project folder and committed as a git repository
before the session starts. Several `prompts` are sent in order, each after the
previous turn and its background work have finished: that is how a follow-up
("is that weighted properly?") is tested.

The fields, and what each one changes:

| Field | What it does |
|---|---|
| `id` | The run's name. The project folder is `b<NAME>-<id>`, the report `out/<id>/report.md`. A scored run is named `<task>.<n>`, because `score.py` strips the last `.n` and runs `checks/<task>.py` |
| `flags` | Passed to `pi` before `--mode rpc`. Most batches used `--auto` and `--no-computer-use`. The permission mode is a flag here: none (manual, where new sessions start), `--read-only-auto`, `--auto` or `--yolo`; in manual and read-only-auto the driver answers each dialog as a user would |
| `prompts` | Sent in order, each after the previous turn and its background work have finished. One entry is a single-turn task; three are a conversation, which is the only way a follow-up is tested |
| `seed` | Copied into the project folder and committed (`git init`, one commit, "the project as it was") before the session starts. Omitted: an empty folder, which is what a write-from-scratch task wants |
| `max` | Seconds before the driver stops the session regardless. Default 2400 through `batch.sh` (3600 if `drive.mjs` is called directly) |

What the driver does while a run is going, because it decides what a report
means:

- **It answers each dialog once, and never "for the session".** `recommended`
  wins if it is offered; otherwise an allow/yes/approve wording that is not
  qualified by session, always, forever or all; anything naming `brew`, `sudo`,
  `softwareupdate`, `port`, `--user`, `break-system`, `--system`, a global npm
  install or `gem install` is declined; `confirm` gets yes; `input` and `editor`
  get "Go ahead with what you think is best." Every dialog and the answer taken
  are in `rpc.jsonl` and in the report.
- **It requeues rather than drops.** A prompt sent while pi is mid-run (a
  rate-limit retry counts) is sent again as a follow-up - the driver's own bug
  on 2026-11-14 was a follow-up dropped in exactly that window.
- **It waits for background work.** A `subagent` or `workflow` launch is read
  from the session file, and the session is not called done while one is
  unreported. The next prompt goes out when the turn has ended, nothing is
  outstanding and 20 s have passed; a run is done when the last turn ends and
  nothing has happened for 30 s; with background runs outstanding it waits, and
  gives up after 30 minutes of no activity. `max` stops it regardless, and the
  log then says `"finish":"time limit"` - a session cut off, not one that ended.
- **It logs the retries.** `auto_retry_start` and `auto_retry_end` go into
  `rpc.jsonl`; the retry counts quoted further down come from there and from
  `analyze.py`'s "Retries" section.

To run it:

```bash
export ELM_PI_ENV_FILE=/path/to/an/.env/with/ELM_API_KEY    # copied mode 600, never printed
export TREADMILL_WORK=~/sandbox                              # installs and projects go here
docs/tuning/harness/treadmill/batch.sh fit1 runs.json 2
python3 docs/tuning/harness/treadmill/score.py fit1 /path/to/dir-with-checks
```

`batch.sh` refuses to reuse an install name. A batch of eight website sessions
takes 30 to 60 minutes and 20 to 50 million ELM tokens; eight short analysis
tasks take about 15 minutes and 1 to 3 million.

`TREADMILL_SETTLE_SECONDS` changes the final 30-second quiet period. It accepts
a non-negative number and is mainly useful for local harness tests; normal runs
should keep enough time for delayed RPC and background-completion notices.

For repeated local installs without downloading dependencies again, set
`TREADMILL_FROM=/path/to/a/working/install`. The batch copies the working tree
as usual, then runs that copy's `scripts/dev-setup.sh --from` against the given
install. The Python launcher and rendered extensions still come from the
working tree. This omits the optional analysis Python environment; stdlib
checks use the interpreter recorded in `agent/python-path`.

A failed bootstrap stops the batch before any sessions start. A missing or
prematurely exiting launcher and a time limit make the driver fail, and a
failed driver or analyzer makes the batch exit nonzero after saving the
remaining reports and summary. RPC extension errors are recorded in the log;
a startup failure without a session file retains its stderr in the report.
The driver's pipes decode UTF-8 across chunks, so split characters survive
in the recorded text. On macOS and Linux each driven launcher has its own
process group, which the driver stops on completion, timeout or interruption;
this also closes pipes left open by tools after a launcher crashes.
Deadlines and elapsed seconds use a monotonic clock, so a wall-clock adjustment
cannot expire a healthy run; the log's readable timestamps still use wall time.

### What the reports record

`analyze.py` writes one `report.md` per run, in this order: **Steps** when the
batch kept a `steps.txt`, **Cost and shape** (wall time, model turns, input and
output tokens), a per-session section for the parent and for each child,
**Sub-agent children** and **Workflow runs** with each child's exit code, turns
and tokens, **Total tokens (parent + children + workflows)**, **Session facts**
(first and largest request, compactions, skills the router put in full or named,
`SKILL.md` files read, `view` calls against the pages and figures the session
wrote), **User prompts**,
**Errors and refusals (parent)** as `time TOOL ERROR: message`, **Extension
messages** (everything except `skill-routing`), **Dialogs answered** (up to 40),
**Retries** (up to 30), **stderr**, **Final reply**, then the audit of what was left on
disk: **Files**, **Comparison per folder of pages**, **Page notes**, and **Image
files that are not images**.

`summary.py` reads those reports into one table: run, finish (with how the last
turn ended), wall, tokens, children, errors, dialogs, pages, images, a
nav/footer comparison (`same`, `same+notes` when the only remarks are a
picture nothing uses or a page nothing links to, `DIFF` when a repeated part
really has several versions), page notes, and image files that are not images,
followed by every error and refusal grouped by kind. Its page and image columns are
website-shaped: a batch of analysis tasks shows `0` in them, which is not a
finding.

`score.py` writes one row per run - pass, wall, turns, tokens, and the last line
of the check's stderr when it failed - prints the table, ends with
`N/M passed, X tokens`, and saves `scores.json` beside the reports. It runs each
`checks/<task>.py` in the run's project folder with the *batch's own* install
Python (`agent/python/env/bin/python`, or its recorded interpreter when the
optional environment was not installed), `PYTHONPATH=.:src`, a 300 s timeout, and
exit 0 meaning pass.

What was not recorded when this file was first written, and is now (in
**Session facts**, added 2026-11-14 after each had been pulled by a throwaway
script more than once): compactions, the first and largest request, which skills
the router put in full or only named and whether a `SKILL.md` was then read,
and `view` calls against what the session itself wrote.

What still is not, and cannot be from these files:

| Not recorded | Why |
|---|---|
| cache reuse per turn | ELM's replies carry no cache figures: `cacheRead` and `cacheWrite` are 0 in every one of 319 session files (205M input tokens). Whether the gateway reuses a prefix is invisible from the session; see question 8 |
| what a sub-agent viewed | Session facts covers the top session. A child's `view` calls are in its own file under `.pi/sessions/<session>/<child>/run-0/` |

Dialogs are the one question already answered from the reports: "Dialogs answered"
gives each one's title and the answer taken, so a permission mode's cost in
questions can be counted today.

### Where a batch's files land

All of it outside the repository:

```
$TREADMILL_WORK/
  elm-pi-b<NAME>/                 the install, built once per batch
  b<NAME>-<run id>/               one project folder per run, a git repo from the seed
$TREADMILL_OUT/b<NAME>/
  bootstrap.txt                   the install's own output: extensions loaded, failed, commit
  steps.txt                       one line per step, with the time
  <run id>/rpc.jsonl              the driver's log: prompts, dialogs, retries, tool calls
  <run id>/report.md              analyze.py's report
  <run id>/analyze.err            its stderr, not its findings
  summary.md                      summary.py's table and error kinds
  scores.json                     score.py's result, one row per run
```

A project folder is left exactly as the session left it - that is what the audit
reads and what a scorer runs against, so do not clean one up before reading it.

### Rules that were learned the hard way

- **It runs on a real machine, as a real user.** The driver answers dialogs for
  that user. It declines anything that changes shared software (`brew`, `sudo`,
  `--user`, `--break-system-packages`, global npm or gem) - an earlier version
  said yes to everything, and a session installed ImageMagick into the owner's
  Homebrew. After a batch, read the test install's `agent/installs.log` and
  report anything outside the project. Ask before undoing it.
- **The key is never printed**, logged, or put in a file that is committed.
  `ELM_PI_ENV_FILE` is copied, not read. Every session spends the owner's
  allocation: say what a batch is expected to cost before a large one.
- **Three multi-agent sessions at once saturate the gateway.** ELM rate-limits
  at about four Qwen sessions in flight; a batch of three ten-agent sites spent
  30 minutes each in 429 retries, and the same sites alone took 7 to 13. Use
  `jobs` 2 for sub-agent work, 3 for single-session tasks. Do not read a
  timing taken under a storm as the model's.
- **A session that ends is not a session that worked.** `summary.py` prints how
  the last turn ended: `done (last turn: aborted)` is a dead session. One bug
  went a day unseen because nothing printed that.
- **Prove a check before trusting a score.** Every hidden check must fail on the
  seed and pass on a reference solution, run before any session is scored. That
  step caught a wrong reference of the author's own. When a failure turns out to
  be the check's fault - an assertion the prompt did not justify, an input the
  spec could fairly reject - correct the check, rescore **every** arm, and say
  so in the record.
- **The harness has bugs too.** Six "elm-pi failures" on 2026-11-14 were the
  harness's: a follow-up sent while pi was mid-retry and dropped; `--user-agent`
  read as `--user` and the downloads declined; a scorer that could not import
  the session's code; the audit running its raster check on a real `.svg`; the
  summary printing `DIFF` for a site whose only remark was an unused picture;
  and a count of dialogs by each command's first word, which took
  `cd images && curl -o ...` for reading and doubled a figure a decision was
  made on. Rule the harness out before changing elm-pi, and read a command
  whole before classifying it.
- **Keep private paths out of what is committed.** `tests/test_tuning_evidence.py`
  scans `docs/tuning/` for them.

## Where the evidence goes

`docs/tuning/` is the record, and `tests/test_tuning_evidence.py` and
`tests/test_session_regressions.py` hold it to the numbers:

- raw results as JSON under `docs/tuning/<date>/` (per-run pass, tokens, turns,
  the reason for each failure), with any corrections to checks listed;
- a dated section in `docs/tuning/README.md`: what was measured, the table, and
  **what it is not** - sample size, what the set can no longer show;
- a test that the numbers the notes quote are the numbers in the JSON;
- for a change to behaviour, a class in `tests/test_session_regressions.py`
  whose docstring names the session and whose test fails on the old code.

`2026-11-14/coding-benchmark.json` and the "a coding benchmark" section of the
README are the worked example.

`tests/test_tuning_evidence.py` also scans every file under `docs/tuning/` for
private paths: a home folder is written `~/sandbox` or `/Users/you`, never a
real name, and no key ever appears, not even a fragment.

## From a task set to a batch

Six steps, and the first two happen before any model spends a token:

1. **Write the set.** `seeds/<task>/` with the input files; `checks/<task>.py`,
   which exits 0 for a pass and must print why not; `solutions/<task>/` holding
   the files a correct answer leaves, laid over the seed; and `tasks.json` with
   one prompt per task. `coding/make_tasks.py` is the worked example, and note
   that it deletes and rewrites `seeds/`, `checks/` and `solutions/` under the
   directory it is given.
2. **Prove every check both ways.** Run `checks/<task>.py` in a copy of the
   seed - it must fail - and in a copy with `solutions/<task>/` laid over it - it
   must pass. This caught a wrong reference solution of the author's own. That
   two-way proof is all the coding benchmark (`coding/make_tasks.py`) has, and
   it was not enough: two of its checks were stricter than their prompts and
   were corrected after sessions failed them. The older tuning suites
   (`harness/ab*.py`, `hard*.py`) go further - each check is held to 23 correct
   answers written differently and 61 plausible wrong ones
   (`harness/solutions.py`: `ALTERNATIVES`, `NEAR_MISSES`;
   `tests/test_tuning_tasks.py`). A new set should do that from the start.
3. **Write `runs.json` from `tasks.json`.** One run per task per round, `id`
   `<task>.<n>` with `n` the round, `seed` pointing at `seeds/<task>`, and the
   same `flags` for every run. Two rounds is the minimum: one run per arm tells
   you nothing a repeat would not contradict.
4. **Run the batch**, `jobs 2` for anything that fans out to sub-agents and 3
   for single-session tasks.
5. **Score it**, `score.py <name> <the dir holding checks/>` - the same directory
   `make_tasks.py` wrote, not the batch's output.
6. **Record it**, as the section above says: the JSON, a dated README section
   with what the set cannot show, and the test that holds the notes to the
   numbers.

If a check turns out to be the check's fault - an assertion the prompt did not
justify - correct it, rescore **every** arm from the sessions already on disk,
and say so; the sessions do not have to be run again.

## What is already known about the six areas

Not much, and it is uneven. These are the sessions that touched them:

| Area | What was run | What happened |
|---|---|---|
| Data modelling | Ba-137m decay counts, half-life with uncertainty (three runs, then in the benchmark) | Right method named, wrong answer twice: `scipy.optimize.minimize` reported "converged" 15 units of -2 ln L above the minimum. A warning in the skill changed nothing; a copy-ready `iminuit` fit in `data-fitting` did. Now 151.5 ± 2.7 s every time |
| Data modelling | Dimuon mass peak on an exponential background | Mass, width and yield within 1σ of the truth; a likelihood-ratio significance; said the width was resolution, not the natural width |
| Data modelling | Mauna Loa CO2 trend | Plausible number, wrong method: a straight line with an invented "intrinsic scatter" to reach χ²/ndf ≈ 1. The skill now says to fix the model, not the errors |
| Data analysis / notebooks | Bateman decay chain in a Jupyter notebook | Notebook correct; the reply's table had a number that was in no output, invented past a preview cut at five lines. `notebook-outputs.ts` now says the preview is cut and how to read it whole |
| Plotting | Pendulum period against amplitude; photoelectric stopping voltage; the fits above | Plots correct when looked at afterwards - but in several sessions the model described a plot it had not opened with `view` |
| Reading papers | "The paper that announced GW150914", download and summarise with page references | Fast, and the wrong paper: the companion detector paper. The research prompt now says to check the title and abstract against the request |
| Image analysis | Only website pictures: is this file an image, does it show the subject | `view` catches a text file named `.jpg` and a web error page saved as a picture. Nothing has measured whether the model can *read* an image |
| Reading plots | Nothing | - |
| Parsing text | A log-format parser written from a spec (coding benchmark) | 0 of 2 without the `changing-code` skill, 2 of 2 with it. Nothing has measured extraction from prose |

So: modelling has three findings and three fixes; the others have at most one
session each, and reading plots and image analysis have none. Both models here
take images (`templates/models.json`: `input: ["text", "image"]`), and the
`view` tool is how a session looks at one.

What a session has to work with: the agent's own Python in every install
(numpy, scipy, pandas, matplotlib, h5py, uproot, iminuit, sympy, pyarrow,
openpyxl, the Jupyter tools, pytest), and the routed skills `data-fitting`,
`uncertainty-propagation`, `statistics-and-significance`, `histogram-analysis`,
`numerical-methods`, `scientific-python`, `physics-documents`. A skill is routed
by `templates/extensions/skill-router.ts` from words in the request; whether it
*was* routed is in the session file, and "the skill said so and was not loaded"
is a different finding from "the skill was loaded and ignored".

## The brief: one scored task set per area

The method that worked for coding: tasks with **a known right answer**,
**inputs generated** so that the truth is exact and nothing can be looked up,
**a hidden check**, each run at least twice, and a baseline before any change.
Build each set the way `coding/make_tasks.py` builds its: seeds, checks,
reference solutions, and a validation step.

For every area, ask the session to write its answer to a small JSON file as
well as saying it. A number in prose cannot be scored reliably; a number in
`answer.json` can. Score the file, and separately read the reply for claims the
file does not support.

### 1. Data analysis

*Can it get the right numbers out of data someone hands it?*

- Seeds: generated CSV, Excel and HDF5 files with planted difficulties - a
  units column that changes halfway, missing values written three ways,
  duplicated rows, one sensor with an offset, timestamps in two time zones, a
  header on line 3.
- Tasks: a grouped summary; "which runs are anomalous and why"; a join of two
  tables on a key with stray whitespace; a resampling to hourly means.
- Check: the numbers, to a stated tolerance; that the planted problem was
  handled *and reported* (the reply or a `notes` field names it); that the
  input files are unchanged (`git diff`).
- Watch for: silently dropped rows; a mean over mixed units; an answer taken
  from `head` of the file; pandas defaults deciding the result (`dropna`,
  integer division, `ddof`).

### 2. Data modelling

*Can it fit a model, and is its uncertainty right?*

The area with the most findings, so the place to go deeper rather than wider.

- Seeds: data generated from a known model with a fixed random seed - Poisson
  counts with background, a weighted straight line with errors on both axes, two
  overlapping peaks, a model with strongly correlated parameters, a case where
  the right answer is "these data cannot distinguish the two models".
- Tasks: fit with uncertainty; compare two models; give a derived quantity with
  its propagated error; say whether the fit is acceptable.
- Check: estimate within a stated number of σ of the reference (computed
  independently, by a different method where possible); the quoted uncertainty
  within about 20% of the reference's; the goodness-of-fit statement consistent
  with the data.
- **Coverage, not just one fit.** Generate the same task from twenty seeds and
  count how often truth lies inside the quoted 1σ interval. Near 68% is
  right. This is the test that catches an uncertainty that is habitually half
  what it should be, which one run cannot.
- Watch for: a minimiser taken at its word; unweighted fits to counts; errors
  rescaled until χ²/ndf is 1; a p-value reported and not acted on; a literature
  value blamed on the apparatus when the fit is at fault.

### 3. Image analysis

*Can it read what is in a picture?* Nothing measured yet.

- Seeds: images **generated** with known content - N dots to count, two markers
  with a scale bar to measure between, a dial or gauge at a known reading, a
  table rendered as a picture, an oscilloscope-style trace with a known period,
  a micrograph-like field with a known particle size distribution.
- Tasks: count, measure, read a value, transcribe a table, say which of four
  panels differs.
- Check: the number within tolerance; for transcription, cell-by-cell agreement.
- Two questions to keep apart: can the *model* read it when shown (`view`), and
  does the *session* choose to look, or does it write code - OpenCV, PIL - and
  is that code's answer right? Record which route each run took. A session
  that answers without either has guessed.
- Watch for: an answer with no `view` call and no analysis code; counts that
  are round numbers; a measurement in pixels reported as millimetres; `view`'s
  own size limits changing what the model was shown.

### 4. Plotting

*Does the figure say what the data say, and can it be read?*

A plot is hard to score by eye and easy to score by structure. Do both.

- Tasks: plot seeded data with requirements stated the way a supervisor would -
  "log y", "error bars", "the fit as a line and the data as points", "units on
  both axes", "residuals underneath", "readable when printed in a column".
- Check, structural: require the script as part of the deliverable, re-run it
  with a small hook that walks the matplotlib figure, and assert what is there -
  axis scales, labels containing units, number of artists of each kind, that
  the plotted arrays equal the data (not a subset, not a smoothed copy), that
  error bars have the lengths the data give, that the file exists at the size
  asked for and is not blank.
- Check, visual: render it and look, with `view` and with your own eyes -
  overlapping labels, a legend over the data, a colour scale with no bar, tick
  labels like 1e-13.
- Also record: did the session `view` its own figure before describing it?
  In several sessions it did not, and described it anyway.
- Watch for: a correct script and a stale image; a default axis range hiding the
  point of the plot; a fit drawn only at the data's x values.

### 5. Reading plots

*Given only a picture of a plot, can it get the numbers back?* Nothing measured.

- Seeds: PNG and PDF plots **generated from known numbers**, with the data not
  in the project: a peak at a known position and width, a line with known slope
  on log-log axes, two curves crossing at a known point, a histogram with a
  known mode, an exclusion plot with a known limit at a given mass, a figure
  with two y axes.
- Tasks: "where is the peak", "what is the slope", "at what x do they cross",
  "what is the value at x = 3", "which curve is higher above 10 GeV".
- Check: within a tolerance set by how well a careful person could read that
  plot - tick spacing over five is a fair first choice. State it per task.
- Vary one thing at a time: linear against log axes, with and without grid
  lines, resolution, a legend that must be read to know which curve is which.
- Watch for: answers that are tick labels; log axes read as linear; the right
  number from the wrong curve; confident precision the picture cannot support.
  A good answer says how well it can be read.

### 6. Reading and parsing text and papers

*Can it find, extract and attribute?*

Two halves, scored differently.

- **Generated documents, exact truth.** Build PDFs (LaTeX in a container, or
  any tool that makes real multi-page PDFs) with planted facts: a number in a
  table on page 7, the same quantity given differently in the abstract and the
  results, a definition in a footnote, a value that appears only in a figure
  caption, a reference list with one retracted item. Ask for values *with the
  page each comes from*. Check the value and the page. A right number with a
  wrong page is a failure: the page is what lets a reader check.
- **Real papers, with `pi --remote`.** A handful where the right paper and the
  right numbers are known in advance and stable (a discovery paper and its
  companion; two versions of one arXiv entry; a paper and its erratum). Check
  *which document was used* before checking any number: the one recorded
  failure in this area was a correct summary of the wrong paper.
- Parsing: semi-structured text with a written format (instrument logs, a
  results table in prose, BibTeX with errors), extracted to JSON; check
  field-by-field, including that invalid input is rejected and counted.
- Watch for: numbers that are plausible and not in the document; a page
  reference to where the number *ought* to be; a summary written from the
  abstract; a table read across the wrong row; `read` on a compressed PDF
  returning nothing and the session carrying on.

## Questions the treadmill can answer

The point of all of it. Each question below is answerable on this machine with
the models this install serves; each names the run and what would settle it.
Settle the cheap ones before building a task set for the expensive ones. A
question becomes work on elm-pi only when its answer would change a decision,
and the bar at the end of this file still applies to what it opens.

**Do not spend a batch re-answering these.** Which ELM model is better on short
agent tasks: Qwen (137 of 150 against Mistral's 112 and Llama's 45). Whether
to turn thinking on for Qwen: it was measured about 400 times slower and left
off; its quality with thinking on was not re-measured, so "no gain" is not on
record - question 42 in `deepseek_suggestions.md` is the open part. Temperature, `top_p`,
`top_k`, `min_p` and the presence penalty: the shipped figures, swept twice,
nothing below p 0.5. Which model reads images better: Qwen, 96% of planted
changes against Mistral's 84%, with 0.4 false reports against 1.1. Which model
summarises a compaction better: Qwen keeps 10-11 of 11 facts on the real 74k
session against Mistral's 9-10, and is 44-63 s per summary against 7-13 s, so
Qwen is the primary route and Mistral the fallback for time. The numbers and
their limits are in `docs/tuning/README.md`.

### 1. What does a session's floor cost, and what does a narrower tool set buy?

Every request starts with the system prompt, the skill list and every tool
definition before any work is in it: 19-26k tokens, measured, and about 4M
across a 195-turn session. What is not measured is what cutting it costs in
*passes*.

*Run:* the coding benchmark as it stands, and the same `runs.json` with
`excludedTools` widened, both at `jobs 3`.
*Settles it:* passes at the same round, and input tokens per task, compared pair
by pair as `harness/paired.py` does. *Cost:* two rounds of the 16-task coding
set.

**Answer so far (2026-11-14).** The floor, measured as the first request of
each top session: **26,452 tokens** (median of 46 website sessions: `--remote`,
the web tools and a routed skill), **19,074** (56 coding sessions, no web), and
**10,065** under `pi --fast`, which loads the policy and nine local extensions
and none of the tool packages. So the tools and their definitions are 9k to 16k
of every request, and `--fast` is the narrow set already built. What it costs
in passes, on the 16-run harder coding benchmark:

| Install | Passed | Tokens | Model turns |
|---|---|---|---|
| full | 16 of 16 | 3.68M | 165 |
| `pi --fast` | 14 of 16 | 1.74M | 144 |

Half the tokens for two passes, and the two failures (`sql-join`, `state-leak`)
are tasks that fail in other arms as well; by question 3 a two-pass difference
on this set is inside the spread of two identical rounds. So for single-session
coding work the tool packages cost about as much again as the work itself, and
buy no measurable passes here. They are what a session needs for sub-agents, the
web, notebooks and anchor edits, none of which these tasks use - the result says
nothing about work that does. It is in `2026-11-14/coding-benchmark.json` as
`skill-wide-route-fast`. Not yet run: the middle question, which tool
definitions could be dropped from the *full* install without `--fast`'s losses.

### 2. How wide can one job's fan-out be before the gateway starts retrying?

ELM rate-limits Qwen at about four sessions in flight, and a batch of three
ten-agent sites spent 30 minutes each in retries where the same sites alone took
7 to 13. What is not known is where one job's own fan-out crosses that line,
because every batch so far ran three sessions at once.

*Run:* one ten-agent job, alone, at 4 children at a time and at today's width.
*Settles it:* wall time, `auto_retry_start` counts from `rpc.jsonl`, and runs
lost. *Cost:* two runs, under an hour - the cheapest measurement in this file.

**Answer so far: not settled, and the batches cannot settle it.** Parent-session
retries per batch of website sessions:

| Batch | Sessions at once | Retries, all parents | Most in one session | Median wall |
|---|---|---|---|---|
| 1 | 3 | 11 | 11 | 8 min |
| 2 | 3 | 63 | 21 | 11 min |
| 3 | 3 | 2 | 1 | 14 min |
| 4 | 3 | 137 | 73 | 19 min |
| 5 | 2 | 45 | 22 | 15 min |
| 6 | 2 | 17 | 7 | 14 min |

Three at once ranged from 2 to 137, and two at once from 17 to 45: the spread
within a setting is larger than the difference between them, the machine was
under another job's load for two of these, and children's retries are not in
these counts at all. One ten-agent session did finish in 9 min 25 s with no
dead time in batch 6 against 30 min in batch 4. The run named above - one job,
alone, at two widths - is still the only thing that answers this.

### 3. How far apart are two runs of the same task?

This is the number every other comparison must beat, and it has only been
measured on the tuning suites: three identical Mistral arms passed 109, 113 and
117 of 150, a spread of 8 runs from no change at all, and in batch 1 Mistral's
own repeat finished 6.0 points ahead of its control (p 0.15). On driven
sessions, nobody has measured it.

*Run:* any eight-task set, twice, same flags, same hour.
*Settles it:* the spread between the two arms. Until it is known, a one- or
two-run difference in a session batch is not a finding.

**Answer (2026-11-14), from the harder coding benchmark,** whose three arms each
ran the eight tasks twice on one install in one batch:

| Arm | Round 1 | Round 2 | Tasks whose two runs disagreed |
|---|---|---|---|
| no skill | 6 of 8 | 5 of 8 | 1 (`sql-join`) |
| skill, narrow route | 7 of 8 | 7 of 8 | 2 (`slow-export`, `state-leak`) |
| skill, wide route | 8 of 8 | 8 of 8 | 0 |

So on eight tasks, two identical rounds differ by 0 or 1 pass in total while 1
or 2 individual tasks flip: **a difference of one or two passes between arms of
this size is noise; three is where it starts to mean something.** Tokens vary
far more than passes - the same task's two runs differed by a median factor of
1.2 to 1.9 and by up to 2.7 - so a cost comparison needs more repeats than a
pass comparison does. The 11 to 14 to 16 across the arms is 3 and then 2 passes:
the first step is outside this spread, the second is not on its own, and the
case for it is that it came with the skill reaching more tasks (question 5).

### 4. How many dialogs does a session need, and where do they come from?

`analyze.py` already prints every dialog answered, with its title. What is not
known is what a permission mode costs in dialogs per task.

*Run:* one eight-task set with `--manual`, the same with `--read-only-auto`
(added 2026-11-14: manual, with shell commands that can only read inside the
project running unasked), and the same with `--auto`.
*Settles it:* dialogs per task, grouped by the title of the ask, which is what
`report.md` prints. What is known so far, from website sessions only: manual
drew 12 to 40 dialogs a session, of which 22% (38 of 172 over seven sessions)
were for reading; the first three read-only-auto sessions drew 23, 28 and 48,
none of them for reading - the rest were downloads, web searches, edits,
`mkdir` and `sleep`. Group by the **whole command**, not its first word: a
first count took `cd images && curl -o ...` for a `cd` and reported half the
asks as reading. This is the before-number for the approved-plan execution
item in `deepseek_suggestions.md`.

**Answer (2026-11-14), for website sessions** - 49 sessions over six batches,
dialogs per session:

| Mode | Sessions | Median | Range |
|---|---|---|---|
| `--auto` | 37 | 0 | 0 to 3 |
| `--read-only-auto` | 3 | 28 | 23 to 48 |
| manual | 9 | 31 | 12 to 112 |

`--auto` asks almost nothing because almost everything a website needs is
inside the project. Manual and read-only-auto ask about the same things once
the reading is taken out: downloads (`cd images && curl -o ...`), Commons
searches with `curl`, edits, `mkdir`, `sleep`, and each sub-agent launch. The
112 was a session polling with `ls`, 100 of them. Three sessions is too few to
say read-only-auto's median is below manual's; what is established is that none
of its dialogs was for reading. Not yet run: the same comparison on analysis or
coding tasks, which is the eight-task run named above.

### 5. Which routed skill was loaded, and did the model read it?

The router injects a skill as a message and `skill-router.ts` can be checked in
a unit test, but a session's report cannot say which skill was injected - and
nothing says whether the `SKILL.md` was then read. The `changing-code` gain (11
to 14 of 16) was entirely where it was loaded, so this separates "not routed"
from "routed and ignored", which have different fixes.

*Needed:* a line in `analyze.py` per routed skill, and whether a `read` of that
`SKILL.md` follows in the same session. **Added 2026-11-14** ("Session facts").

**Answer.** The question as put has a wrong premise: a routed skill is not
something the model then has to read. The router puts up to two skills **in
full** into the conversation (`inlined`) and only names any beyond that
(`named`). Across 109 top sessions it inlined `elm-delegation` 41 times,
`changing-code` 19, `uncertainty-propagation` 2, `physics-documents` and
`data-fitting` once each; it named a skill without inlining it twice, and
neither was then read. `SKILL.md` was opened with `read` once in all of them.
So "routed" means "was in front of the model", and the two cases to tell apart
are *not routed* and *in front of the model and not followed*.

On the harder coding benchmark, all three arms together (48 runs):

| `changing-code` | Passed | Failed |
|---|---|---|
| in the conversation | 17 | 1 |
| not routed | 24 | 6 |

and on the four tasks that ever failed: 11 of 12 with it, 6 of 12 without. The
one failure with the skill in front of the model (`state-leak`, a nested list
still shared after a shallow copy) is the "followed in part" case. The six
without it are routing: the first pattern matched 6 of 16 run prompts and the
widened one 12 of 16 - `inventory` ("Add reservations to stockroom ...") and
`drag-range` still do not match, and passed anyway.

### 6. Did the session look at what it made?

`view` is how a session sees a figure or a page, and in several sessions it
described a plot it had not opened: a check that reads the file cannot catch
that, because the file was right.

*Needed:* a count of `view` calls against the files the session wrote. **Added
2026-11-14** ("Session facts").

**Answer, for the 50 website sessions,** every one of which was asked to
"check the visual renderings between each subpage":

| What the top session viewed | Sessions |
|---|---|
| at least one page | 30 |
| pictures only, no page | 2 |
| nothing at all | 18 |

**Twenty of fifty finished without looking at a single page they were asked to
compare.** That is the session's own `view` calls; a sub-agent may have looked
at the page it wrote, which is in its own session file and not counted here. It
is why the end-of-run check exists - it compares the pages itself when a reply
claims consistency over pages nobody viewed, and in batch 4 it sent four
sessions back - and it is the strongest reason to build the plotting set with a
"did it look" column: a session that describes a figure it never opened will
pass any check that only reads the file.

### 7. Does a session ever compact, and what does the report say when it does?

Nothing reads a `compaction` entry, so this cannot be answered from the reports
today - and it is the trigger for the whole long-session question. Over 212
session files from 2026-11-14 there were none, and the largest context was
122,595 against a 183.5k trigger.

*Needed:* a compaction count in `analyze.py`. **Added 2026-11-14** ("Session
facts": compactions, first and largest request).

**Answer: no, not once.** Over 319 session files from 2026-11-14 - 109 top
sessions and 210 sub-agents, including 30-minute ten-agent jobs and a sub-agent
that ran 140 turns - there is no compaction entry, and the largest request was
122,595 tokens against a 183,500 trigger. Five sessions passed 100k. So the
long-session questions (`keepRecentTokens`, a checkpoint ledger, drift at 150k)
are about a state these sessions do not reach; what they do reach is cost: a
context of 90 to 120k carried for 100 to 200 turns.

### 8. How much of a long turn is cache reuse?

The prefix cache is what makes a long session affordable, and two extensions are
built around not breaking it: `pinned-instructions.ts` reads the system prompt
only at a start or after a compaction, `skill-router.ts` appends a message
instead of changing a section. No report shows whether a change held.

*Needs:* per-turn usage (input, cache read, cache write) from the session file,
totalled in `analyze.py`. *Settles it:* the shares before and after any change
that touches the system prompt.

**Answer: it cannot be read from a session.** Every reply's usage has the
fields, and they are zero: `cacheRead` 0 and `cacheWrite` 0 across all 319
session files and 205 million input tokens, with `cost` zero too. ELM does not
report cache use to the client, so whether a prefix was reused is invisible
here, and a report line for it would print 0% forever. What can be measured
instead is what the cache would show up as. The one profile on record went
through a logging relay, not the session file
(`templates/extensions/pinned-instructions.ts`, its opening comment: pinning an
instruction mid-session left the next request sharing 54% of its start with any
earlier one). The same relay, or time to first token on the second request of a
session, is the test for any change that touches the system prompt.
Until that is run, "this does not break the cache" is an argument, not a
measurement.

**Since measured, from outside (2026-11-14, later the same day).** Five tests in
`harness/cache/` time what the gateway will not report; the results are in the
README's "ELM's prompt cache" section and `2026-11-14/elm-cache.json`. All three
models reuse a prefix and keep it for 7 to 15 minutes at least. In three
twelve-prompt sessions every one of 254 requests began with the whole of the one
before, with the tool list unchanged - so both extensions held, and nothing else
elm-pi adds breaks the prefix. And about one request in six comes back cold all
the same (47 of 254), which no change to elm-pi can fix: it looks like several
servers with a cache each. A change that touches the system prompt is now
checked by running test 5 again and reading "requests extending the last".

### 9. The six areas, which need a task set first

Reading plots and reading images have never been measured at all; uncertainty
coverage over twenty seeds is the most promising in modelling; plotting and
text extraction have a brief each. Build those as the brief says, and each
becomes a question of the same shape as 1-8.

**Answer: still open - no task set exists for any of the six.** Question 6
moves plotting and reading plots up the list: if 20 of 50 sessions do not look
at pages they were told to compare, "did it open the figure" is likely to be the
first finding there too.

And two that need a long-session task set: whether `compaction.keepRecentTokens` at 20000
or 60000 keeps more facts on a long session, and whether `presence_penalty 1.5`
drifts at 150k when it costs nothing at 90k. Question 7's answer applies: no
session here has compacted or reached 150k, so neither is urgent. Both are written up, with their
rules for shipping, in `deepseek_suggestions.md` items 34 and 43.

### What it cannot answer

Whether the install is pleasant to use; what the gateway does inside itself; and
whether an answer is *right* when the session says it is. The last is what the
checks are for: the driver and `summary.py` can tell you how a turn ended, not
whether what came out of it was true. A reply that says "verified" is a claim to
test.

## Order of work

1. **Baseline first.** Build the six task sets (six to eight tasks each is
   enough to start), validate every check, run each task twice on the current
   tree, and record the scores before changing anything. Expect some sets to
   score near 100%: that is a result - say so, make the set harder, and do not
   tune against a ceiling.
2. **Read the failures before fixing any.** Sort each into: the harness; the
   check; the model given everything it needed; the model not given something
   (a skill not routed, a tool result cut short, a preview that hid the
   answer). Only the last two are elm-pi's to fix, and the last is the cheapest.
3. **Fix one thing, measure again.** A skill that carries something to copy
   has so far beaten a skill that warns. Routing matters as much as content:
   the `changing-code` skill's gain was entirely where it was loaded.
4. **Record it**, as above, with what the measurement cannot show.

And through all of it, the bar this repository uses for any change: **which
recorded session failed without it?**
