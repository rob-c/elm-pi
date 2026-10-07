---
name: elm-delegation
description: "How to delegate to sub-agents on this install: when to fan out, routing between the qwen and llama sub-agents and the builtin agents, writing a child's prompt, budgets, checking a child's work, concurrent writers and worktrees, and answering a child's supervisor request. Load it before the first subagent call in a session."
---

# Delegating to sub-agents

The always-on rules are in AGENTS.md; this is the detail behind them. For several children at once, also load `elm-subagent-workflows`.

### Delegate to sub-agents by default

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

`subagent` is `async: true` by default, so a call returns immediately. One child
is one call: `subagent({ agent: "qwen", task: "..." })`. Several children are
**one** call that runs a workflow script (see "Mixing both in one orchestration"
below); separate top-level calls for each child are not the pattern here.
Collect with `bg_wait({ all: true })`, or `bg_wait({ id: "<runId>" })` for one run.

**Do not pass `nonBlocking` to `bg_wait`.** Async runs notify this session when
they finish, so a wait subscription buys nothing, and it is refused: it needs one
exact `id` and cannot be combined with `all`, and it cannot work at all in print
mode (`pi -p`).

Budget: 64 child launches per run (`maxSubagentSpawnsPerRun`), and at most 8 of a
workflow's children run at once (`globalConcurrencyLimit` in
`agent/extensions/subagent/config.json`); the rest queue. Match the count to how
the work divides - one sub-agent per file or per independent question - rather
than to a fixed number.

A completion notice previews only the first 8 children ("N additional child
preview(s) omitted by notice budget"). Read the rest with
`subagent({ action: "status", id })`, or have the workflow `return` the
aggregated outputs, and tell each child to report tersely.

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

A `qwen` child starts with a copy of this conversation (`defaultContext: fork`)
and a `llama` child starts with nothing (`fresh`), but neither can be relied on
to dig the task out of history. Every prompt must stand alone: name exact file
paths, state precisely what to do, and say what to report back. A vague prompt
wastes a whole round trip.

Three failures account for most bad delegation, and each has a fix you write into
the prompt:

- **Leaked distractors.** You paste in context the child does not need, and it
  reasons about the wrong thing. Give it what the task needs and nothing else.
- **Out-of-role work.** The child does something adjacent that was not its job.
  Open with its single responsibility - "Your only job is X" - and name what it
  must not touch.
- **Dropped shared context.** You assume the child knows a fact that lives only in
  this conversation. Repeat the facts it needs *in its prompt*, every time, even
  when you have already said them to another child. Repetition across prompts is
  correct here; it costs a few tokens and saves a round trip.

These matter more for `llama` than for `qwen`: adherence tracks how clearly the
instruction is written rather than how big the model is.

`qwen` and `llama` can edit files, and will unless the prompt says the task is
read-only - so say which it is, every time. Give write access only when the scope
is unambiguous and confined, and never let two sub-agents write to the same file
concurrently.

### Llama needs explicit steps, not goals

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

### Choosing a model for sub-agents

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

### Two named sub-agents: `qwen` and `llama`

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

**All codebase research goes to `qwen`**, and that is most of what a sub-agent is for
here. Finding how something works across a codebase, reading several files and
synthesising one answer, comparing options, tracing why a thing behaves as it
does, checking a claim against the source. What makes it research is that
**nobody has said in advance which evidence matters** — the agent has to decide
what is relevant, what to discard and what the answer actually is. That is the
same implicit-criteria test as visual work, and Llama fails it the same way: it
has invented commands and referenced files that do not exist when asked to work
across several. The builtin `scout`, `researcher`, `oracle` and `reviewer`
agents are pinned to Qwen in `settings.json` for this reason.

Web research is different. `qwen` excludes the web tools, so it can never do
it. The builtin `researcher` keeps them and is pinned to Qwen, but outside
`pi --remote` the egress proxy refuses every host but the ELM gateway, so its
searches come back 403. Send web research to `researcher` only in a session
started with `pi --remote`; otherwise say the session cannot reach the web.

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

Both agents can edit, and neither declares a `tools` allowlist, deliberately. A
`tools` list is a strict allowlist matched by name: anything it does not name is
unavailable, the anchor tools included. The builtin `worker`, `delegate`,
`scout`, `reviewer` and `oracle` all declare such lists without the anchor
tools, so on this install they can change a file only with `write` or `bash`.
Send edits to `qwen` or `llama`. With `tools` omitted, a background child takes
the ambient extensions, so `read` and the anchor tools are simply there;
`excludeTools` does the narrowing. Never launch an editing child with
`async: false`: a foreground child loads no ambient extensions.

The builtin `claude-code`, `codex-exec` and `cursor-agent` agents (and their
`-writer` forms) drive commercial CLIs. They are disabled in `settings.json`
and the tool's agent-management actions are switched off; never launch, create
or re-enable an agent that runs anything but the ELM models.

### Concurrent writers, and the worktree option

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

`worktree` is also a config key — `agent/extensions/subagent/config.json`, where
this install sets it `false`. It is the default for launches that pass no value
of their own, so flipping it to `true` isolates every workflow child without
anyone asking. Do not flip it on a machine whose projects are plain
directories: pi-subagents throws rather than degrading, and there is no fallback
setting.

**So the precondition is the work, not the flag.** Before a writing fan-out you
want isolated, make the project a repo and commit, because isolation branches
from a clean HEAD:

```bash
git rev-parse --is-inside-work-tree 2>/dev/null \
  || { git init -q && mkdir -p .pi && printf '*\n' > .pi/.gitignore \
       && git add -A && git commit -qm "baseline before a fan-out"; }
git diff --quiet && git diff --cached --quiet || echo "uncommitted changes: isolation will refuse"
```

One `git init` in the project directory is the whole difference between
isolation being unavailable and being available. Write `.pi/.gitignore` before
the first `git add`, as above: the launcher writes it only when pi starts inside
an existing work tree, so a repository created mid-session would otherwise
commit the transcripts. If you are told to isolate a fan-out
and the directory is not a repo, do that first and say you did, rather than
reporting that isolation is unsupported here.

Two things about it worth knowing before you rely on it. Isolation applies to
any launch that resolves `worktree: true`: per workflow child, on a direct
`subagent({ agent, task, worktree: true })`, or from the config key, which is
applied to every request that does not set it. And when children do run
isolated, **the patches are the result**: a child's report no longer means its
work is in your working copy.

### Answering a sub-agent's supervisor request

A `qwen` sub-agent can ask one focused question through `contact_supervisor`.
It arrives as a **Supervisor interview request** card carrying a `Request ID`.

Reply with **the id on that card**, through the `subagent_supervisor` tool:

```js
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

**There is no completion guard.** pi-subagents removed it in 0.70.1: a child
that finishes having changed nothing is reported as a successful run, so a
child's "FINISHED" or `CHANGED` block is not evidence. After every implementation
child, check the named file yourself (`read` it, or `git diff --stat`) before
relying on it. If nothing changed, the prompt was the cause: it was a goal where
it needed a procedure, or it named no file.

- **Relaunch once** with numbered steps and an exact path. Do not take the work
  back on the first failure: one reprompt is cheaper than collapsing the
  pipeline, and taking over teaches you nothing about why it failed.
- **Do not narrate a cause you did not check.** Read the child's output or
  transcript (`subagent({ action: "status", id, view: "transcript" })`) before
  deciding what happened.

An implementation task that cannot be reduced to numbered steps over one named
file is a `qwen` task, not a `llama` one.
