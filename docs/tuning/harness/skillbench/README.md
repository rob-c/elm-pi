# SkillsBench for elm-pi's own skills

[SkillsBench](https://github.com/benchflow-ai/skillsbench) (arXiv 2602.12670)
measures a skill the only way that means anything: the same task run with the
skill and without it, each run scored by a deterministic check the agent never
sees. This folder applies that to the skills in `templates/skills` - not to the
K-Dense library - with elm-pi itself as the agent.

Two parts:

| Part | Tool | What it answers |
|---|---|---|
| Static | BenchFlow's `bench skills validate` (NVIDIA SkillEvaluator and SkillSpector, no model) | Is each SKILL.md well formed, and does a scanner see anything unsafe in it |
| Paired | `bench.py` here, driving real elm-pi sessions with `../treadmill/drive.mjs` | Does a session given the skill solve a task that a session without it gets wrong |

## Why the paired runs do not use BenchFlow's runner

`bench run -a pi` runs plain pi in a container. elm-pi's skills reach a session
through its skill router, and fifty-six of them are hidden from pi's own listing,
so plain pi would never be given them; and it would have none of elm-pi's
launcher, guards or prompt. What is being asked is whether elm-pi, as a user
gets it, does better for its skills. So the task package, the oracle and
verifier rules, the two arms and the audit of whether a skill was used are
SkillsBench's, and the agent is `pi` from an install built from this tree.

## Static

```bash
T=~/sandbox/skillbench-tools            # nothing goes into ~/.local
export UV_TOOL_DIR=$T/tools UV_TOOL_BIN_DIR=$T/bin UV_PYTHON_INSTALL_DIR=$T/python UV_CACHE_DIR=$T/cache PATH=$T/bin:$PATH
uv tool install --python 3.12 benchflow
uv tool install --python 3.13 "skillevaluator[all] @ git+https://github.com/NVIDIA/SkillEvaluator.git@v0.5.0"
uv tool install "skillspector @ git+https://github.com/NVIDIA/SkillSpector.git@v2.12.0"
bench skills validate templates/skills --fail-on never --json > validate.json
```

## A task

One folder per skill, named for it, laid out as a SkillsBench task package:

```
tasks/<skill>/
  task.md                     frontmatter, then the prompt exactly as a user would type it
  environment/                what the session finds in its project folder
  oracle/make_environment.py  writes environment/ (fixed seed); the truth is here and in the verifier only
  oracle/solve.py             the reference solution: run in the project folder, computes the answer
  oracle/naive.py             the plausible careless solution the task is built to catch
  verifier/test_outputs.py    the hidden check: pytest, run in the project folder; all pass = reward 1
```

`task.md` frontmatter: `skill` (the skill the task is for), `also` (other
skills expected to be routed, comma separated, optional), `category`,
`pitfall` (what a solution without the skill tends to get wrong, one line),
`timeout_sec`.

The rules, SkillsBench's and three of ours:

1. **A real request.** One to four sentences a physicist would type to a
   colleague: the files, what is wanted, and where to put it - `result.json`
   with named keys and units. No method, no warning about the pitfall, no
   skill named. (`bench.py validate` refuses a prompt that names its skill.)
2. **Self-contained and offline.** Everything needed is in `environment/`:
   the data, and every constant or nuclear datum as a notebook or certificate
   would give it. Nothing to look up, nothing to recall. The session has
   numpy, scipy, pandas, matplotlib, iminuit, sympy, uproot, awkward, h5py,
   pyarrow and pytest, a C++ compiler, and no network.
3. **The oracle computes.** `solve.py` derives the answer from the
   environment files by the right method; it hardcodes nothing it could read.
4. **Outcome-based, deterministic verifier.** Three to eight test functions
   on what the session left on disk. Tolerances come from the statistics: wide
   enough that any correct method passes (try two), narrow enough that the
   naive one fails. No network, no randomness, no judgement of prose.
5. **Ours: the task turns on something the skill says.** Read the skill
   first. The task contains at least one pitfall that the skill explicitly
   warns of, and `naive.py` is the solution that falls into it. It is not a
   trick: a careful expert who has never seen the skill passes.
6. **Ours: the truth does not leak.** Nothing in `environment/` gives the
   answer or the method, and the install a session can read does not contain
   `tasks/` at all.
7. **Ours: small.** `environment/` under 300 kB; ten minutes for an expert.

`bench.py validate` holds each task to what can be checked mechanically: the
oracle scores 1, the untouched environment scores 0, and the naive solution
scores 0.

## Running it

```bash
export ELM_PI_ENV_FILE=/path/to/.env                # the ELM key: copied mode 600, never printed
B=docs/tuning/harness/skillbench/bench.py
python3 $B build 1117                               # ~/sandbox/elm-pi-sb1117, a full bootstrap, no K-Dense
python3 $B validate --python ~/sandbox/elm-pi-sb1117/agent/python/env/bin/python
python3 $B run 1117 with-skill --jobs 4             # one arm at a time: they share the install
python3 $B run 1117 no-skill --jobs 4
python3 $B report 1117
python3 $B run 1117 with-skill --round 2 --only gamma-spectroscopy,hep-jets    # more trials of some
```

A finished run is never repeated: its `result.json` is read back, so an
interrupted arm is continued by running the same command again.

## Reading the report

For each task: passes over runs in each arm, and how many with-skill runs
actually had the task's skill put in front of the model. SkillsBench's own
warning applies: an installed skill is not a used one, and a skill that never
reached the session cannot have changed its score. Four cases:

- **helped**: fails without, passes with. What a skill is for.
- **both pass**: the model does this without the skill. Either the task is
  too easy to show anything, or the skill is not needed for it.
- **both fail**: the skill did not get the session there. Read the with-skill
  transcript: the skill was not routed, was routed and not followed, or does
  not say what was needed.
- **hurt**: passes without, fails with. Read both transcripts before anything
  else.

One run a side says which case a task is probably in and no more; the
treadmill's rule holds here too - two runs do not rank two things a point
apart. Rerun the tasks that matter with `--round`.
