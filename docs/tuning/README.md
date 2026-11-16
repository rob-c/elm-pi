# Model tuning: the evidence

Every model setting elm-pi ships was measured on ELM before it was chosen. This
folder keeps the measurements: what was run, when, with what settings, and every
result, so a setting can be checked or the run repeated. The research it
started from, with sources, is in [sources.md](sources.md).

- `2026-11-11/`, `2026-11-12/` - the results, one file per experiment, as the
  runs wrote them (scratch paths and the home folder replaced with `<scratch>`
  and `~`)
- `harness/` - the scripts that produced them; `tables.py` computes every table
  below from the results, and `tests/test_tuning_evidence.py` fails if a table
  here no longer matches its evidence
- [decisions.json](decisions.json) - the shipped settings, each with the
  experiment it came from; the same test checks the templates still ship them

All runs: pi 1.5.2 through the real `./pi` launcher (`pi --auto -p`), against the
ELM gateway with a staff key, models `Qwen/Qwen3.5-397B-A17B-FP8`,
`mistralai/Mistral-Small-4-119B-2603` and `meta-llama/Llama-3.3-70B-Instruct`
(through the shim). Two results from the user's own sessions are kept as scores
only: their content is private, and this repository is public.

## How tasks are scored

Each task runs in a fresh copy of a small Python project (`harness/ab.py`,
`FILES`) and is checked by a script written before any model ran it, against
the project's files and the reply. Every check was run first against the
untouched project (it must fail) and against a hand-written solution (it must
pass). Four task sets:

- the first 11 (`harness/ab.py`): find a function, count classes, rename by
  numbered steps, fix a bug, add a function, a data question, run the tests,
  summarise a file, write JSON, a cross-file question, docstrings on 12 functions;
- 6 written after the first results, to check nothing was tuned to the first 11
  (`harness/ab2.py`, `HELD_OUT`);
- 8 harder ones for the tuning runs (`harness/hard.py`): move a function to a new
  module, debug an off-by-one, write tests that must catch a planted bug, fit an
  exponential, add a command line, add an option with a test, find a
  divide-by-zero, run a pipeline;
- 25 harder still (`harness/hard2.py`, `HARD2`), written for the sampling sweep
  once Qwen passed 96% of the rest, so a setting has room to help or hurt:
  refactors across files (a class renamed in code, strings and JSON; functions
  moved to a new module; one shared constant where one module works in km/s),
  debugging with two causes in other modules or a symptom away from the cause,
  scientific code (a weighted fit with absolute uncertainties, error
  propagation in degrees, a stable log-sum-exp, histogram edges, a messy CSV, a
  log with two different micro signs), tests that must catch 6 or 7 planted
  mutants, edits held to exactly what was asked, honesty (a missing input file,
  a rule that makes the task impossible, a bug report that is false), questions
  about a 540-line module that grep answers wrongly, a git bisect past a commit
  named "Fix", and making a pair count fast without changing its answers.

The 33 checks of `hard.py` and `hard2.py` and the 6 of `HELD_OUT` are tested
themselves (`tests/test_tuning_tasks.py`, against `harness/solutions.py`): each
must fail the untouched project and pass a reference solution, pass 23 correct
answers written differently (`ALTERNATIVES`, so no check is stricter than its
prompt) and fail 61 plausible wrong ones (`NEAR_MISSES`); the answers the checks
hold are recomputed independently (exact fractions, 50-digit decimals, the git
history replayed commit by commit).

"Failed with no tool call" counts runs that failed having called no tool at
all - a reply that described work instead of doing it. Results with numpy: two
correct solutions imported numpy, which the checking interpreter lacked;
`harness/rescore.py` re-checked failed runs of the file-based tasks under one
that has it, and the files here are the re-checked ones (`pass_without_numpy`
keeps the first verdict).

## 2026-11-11: the first A/B, three models, defaults

Three runs of each of the first 11 tasks (`ab-rounds-1-3.json`). Mistral as
first added sent no sampling settings, so it ran at the gateway's 1.0.

<!-- table:first-ab -->
| Model | Passed | Median per task | Failed with no tool call |
|---|---|---|---|
| Qwen | 33/33 | 12.2 s | 0 |
| Mistral (as first added) | 20/33 | 6.3 s | 3 |
| Llama | 23/33 | 9.7 s | 3 |
<!-- /table:first-ab -->

## 2026-11-11: what the gateway does

The gateway's default temperature, read from the spread of answers
(`temperature-probe.json`): Mistral ships no sampling defaults, so vLLM uses 1.0.

<!-- table:temperature -->
| 12 answers, random number 1-100 | Distinct |
|---|---|
| Mistral, server default | 8 |
| Mistral, temperature 0.15 | 2 |
| Mistral, temperature 1.0 | 7 |
| Qwen, server default | 1 |
<!-- /table:temperature -->

Output length (`gateway-probes.json`): both accept `max_tokens` 81920 and refuse
1,000,000 (`max_model_len=262144`); each streamed past the old 32768 limit.

<!-- table:output-length -->
| | Qwen | Mistral |
|---|---|---|
| One streamed reply | 43,893 tokens, finish `stop` | 40,000 tokens, finish `length` |
| Time | 1966 s | 214 s |
<!-- /table:output-length -->

## 2026-11-11: Mistral, setting by setting

All 17 tasks, three runs each, the arms side by side on the same tasks at the
same moment (`guidance.json`, `temperature-0.15.json`,
`guard-reasoning-vibe.json`; the guidance texts are `harness/mistral-guidance.md`
and `harness/mistral-vibe.md`, the guard `harness/claim-guard.ts`).

<!-- table:mistral-settings -->
| Mistral, as set up | First 11 | Later 6 | All 17 | Failed with no tool call | Guard fired (then passed) | Median |
|---|---|---|---|---|---|---|
| As first added (temperature 1.0) | 25/33 | 8/18 | 33/51 | 3 | - | 7.7 s |
| 1.0 and written rules against false claims | 24/33 | 10/18 | 34/51 | 3 | - | 7.8 s |
| Temperature 0.15 | 29/33 | 9/18 | 38/51 | 3 | - | 6.0 s |
| 0.15 and the claim guard | 27/33 | 8/18 | 35/51 | 0 | 3 (3) | 7.6 s |
| 0.15, Vibe's rules and the claim guard | 28/33 | 10/18 | 38/51 | 0 | 3 (3) | 7.8 s |
| Reasoning on, 0.7, and the claim guard | 31/33 | 15/18 | 46/51 | 0 | 0 (0) | 9.5 s |
| Qwen, for reference | - | 18/18 | 18/18 | 0 | - | 15.4 s |
<!-- /table:mistral-settings -->

Shipped: reasoning on by default at 0.7, 0.15 when off, and the claim guard.

## 2026-11-11: compaction

pi's own `compact()` with each model, two runs each (`compaction.json`;
`harness/compact_test.mjs`). The generated session (`compaction-generated-session.jsonl`,
made by `harness/make_long.py`) has eight facts planted in it; the real one is a
74K-token research session of the user's, kept as scores.

<!-- table:compaction -->
| | Qwen | Mistral | Llama |
|---|---|---|---|
| Real session (of 11 facts) | 10, 11 | 9, 10 | 9, 10 |
| Generated session (of 8 facts) | 5, 6 | 5, 4 | 4, 3 |
| Time per summary | 44-63 s | 7-13 s | 16-24 s |
<!-- /table:compaction -->

Shipped: Mistral as the compaction fallback, reasoning off.

## 2026-11-11: prompt suggestions

pi-next-prompt's request, sent to both models for 12 real session endings
(`suggestions.json`; `harness/suggest_test.py`), judged blind - the verdicts
were written down before the labels were revealed.

<!-- table:suggestions -->
| | Qwen | Mistral | Tie |
|---|---|---|---|
| Better suggestion, judged blind | 4 | 3 | 4 |
| Request failed (HTTP 400) | 0 | 1 | |
| Median time | 0.78 s | 0.65 s | |
<!-- /table:suggestions -->

Not changed: suggestions come from the session's own model, which keeps the
gateway's prompt cache.

## 2026-11-11, evening: tuning all three models

Can a different setting do better than the shipped one? Three copies of one
install, the shipped settings in A and an alternative per model in B and C, run
side by side on every task three times (`tuning.json`, the arms in
`tuning-arms.json`, the run in `tuning-notes.json`; `harness/ab6.py` and
`harness/hard.py`). Qwen ran the 6 later and 8 hard tasks only - it passes the
first 11 every time; Mistral and Llama ran all 25.

<!-- table:tuning -->
| Arm | Settings | Passed | The 8 hard tasks | Failed with no tool call | Median | Input tokens per task |
|---|---|---|---|---|---|---|
| qwen-A | temperature 0.7, top_p 0.8, top_k 20, min_p 0, presence_penalty 1.5 (shipped: the card's instruct profile) | 41/42 | 23/24 | 0 | 20.1 s | 91K |
| qwen-B | temperature 0.7, top_p 0.8, top_k 20, min_p 0, presence_penalty 0 | 39/42 | 21/24 | 0 | 19.9 s | 75K |
| qwen-C | temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence_penalty 0 (the card's thinking profile) | 40/42 | 22/24 | 0 | 19.4 s | 83K |
| mistral-A | reasoning high, temperature 0.7 (shipped: Mistral's figure) | 72/75 | 24/24 | 0 | 14.5 s | 75K |
| mistral-B | reasoning high, temperature 0.4 | 69/75 | 22/24 | 0 | 13.4 s | 74K |
| mistral-C | reasoning high, temperature 0.15 | 73/75 | 24/24 | 0 | 13.0 s | 76K |
| llama-A | pi sends 0.6 / top_p 0.9 (shipped); the shim sends 0 with tools | 41/75 | 12/24 | 3 | 23.0 s | 81K |
| llama-B | pi sends 0.2 / top_p 0.9; the shim sends 0 with tools | 35/75 | 7/24 | 8 | 24.3 s | 68K |
| llama-C | pi sends 0 / top_p 0.9; the shim sends 0 with tools | 36/75 | 8/24 | 5 | 22.6 s | 81K |
<!-- /table:tuning -->

- **Qwen:** the shipped instruct profile did best (41 of 42). Its presence
  penalty of 1.5, which Qwen's card says may cost "a slight decrease in model
  performance", cost nothing here: without it, 39. Kept.
- **Mistral, reasoning on:** 0.7 and 0.15 tie (72 and 73 of 75), 0.4 is a little
  lower; 0.7 is Mistral's own figure and is kept. With reasoning on it passed all
  24 hard-task runs and 72 of 75 in all, as Qwen did, at 14.5 s a task against
  Qwen's 20.1 s.
- **Llama:** the three arms are one setting three times over - the shim sends
  every tool request at temperature 0 (measured 6/6 against about half at the
  default, in `shim/shim.py`), so pi's Llama temperature never reaches the
  gateway in an agent task. Their spread, 35 to 41 of 75, is how far one setting
  moves between identical runs at this size, and so the margin any difference
  above has to beat. About half the tasks, the lowest of the three.

No setting changed: every shipped one measured best or level.

## 2026-11-11: fields pi or a package may add

`gateway-fields.json` (`harness/tier.py`): one request per model with each of
`service_tier: "priority"` (pi-subagents' fast mode), `prompt_cache_key` with
`prompt_cache_retention` (pi, with `PI_CACHE_RETENTION=long`) and `store: false`
(pi, always). All 12 were accepted. The models' `compat` keeps the cache fields
out all the same, so every request is the one the settings were measured with.

## 2026-11-11, night: temperature, swept

Each model at three or four temperatures with everything else held at the
shipped values (`sweep.json`, the arms in `sweep-arms.json`, the run in
`sweep-notes.json`): Qwen with thinking off, Mistral with reasoning off (its
temperature with reasoning on is in the table above), and Llama at the
temperature its tool requests actually reach ELM at - the shim's
`SHIM_TEMPERATURE`, each arm with its own shim. All 25 tasks, three runs each.

<!-- table:sweep -->
| Model | Temperature | Passed | The 8 hard tasks | Failed with no tool call | Median | Input tokens per task |
|---|---|---|---|---|---|---|
| Llama, through the shim | 0.0 (shipped) | 33/75 | 4/24 | 4 | 21.5 s | 68K |
| Llama, through the shim | 0.3 | 41/75 | 9/24 | 3 | 25.5 s | 83K |
| Llama, through the shim | 0.6 | 37/75 | 7/24 | 4 | 22.4 s | 81K |
| Mistral, reasoning off | 0.0 | 60/75 | 20/24 | 0 | 17.0 s | 74K |
| Mistral, reasoning off | 0.15 (shipped) | 62/75 | 21/24 | 0 | 16.2 s | 72K |
| Mistral, reasoning off | 0.4 | 59/75 | 20/24 | 0 | 16.6 s | 78K |
| Mistral, reasoning off | 0.7 | 60/75 | 19/24 | 0 | 17.0 s | 75K |
| Qwen, thinking off | 0.2 | 72/75 | 21/24 | 0 | 18.5 s | 72K |
| Qwen, thinking off | 0.4 | 72/75 | 21/24 | 0 | 18.7 s | 72K |
| Qwen, thinking off | 0.7 (shipped) | 72/75 | 21/24 | 0 | 18.3 s | 56K |
| Qwen, thinking off | 1.0 | 69/75 | 20/24 | 0 | 18.4 s | 56K |
<!-- /table:sweep -->

- **Qwen:** 0.2, 0.4 and 0.7 level at 72 of 75; 1.0 a little lower. 0.7 stays.
- **Mistral, reasoning off:** level across 0 to 0.7 (59-62 of 75). Its
  temperature is not what matters; reasoning is (72-73 of 75 with it on), and
  reasoning is on by default.
- **Llama:** 0.3 did best here, in every round. But temperature 0 has now been
  run four times on these tasks - 41, 35, 36 and 33 of 75 - and 0.3's 41 is no
  better than the best of those. Not a difference this many runs can show, so
  the shim's 0 stays.

The run was stopped once, and its first Llama runs set aside, for a bug it found
in the shim (`llama-shim-bug.json`): requests failed through a proxy that had
gone, and a shim bootstrap.sh had left running sent Llama traffic straight to
ELM. Both are fixed, and the Llama arms ran again in full on the fix.

No setting changed.

## 2026-11-12: top_p, top_k, min_p and the presence penalty

Temperature was settled; this tests the rest of the sampling settings, the ones
[sources.md](sources.md) ("Sampling beyond temperature") found worth trying and
no published study had tested on agent work. On a harder suite: the 25 tasks of
`hard2.py` added to the 25 before, 50 in all, three rounds (`harness/ab6.py`
with `AB_SUITE=50`). Three things are new in how it was run and read:

- **A repeat of the control.** Each model's shipped settings ran twice side by
  side ("the same again"). How far two identical arms drift apart is the noise
  a real difference has to beat.
- **Pair by pair.** An arm is compared with its control on the same task in the
  same round, run at the same moment: "pairs better" are the ones the arm passed
  and the control failed, "worse" the reverse, and p is the exact McNemar test on
  those (`harness/paired.py`).
- **Gateway errors left out.** ELM rate-limits Qwen (HTTP 429) once about four
  Qwen sessions are in flight; pi retries, but 21 of batch 1's 1,800 runs and 12
  of batch 2's 600 ended on an error all the same. A task and round with such a
  run in it is left out of the comparisons, hence 133 or 142 pairs and not 150;
  "Passed" counts every run.

Batch 1, all three models (`sampling-batch1.json`, the arms in
`sampling-batch1-arms.json`, the run in `sampling-batch1-notes.json`):

<!-- table:sampling-1 -->
| Model | Settings | Passed | The 25 hardest | Against the control, pair by pair | p | Failed with no tool call | Median | Input tokens per task |
|---|---|---|---|---|---|---|---|---|
| Llama, through the shim | SHIM_TEMPERATURE 0 (shipped) | 45/150 | 10/75 | - | - | 8 | 35.8 s | 86K |
| Llama, through the shim | the same again | 53/150 | 10/75 | +4.5 points (11 pairs better, 5 worse, of 133) | 0.21 | 7 | 34.5 s | 82K |
| Llama, through the shim | **SHIM_TEMPERATURE 0.3** | 43/150 | 8/75 | -0.8 points (12 pairs better, 13 worse, of 133) | 1.00 | 7 | 36.5 s | 93K |
| Llama, through the shim | **SHIM_TEMPERATURE 0.6** | 49/150 | 11/75 | +2.3 points (13 pairs better, 10 worse, of 133) | 0.68 | 8 | 34.4 s | 94K |
| Mistral, reasoning high | temperature 0.7 (shipped) | 112/150 | 46/75 | - | - | 0 | 25.4 s | 128K |
| Mistral, reasoning high | the same again | 115/150 | 44/75 | +6.0 points (16 pairs better, 8 worse, of 133) | 0.15 | 0 | 26.4 s | 131K |
| Mistral, reasoning high | **top_p 0.8** | 120/150 | 48/75 | +9.0 points (21 pairs better, 9 worse, of 133) | 0.04 | 0 | 28.6 s | 136K |
| Mistral, reasoning high | **top_p 0.95** | 118/150 | 46/75 | +6.8 points (20 pairs better, 11 worse, of 133) | 0.15 | 0 | 26.9 s | 129K |
| Qwen, thinking off | temperature 0.7, top_p 0.8, top_k 20, min_p 0, presence_penalty 1.5 (shipped) | 137/150 | 65/75 | - | - | 0 | 35.0 s | 92K |
| Qwen, thinking off | the same again | 134/150 | 61/75 | -0.8 points (4 pairs better, 5 worse, of 133) | 1.00 | 1 | 37.9 s | 91K |
| Qwen, thinking off | **presence_penalty 0** | 137/150 | 64/75 | +1.5 points (5 pairs better, 3 worse, of 133) | 0.73 | 1 | 34.5 s | 93K |
| Qwen, thinking off | **top_p 0.95** | 133/150 | 60/75 | -0.8 points (4 pairs better, 5 worse, of 133) | 1.00 | 1 | 33.6 s | 91K |
<!-- /table:sampling-1 -->

Batch 2, Qwen only, run alongside batch 1 (`sampling-batch2.json`,
`sampling-batch2-arms.json`, `sampling-batch2-notes.json`):

<!-- table:sampling-2 -->
| Model | Settings | Passed | The 25 hardest | Against the control, pair by pair | p | Failed with no tool call | Median | Input tokens per task |
|---|---|---|---|---|---|---|---|---|
| Qwen, thinking off | temperature 0.7, top_p 0.8, top_k 20, min_p 0, presence_penalty 1.5 (shipped) | 134/150 | 63/75 | - | - | 1 | 33.1 s | 91K |
| Qwen, thinking off | **min_p 0.05** | 137/150 | 65/75 | +1.4 points (4 pairs better, 2 worse, of 142) | 0.69 | 1 | 37.2 s | 92K |
| Qwen, thinking off | **presence_penalty 0.5** | 132/150 | 61/75 | -0.7 points (3 pairs better, 4 worse, of 142) | 1.00 | 3 | 36.4 s | 91K |
| Qwen, thinking off | **top_k 40** | 133/150 | 61/75 | -0.7 points (2 pairs better, 3 worse, of 142) | 1.00 | 2 | 38.4 s | 91K |
<!-- /table:sampling-2 -->

- **Qwen:** nothing beats the shipped instruct profile. top_p 0.95, top_k 40,
  min_p 0.05 and a presence penalty of 0 or 0.5 all land within 1.5 points of
  it, and its own repeat 0.8 points off. The penalty of 1.5 again cost nothing
  (at 0: +1.5 points, p 0.73). The new tasks left room to fail - 60 to 65 of 75
  runs of the 25 hardest passed - and still nothing moved. Kept.
- **Llama:** the shim's temperature 0 against 0.3 and 0.6: -0.8 and +2.3
  points, inside the +4.5 its own repeat drifted. The shim's 0 stays.
- **Mistral, reasoning high:** top_p 0.8 was 9.0 points ahead of its control
  (21 pairs better, 9 worse, p 0.04), the one comparison below 0.05. But that
  control was itself 6.0 points behind its repeat, and against the repeat top_p
  0.8 is +3.0 (p 0.50). Against both controls together it is +6.0 points, 95%
  interval -0.4 to +12.8 from resampling whole tasks (`paired.task_bootstrap`);
  and six comparisons at once make one p below 0.05 likely by chance (Holm,
  `paired.holm`: 0.26). Not shown, but plausible enough to test on its own:
  next section.

No setting changed.

## 2026-11-12: Mistral at top_p 0.8, tested on its own

The plan was written down, with the rule for the decision, before the run
started (`mistral-top-p-confirmation-plan.json`): three arms at the shipped
settings and three at top_p 0.8, all six on every task at the same moment,
three rounds of the 50 tasks; replicate i of one paired with replicate i of the
other (`paired.fold_replicates`), 450 pairs, enough to find 6 points four times
in five. top_p 0.8 ships only if, in this run alone, it is ahead with p below
0.05 and the whole-task interval lies above zero. Batch 1 is not added in.

The run (`mistral-top-p-confirmation.json`, `mistral-top-p-confirmation-notes.json`),
read by that rule (`paired.confirm`):

<!-- table:mistral-top-p -->
| Mistral, reasoning high | Passed | The 25 hardest | Median | Input tokens per task |
|---|---|---|---|---|
| temperature 0.7 (shipped) | 339/450 | 133/225 | 23.0 s | 130K |
| temperature 0.7, **top_p 0.8** | 343/450 | 137/225 | 23.6 s | 133K |

| Pair by pair | top_p 0.8 against the shipped setting |
|---|---|
| Pairs (gateway errors left out) | 443 |
| Better, worse | 57, 51 |
| Difference | +1.4 points |
| Exact McNemar p | 0.631 |
| 95% interval, resampling whole tasks | -2.7 to +5.1 points |
| By the rule written beforehand | does not ship |
<!-- /table:mistral-top-p -->

top_p 0.8 does not ship: +1.4 points, p 0.63, and the interval, -2.7 to +5.1,
leaves no room for the 9 points batch 1 suggested. That was its control having
a bad run - which the repeat of the control had already hinted at. The three
identical shipped arms here passed 109, 113 and 117 of 150 between them, a
spread of 8 runs from no change at all; the three top_p 0.8 arms, 113 to 115,
fall inside it.

No setting changed.

## 2026-11-12: images, Qwen against Mistral

Which model to give image description and visual consistency work. Pages,
requests and scoring: `harness/vision_pages.py`, `harness/vision_eval.py` and
`harness/vision_score.py`; every reply in `2026-11-12/vision-results.json`, the
scores in `2026-11-12/vision-summary.json`, test5's pages the comparisons use in
`2026-11-12/vision-pages/`. Five images with known answers and four "list every
difference" pairs, one with no difference at all, sent through ELM as pi sends
them, five times each, to Qwen (thinking off) and Mistral (thinking high, and
off).

All three read charts, a table and a page about equally well (99 to 104 of 105
answers). Comparing is where they part. Qwen found 96% of the planted changes and
reported 0.4 that were not there per comparison. Mistral with thinking high found
84% and invented 1.1. With thinking off it found 65% and invented 8.2, and 12.8
when shown the same page twice. The table is in INSTALL.md, "Images: Qwen against
Mistral". The result: images go to `qwen` (AGENTS.md).

## 2026-11-12: how long ELM goes silent

What `httpIdleTimeoutMs` should be: pi ends a request that sends nothing for
that long and retries it, 300s by default. In test6 a sub-agent's reply stopped
after four tokens and the agent sat for eight minutes. `harness/stall_latency.py`
reads the pi sessions already on disk - the tuning runs of 2026-11-11 and 12,
the interactive tests and other ELM sessions, 45,110 requests once a fork's copy
of its parent is dropped - and times each request from its start to its end.
A reply of at most 100 tokens spends that time almost all waiting for its first
token. Counts and durations only: `2026-11-12/stall-summary.json`.

| Model | short replies | median | 99% | 99.9% | longest |
|---|---|---|---|---|---|
| Qwen | 7,452 | 1.4s | 18.3s | 44.1s | 58.4s |
| Llama | 7,213 | 1.8s | 12.5s | 44.2s | 58.2s |
| Mistral | 13,128 | 1.5s | 4.0s | 33.2s | 56.1s |

None waited past 60s, through 429 storms included. Two requests did stall, both
Qwen, and ran 477.6s and 1126.6s before pi's 300s timer ended them. The result:
`httpIdleTimeoutMs` 120000 in `templates/settings.json`, twice the longest
healthy wait (`decisions.json`).

## 2026-11-14: a coding benchmark, and the `changing-code` skill

The tasks above measure tool use and short edits. Whether a *fix is right* was
not measured anywhere, so eight harder tasks were written for it
(`harness/coding/make_tasks.py`): a feature across three modules, state leaking
through a shared default, a slow function to speed up without changing what it
returns, a numerics trap, a thread race, a parser from a written spec, a SQL
join that double-counts, and a projectile with drag to 0.1%. Each is scored by a
check the session never sees, and each check was first shown to fail on the
starting project and pass on a reference solution - which caught one wrong
reference of the author's own. Each task was run twice per arm
(`2026-11-14/coding-benchmark.json`).

| Arm | Passed | Tokens |
|---|---|---|
| no skill | 11 of 16 | 2.79M |
| `changing-code`, routed for 3 of the 8 task wordings | 14 of 16 | 2.97M |
| `changing-code`, routed for all 8 | 16 of 16 | 3.68M |
| the same, under `pi --fast` | 14 of 16 | 1.74M |

Without the skill every failure was a change that made the reported example work
and went no further: a copy that still shared the list nested in it, a count
right for the group in the report and wrong for the next, a parser that took a
time no clock shows. The skill says to try to break the fix with cases the
report did not give. The gain followed its reach: in the middle arm it came
where the skill was loaded and nowhere else.

The last row is the install's narrow configuration: `--fast` loads the policy and nine local
extensions and none of the tool packages, so each request starts at about 10k tokens where the full
install's starts at 19k. It cost half the tokens and two passes, on the two tasks that fail in
other arms too. Two identical rounds of this set differ by up to one pass with one or two tasks
flipping, so two passes is not a finding; half the tokens is.

What this is not: a large sample. Two runs a task is enough to see 11 against
16 and not enough to rank two prompts a point apart, and at 16 of 16 this set
can show no further gain - the next change needs harder tasks. Two checks were
corrected after reading failures (an assertion the prompt did not justify, and a
time the spec could fairly reject); all three arms were rescored with the
corrected checks. The skill costs about a third more tokens on these tasks,
which is the extra cases being run.

## ELM's prompt cache (2026-11-14)

ELM reuses the start of a prompt it has just read, and says nothing about it: no cached-token
field in `usage`, and `cacheRead` 0 in every session file. So it is timed from outside, by five
tests (`harness/cache/`; `tests/test_cache_probe.py` holds each to telling a gateway that reuses
a prefix from one that does not). "Cold" and "warm" are seconds to the first token for a prompt
of about 23k tokens, new or just sent.

| Model | Cold | Warm | 1 repeat | 2 grow | 3 lifetime | 4 shared | 5 requests extending the last | 5 of those, warm |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 | 2.3 s | 0.3 s | 7 of 8 | 6 of 7 | 15 min | 3 of 4 | 54 of 54 | 39 of 54 |
| Mistral Small 4 | 1.9 s | 0.8 s | 7 of 8 | 6 of 7 | 15 min | 4 of 4 | 150 of 150 | 125 of 150 |
| Llama 3.3 | 6.7 s | 0.4 s | 7 of 8 | 6 of 7 | 7 min | 4 of 4 | 50 of 50 | 43 of 50 |

What that says:

- **All three models reuse a prefix**, and keep it at least 15 minutes (Qwen, Mistral; the longest
  gap tried) or 7 (Llama, whose 15-minute ask was cold, as was its 1-minute one).
- **pi's requests can all be served from it.** In three twelve-prompt sessions - 55, 151 and 51
  requests, up to 350 kB - every request began with the whole of the one before, and the tool
  list never changed. Nothing elm-pi adds (routed skills, guard notes, attached pictures)
  rewrites what was already sent.
- **About one request in six is cold anyway.** One repeat in eight was cold on every model in
  test 1, and in the sessions 15 of 54 (Qwen), 25 of 150 (Mistral) and 7 of 50 (Llama) requests
  that extended the last one took a cold request's time: 43 s, 10 s and 38 s of waiting over a
  session. A cold repeat followed by warm ones is what several servers, each with its own cache,
  look like from outside; that is an inference, and one for the ELM team to confirm. The session
  figures use the 23k-token cold time as the bar while the requests grew to three times that, so
  Mistral's, whose warm and cold are closest, is the least certain.
- **Sub-agents share their parent's prefix**: a new conversation that starts with the same text
  starts warm (11 of 12 across the models).
- **The control never passes**: with its first line changed each turn, 0 of 21 turns were warm.

The raw times are in `2026-11-14/elm-cache.json`. To run it again:
`python3 -I harness/cache/cache_probe.py ENVFILE out.json`, and for test 5 a batch with
`TREADMILL_EXTENSION=harness/cache/cache_log.ts`, then `cache_probe.py sprint`.

## 2026-11-14: a ten-problem batch, and what a request costs before any work

Two driven sessions of the same ten stock coding problems (HumanEval-flavoured:
`has_close_elements`, `separate_paren_groups`, `truncate_number`, `below_zero`,
`mean_absolute_deviation`, `intersperse`, `parse_nested_parens`,
`filter_by_substring`, `rolling_max`, `is_simple_power`), sent as ten prompts in
order in one session, so that the tenth problem is answered by a session that
has already done nine. Each problem asked for one file under `solutions/`, with
its examples and edge cases in the prompt; the check imports all ten and runs
the cases the prompt justifies, and was proved on the seed (0/10) and on a
reference solution (10/10) before any session ran.

<!-- table:c10 -->
| Run | Problems | Wall | Input | Output | Requests | Tool errors | Dialogs | Sub-agents |
|---|---|---|---|---|---|---|---|---|
| c10.1 | 10/10 | 5 min 54 s | 678,217 | 4,125 | 30 | 0 | 0 | 0 |
| c10.2 | 10/10 | 5 min 27 s | 668,983 | 3,514 | 30 | 0 | 0 | 0 |
<!-- /table:c10 -->

Both sessions wrote exactly ten files, ran exactly one `python3 -c` check per
file, and left nothing else: no scaffolding, no test file kept, no sub-agent,
no dialog, no refusal. The only thing wrong with either is the cost.

Every request in those 30 begins at 19,152 tokens before a word of the work is
in it: the system prompt (`AGENTS.md`, `APPEND_SYSTEM.md`, pi's own), the skill
list, and the definitions of every tool. The session facts line in `report.md`
prints it. What it is made of, measured one flag at a time on the same empty
project (`2026-11-14/prompt-floor.json`; one prompt, "Say OK.", first request's
input tokens):

<!-- table:prompt-floor -->
| Flags | First request | Difference | What the difference is |
|---|---|---|---|
| as shipped | 18,169 | - | - |
| `--fast` | 9,359 | -8,810 | no npm-package tools at all: sub-agents, workflows, notebooks |
| `--tools read,bash` | 8,723 | -9,446 | every tool definition but two |
| `--exclude-tools subagent,workflow,workflow_control` | 15,501 | -2,668 | three tool definitions |
| `--exclude-tools 'notebook_*'` | 16,384 | -1,785 | the notebook tools |
| `--exclude-tools view,todo,pin_instruction,unpin_instruction,ask_user_question,bg_wait,contact_supervisor,tool_search` | 17,120 | -1,049 | elm-pi's own eight |
<!-- /table:prompt-floor -->

So 81% of what those two sessions spent was the floor, and 52% of the floor is
tool definitions for tools the work did not use: at 9,446 tokens a request,
1.35M tokens became about 283k that bought nothing. `--fast` halves the floor
and is the right flag for a session of small one-file tasks; it is documented in
`INSTALL.md` as the one-shot path and now has a number.

**The one defect the batch found, and the fix.** Both project folders got a
`solutions/__pycache__`: the session's Python wrote bytecode into the user's
project, which is litter nobody asked for and nothing removes. `./pi` now
exports `PYTHONDONTWRITEBYTECODE=1` beside the other environment it sets, the
way `score.py` already does for its own imports; `PYTHONDONTWRITEBYTECODE=0`
turns it back off. `tests/test_project.py` holds it. The batch was run again on
the fix: 20/20 again, and no `__pycache__` in either project folder.

**What this is not.** Two sessions, ten problems each, one model, one day: it
says nothing about problems that need more than one file, about reading code
that already exists, or about work long enough to compact. The problems were
written with their edge cases in the prompt, so a pass here means the session
implemented what it was told - not that it found the edge cases itself. The
floor probe is one prompt per flag in one project folder; the four rows add up
to a little more than the whole (tool definitions overlap in the prompt's own
text), so read them as the size of each group, not as an exact decomposition.

## 2026-11-14, evening: ten sessions of twenty problems, and the one defect that passed

Ten sessions, twenty stock coding problems each - the ten above plus
`count_distinct_characters`, `count_vowels`, `remove_vowels`, `longest_word`,
`sum_positive`, `is_sorted`, `rotate_left`, `unique_in_order`, `count_words`,
`median` - with the prompts rotated by two in each session, so every problem
sits in every position once across the ten. One file per problem; the check
imports all twenty and was proved on the seed (0/20) and on a reference
solution (20/20) before any session ran. Driven at `jobs 3`.

<!-- table:c20 -->
| Run | Problems | Wall | Input | Requests | Commands run |
|---|---|---|---|---|---|
| c20.1 | 20/20 | 10 min 21 s | 1,513,324 | 62 | 21 |
| c20.2 | 20/20 | 10 min 56 s | 1,586,851 | 62 | 21 |
| c20.3 | 20/20 | 11 min 44 s | 1,627,892 | 62 | 21 |
| c20.4 | 20/20 | 12 min 12 s | 1,664,079 | 62 | 21 |
| c20.5 | 20/20 | 9 min 59 s | 1,430,669 | 60 | 20 |
| c20.6 | 20/20 | 10 min 6 s | 957,850 | 41 | 0 |
| c20.7 | 20/20 | 9 min 24 s | 925,462 | 40 | 0 |
| c20.8 | 20/20 | 11 min 50 s | 1,429,514 | 60 | 20 |
| c20.9 | 20/20 | 15 min 41 s | 1,778,439 | 63 | 22 |
| c20.10 | 20/20 | 10 min 48 s | 1,529,170 | 62 | 21 |
<!-- /table:c20 -->

200 of 200 solved, 14,443,050 input tokens, ten sessions that all ended `stop`,
no dialogs, no children, 751k-1.78M a session on a 19,084-token floor. The
**Commands run** column is the only one that separates them: **c20.6 and c20.7
wrote twenty files and executed nothing.** Forty and forty-one requests where
the other eight needed 60-63, and 0.93M and 0.96M tokens against 1.43M-1.78M.
Both replied "Done." twenty times, both passed the check, and no guard fired -
`claim-guard` fires on a run with no tool call, and these runs wrote files.

That is the defect worth fixing, because a result cannot show it: the code was
right. On a task the model is less sure of, the same habit is work reported and
never run. So `templates/extensions/verify-guard.ts` now sends a turn back once
when it wrote a code file (by extension) and ran nothing in that turn - `bash`,
a python tool, a notebook run or a sub-agent launch all count, failed or not,
because a command that failed is a run that tried. Twice per session at most.
`tests/test_ext_verify_guard.py` holds the six cases and the cap.

Two smaller things the same ten sessions show, neither fixed:

- **eight of ten** spent one request and one visible tool error on a `read` of
  the file they were about to create (`[E_NOT_FOUND]`), then never did it again
  - 19k tokens each. A prompt line would fix it and `AGENTS.md` has no room;
  the failed call is the cheaper teacher.
- **three sessions** prefixed every command with `cd /Users/...` (20-22 times a
  session) although the bash tool already runs in the project: ~60 characters a
  call, and a sign the model was not sure where it was.

**The set is at its ceiling.** 200/200 here and 40/40 on the ten-problem
version: it can no longer show a difference of one or two problems, so the next
measurement needs harder tasks, not more sessions.

`2026-11-14/prompt-floor.json` holds both batches, every per-session figure and
these findings.

## 2026-11-15: Python launcher and session stability

Five isolated local installs and seventeen real Qwen sessions exercised the
Python port, the Bash reference, parallel children, Unicode text and tools.
The [file-by-file report](2026-11-15/python-port.md) records the fixes, validation
and remaining model failures; the [results](2026-11-15/python-port.json),
[source patch](2026-11-15/python-port.patch) and
[independent scorer](2026-11-15/python_port_score.py) preserve the evidence.

Validation used a frozen source snapshot, separately from concurrent network
and jail changes. The results distinguish working artifacts from a successful
whole session, retain the clock-jump timeout and the failed parser repeat, and
do not claim a general accuracy or speed gain over the Bash baseline.
