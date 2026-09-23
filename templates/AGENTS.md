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

**Do not pass `nonBlocking` to `bg_wait`.** Ordinary async sub-agent runs notify
this session natively when they finish, so a wait subscription buys nothing. If
you pass it anyway you get one of two refusals rather than a result:

- `Non-blocking wait subscriptions require id ...` - it binds exactly one run,
  so it needs `id`, and it cannot be combined with `all`.
- `... require a long-lived interactive subagent runtime` - it cannot work at
  all in print mode (`pi -p`).

The two correct shapes are `bg_wait({all: true})` to collect a fan-out, and
`bg_wait({id: "<runId>"})` to block on one run. `nonBlocking` is for detached or
provider work that has no native completion notification, which is not what
`subagent` produces.

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
Always verify a Llama sub-agent's output rather than trusting its report. It is not
a speed optimisation either: see the measurements below.

## Choosing a model for sub-agents

**Default to Qwen for everything, including sub-agents** - see the two named
sub-agents below for the one carve-out. Measured directly
against the gateway, Qwen 3.5 397B is both faster and more capable than Llama 3.3
70B here - the MoE model with 17B active parameters beats the 70B dense one:

| | Qwen 3.5 397B | Llama 3.3 70B |
|---|---|---|
| Single request, ~180 tokens out | 2.7-3.0s, 68-76 tok/s | 3.7-5.7s, 30-47 tok/s |
| 8 concurrent | 2.1s wall, 399 tok/s aggregate | 3.4s wall, 295 tok/s |
| 12 concurrent, all Qwen | **2.5-2.7s wall, 535-566 tok/s** | - |
| 12 concurrent, 6 Qwen + 6 Llama | 3.7-4.0s wall, 309-347 tok/s | - |

Splitting a fan-out across both models makes it **slower**, not faster: the Llama
half sets the wall time. Qwen also holds up under concurrency - 12 parallel
sub-agents came back in 2.5s.

`elm-shim/meta-llama/Llama-3.3-70B-Instruct` remains available for when Qwen is
rate-limited or unavailable, and it reaches tool calling through a local
translating proxy (the `elm-shim` provider, started automatically by the
`elm-shim` extension); its native ELM endpoint cannot call tools at all. The shim
buffers the whole response before re-emitting it, so it loses streaming as well.

**Llama's limit is real: it drifts on multi-step work.** It has invented commands
and referenced files that do not exist when asked to plan across several files.
Give it one concrete, bounded job and a clear statement of what to report back,
and verify what it reports. The moment a sub-agent needs to decide *what* to do
rather than *do* one thing, use Qwen.

## Two named sub-agents: `qwen` and `llama`

Two agent definitions ship with this install, in `agent/agents/`. They exist so
that delegation names a *role*, not a model id:

| | `qwen` | `llama` |
|---|---|---|
| Model | Qwen 3.5 397B, direct | Llama 3.3 70B, through the tool-call shim |
| For | work that needs judgement | work that has already been decided |
| Given | a task | a numbered procedure |

**`qwen` is the default.** Anything where the sub-agent has to work out *what* to
do belongs here: exploring code nobody has read yet, distilling several files
into an answer, deciding how a change should be shaped, reviewing.

**All research goes to `qwen`**, and that is most of what a sub-agent is for
here. Finding how something works across a codebase, reading several files and
synthesising one answer, comparing options, tracing why a thing behaves as it
does, checking a claim against the source. What makes it research is that
**nobody has said in advance which evidence matters** — the agent has to decide
what is relevant, what to discard and what the answer actually is. That is the
same implicit-criteria test as visual work, and Llama fails it the same way: it
has invented commands and referenced files that do not exist when asked to work
across several. The builtin `scout`, `researcher`, `oracle` and `reviewer`
agents are pinned to Qwen in `settings.json` for this reason.

Note for web research specifically: `web_search`, `fetch_content`,
`source_check` and `get_search_content` are excluded by default, so a
`researcher` child has no web tools unless the run is started with
`PI_ELM_WEB=1`. Without that it can research the codebase and nothing else.

**`llama` is for rote execution of a fully specified change.** Applying a
formatting convention, generating boilerplate to a stated shape, a mechanical
edit confined to one named file, running a command and reporting the output.

**Anything judged by eye goes to `qwen`**: HTML and CSS, layout, styling, SVG
and diagrams, prose that has to read well. Output with implicit criteria — it
must look right, and match its siblings — is full of requirements nobody wrote
down. Eight Llama children each built a page of the same site here and produced
eight inconsistent navigations. It is a capability line too: Qwen accepts text
and images, Llama through the shim accepts text only, so anything with a
screenshot, diagram or rendered page as input must be `qwen`.

Three rules, all of them from measurements above, not preference:

1. **Give `llama` steps, never a goal.** "Read each file and add docstrings"
   returned FINISHED having changed nothing. The same work as numbered steps —
   read, replace, read, replace — was correct in 17s.
2. **One file per call, named explicitly.** It drifts across multiple files and
   has invented paths that do not exist.
3. **Verify everything it returns.** In past fan-outs one to two of three
   completed unaided. Verification is the orchestrator's job, and a `qwen`
   sub-agent is a reasonable place to put it.

Both agents can edit. Editing is anchor-based, and the `tools` allowlist in an
agent definition *names* a tool without loading the extension that provides it,
so both definitions load `pi-hashline-edit-pro` through
`subagentOnlyExtensions`. Verified: a `llama` sub-agent reads a file, changes a
line by anchor and reads it back. Without that line the child silently loses
`read` and every anchor tool, and falls back to `bash` and whole-file `write` —
which is how a "rote" agent quietly becomes a destructive one.

### Mixing both in one orchestration

For anything beyond a single child, make **one** `subagent` call with
`async: true` and a `workflowScript`, and launch the children inside it. The
script is ordinary JavaScript: `runs.all([...])` for parallel fan-out,
`runs.run` for a keyed child, `runs.lanes` for staged work. Children come back
as plain JSON with `ok`, `output` and `structuredOutput`.

Different children can run on different models, because the model travels with
the agent name:

```js
const [survey, edits] = await runs.all([
  { key: "survey", agent: "qwen",  task: "Read src/api/*.ts and return, per file, the exported names and one line on what each does." },
  { key: "fmt",    agent: "llama", task: "Step 1: read src/util/date.ts. Step 2: replace the body of formatDate with the version below. Step 3: read it back and report the new body.\n\n<exact code>" },
]);
return { survey: survey.output, edits: edits.output };
```

Verified on this install: one workflow call, a `qwen` child and a `llama` child
in parallel, each on its own model, both results aggregated by the script.

The routing rule is the same one as above, applied per child rather than per
task: **whoever has to decide gets Qwen; whoever is following a procedure gets
Llama.** Size is the second half of that test - **send a child to `llama` by
default when all three hold**, rather than treating it as the exception:

1. the task is fully specified, with nothing left to decide
2. it is confined to one named file, or to no files at all
3. the expected answer is short - a lookup, one edit, a format pass, a command
   and its output

Anything failing one of those three goes to `qwen`: multi-file work, anything
needing a judgement call, and anything whose answer is a page of prose. The
`delegate` role is pinned to Llama in `settings.json` for the same reason, with
Qwen as its fallback.

Give a Llama child numbered steps even when the task is trivial. That is not
ceremony: a one-line goal is what produced "FINISHED" with nothing changed. A survey, a synthesis or a review is a Qwen child. A per-file
mechanical edit with the exact replacement text already written out is a Llama
child, and there can be many of them in the same `runs.all`.

Two settings back this up, in `agent/settings.json` under `subagents`:

- `agentOverrides` pins `worker`, `scout`, `reviewer`, `oracle` and
  `researcher` to Qwen rather than letting them drift with the session model,
  and gives the first three `fallbackModels: llama`. That fallback fires only
  for retryable provider failures - rate limit, overload, unavailable - and
  only before the child has done any tool work. It is the honest use of the
  small model here: capacity, not speed.
- `modelScope` is `enforce: true, strict: true` with `allow: elm/*,
  elm-shim/*, inherit`. The ELM-only policy strips commercial catalogues in the
  parent; this closes the same door for children, so a per-run `model:`
  override or a fallback chain cannot route one off the university's GPUs.

**This split is not a speed optimisation.** Llama is the slower model here, and
a fan-out split across both is slower end to end than sending all of it to Qwen.
Route volume to `llama` when Qwen is rate-limited, or if a cheaper allocation
charge justifies the wall-clock cost — and note that the charge is the part
nobody has verified, because `guidanceCost` is only visible in the ELM web UI.
If the goal is a faster delegation rather than a cheaper one, the measured lever
is `pi --fast`, which cuts sub-agent startup from ~3.3s to ~0.9s.

## Concurrent writers, and the worktree option

Two children writing the same file, or a child and you writing it at once, is
the failure this section exists to prevent. It has happened here: a fan-out of
eight writers building a site, where the parent listed the directory before the
children finished, concluded they were stuck, and rewrote all eight pages
itself. The children then finished and wrote theirs. Same files, two authors,
last writer wins.

**The two cheap protections come first**, and they cost nothing:

1. **Collect before you check.** `bg_wait({all: true})` after a fan-out. The run
   above went wrong because the parent checked for results that could not exist
   yet. An empty directory means the children have not finished, not that they
   failed.
2. **One writer per file.** Split a fan-out by file, not by topic, so two
   children are never aimed at the same path. Where that is not possible, do the
   writing yourself and use children to gather.

**Worktree isolation is available and off by default.** Turned on, each child
branches from clean HEAD into its own git worktree and hands back a patch and a
handoff manifest instead of touching your tree. It is genuinely stronger than
the two rules above — and it is opt-in because it **requires a git repository
with a clean checkout**, and throws `worktree isolation requires a git
repository` without one. Most working directories are not repos, and failing
every launch there is worse than the race it prevents.

Turn it on per call, for a fan-out that writes in a repo you have committed:

```js
await runs.all([
  { key: "api", agent: "qwen",  task: "...", worktree: true },
  { key: "ui",  agent: "llama", task: "...", worktree: true },
]);
```

Two things about it worth knowing before you rely on it. Isolation applies to
**workflow children** — a child inside a `workflowScript` — and a direct
`subagent({agent, task})` call runs in the shared cwd whatever the config says;
verified by a direct launch recording `worktreePath: null` and writing straight
into the working tree. And when children do run isolated, **the patches are the
result**: a child's report no longer means its work is in your working copy.

## Answering a sub-agent's supervisor request

A `qwen` sub-agent can ask one focused question through `contact_supervisor`.
It arrives as a **Supervisor interview request** card carrying a `Request ID`.

Reply with **the id on that card**:

```
subagent_supervisor({ action: "reply", replyTo: "<Request ID from the card>", message: "..." })
```

`No pending supervisor request found for replyTo '<id>'` means the id was
wrong, usually one reused from an earlier request, a run id, or a child target
id. Nothing is lost when that happens: the request is still pending and the
card is re-displayed. Call `subagent_supervisor({ action: "pending" })` to list
the live requests and their real ids rather than guessing.

Answer it or stop the run. A workflow whose child is waiting on an interview
stays **paused** until that child exits, so an unanswered question stalls the
whole orchestration. `llama` sub-agents cannot open one at all - they report
what was missing and hand back.

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
