# Working defaults

## Delegate to sub-agents by default

Sub-agents are the default tool for **breadth**, and running several at once is
normal here rather than an escalation. Reach for them when a task has independent
parts that each need real work:

- Searching or exploring code you have not read yet, in more than one place
- Reading or summarising several files, modules, or documents
- Running tests, linters or builds while other work continues
- Applying a substantial change that splits cleanly across separate files

Do **not** delegate work that is smaller than the round trip. A handful of one-line
edits you could make in a single read-and-edit pass is faster done directly -
measured on this setup, forcing delegation on trivial edits was more than ten times
slower and often failed to finish. The test is the size of the sub-task, not the
number of files.

Launch them with `subagent` (which is `async: true` by default, so each call returns
immediately) and collect with `bg_wait({all: true})`. `subagent` takes exactly one
child per call, so fan out by making several calls in the same turn.

pi's configured fan-out budget is **64 children**, and 20 concurrent has been
verified working here. Match the count to how the work actually divides - one
sub-agent per file or per independent question - rather than to a fixed number.
Measured on this setup: 6 agents ~110s, 12 ~269s, 20 ~264s, so wide fan-out is close
to free once you are past the fixed startup cost. Narrow fan-out on trivial work is
still slower than doing it directly.

When a fan-out is wide, results can be truncated with "previews omitted by budget" -
tell each sub-agent to report tersely, or raise `maxOutput` on the calls.

**Delegate** (these have narrow, well-defined scope):
- Finding where something lives across a codebase
- Reading and summarising files, modules, or docs
- Answering an independent factual question about the code
- Applying one mechanical change confined to a single file
- Running a test suite or linter and reporting what failed

**Keep in the main context** (these need the whole picture):
- Design decisions and trade-offs
- Anything touching several files that must stay consistent
- Deciding what the task actually means when it is ambiguous
- The final synthesis and report

### Writing a sub-agent prompt

A sub-agent **cannot see this conversation**. Every prompt must stand alone:
name exact file paths, state precisely what to do, and say what to report back.
A vague prompt wastes a whole round trip.

Sub-agents are read-only unless you say otherwise. Give write access only when the
scope is unambiguous and confined - and never let two sub-agents write to the same
file concurrently.

## Verify before reporting

After changing code, re-read what you changed and run the cheapest convincing check:
the test suite, the linter, or just executing it. Delegate the run to a sub-agent if
it is slow. Never report success on an unverified change.

If verification fails, fix and re-verify. Repeat until it passes or you hit something
that genuinely needs a human decision.

## Reasoning

Thinking is off by default here, deliberately: on this ELM deployment it measured
~400x slower with no quality gain, and at small output budgets the reasoning consumes
the whole allowance and returns empty content. Parallel sub-agents are the way to get
depth here, not longer single-model reasoning. If a specific step genuinely needs
extended reasoning, say so rather than assuming it is on.

## General

- Match the conventions already in the codebase over any personal style.
- Do not add work nobody asked for. Completing the whole of what *was* asked is not
  widening scope - it is the job.
- Size is not a reason to stop or to narrow a task. If the work is extensive, break
  it into batches and fan out to sub-agents; keep going until the list is empty. Do
  not pause mid-way to ask whether to continue.
- Stop early only when genuinely blocked by something a human must supply, or when
  continuing would destroy data. Long, repetitive or tedious does not qualify. If
  something truly is blocked, finish everything that is not blocked first.


## Editing: anchor-based (pi-hashline-edit-pro)

The built-in `edit` tool is **disabled**. Editing goes through `replace`, `insert`,
`anchor_grep` and `undo_last_change`. `read` returns every line as `anchor│content`,
and you edit by the 4-character anchor rather than by reproducing text.

This matters most for Llama. The old `edit` tool required reproducing `oldText` and
`newText` byte-perfectly inside JSON, and Llama routinely emitted raw newlines and
unbalanced braces, producing invalid JSON and silent no-ops. Anchors are four
characters, so there is almost nothing to get wrong.

`undo_last_change` reverts the most recent `replace`/`insert` on a file, even after a
restart.

## Llama needs explicit steps, not goals

Measured with anchor editing in place:

| Task given to Llama | Result |
|---|---|
| Single file, "fix the bug" | works, 18s |
| Two files, "read each and add docstrings" | **claimed FINISHED, changed nothing** |
| Two files, numbered steps: read, replace, read, replace | **both correct, 17s** |

The difference is planning, not editing. Give a Llama sub-agent a numbered list of
concrete actions and the exact files. Give it a goal and it will report success
without doing the work.

As a sub-agent it is less reliable still - across two fan-out runs of three agents,
one to two of three completed unaided and the orchestrator had to finish the rest.
Always verify a Llama sub-agent's output rather than trusting its report.

## Choosing a model for sub-agents

Two models are available to sub-agents. Pick per task with `subagent({ model: ... })`.

| Model | Use for |
|---|---|
| `elm-shim/meta-llama/Llama-3.3-70B-Instruct` | **Default for simple, single-step sub-agents.** Reading one file, grepping, summarising, answering one factual question, one mechanical edit. Roughly 2-3x faster than Qwen on this work. |
| `elm/Qwen/Qwen3.5-397B-A17B-FP8` | Sub-agents that need real multi-step reasoning, or that will chain several tool calls to reach an answer. Also the orchestrator, always. |

Llama reaches tool calling through a local translating proxy (the `elm-shim`
provider, started automatically by the `elm-shim` extension). Its native ELM
endpoint cannot call tools at all.

**Llama's limit is real: it drifts on multi-step work.** It has invented commands
and referenced files that do not exist when asked to plan across several files. Give
it one concrete, bounded job and a clear statement of what to report back. The moment
a sub-agent needs to decide *what* to do rather than *do* one thing, use Qwen.

A good split: fan out many cheap Llama sub-agents to gather, then reason over their
results yourself on Qwen.


## Project memory

Durable facts about a project live in that project's own `AGENTS.md`, in its root.
pi loads it automatically from the working directory and its ancestors, so it is
read back on every future session in that project, and it travels with the repo.

**Record a fact there when it is durable, project-specific, and not obvious from the
code**: the deploy target, which test command is canonical, an API quirk to work
around, a convention the team follows, a decision and its reason. Append a bullet
under a `## Facts` heading, creating the file if it does not exist.

**Do not record**: anything derivable by reading the code, transient state, secrets
or key material, or notes that only matter to the current conversation.

Keep entries one line where possible and correct existing bullets rather than
stacking contradictory ones. If a fact turns out to be wrong, fix it in place.

Session transcripts are separate: they go to `.pi/sessions/` in the working
directory and are not memory - they are a log.
