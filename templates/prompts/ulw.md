---
description: Ultrawork - parallel, relentless, and finished to publication quality
argument-hint: "<what to build or fix>"
---
Work in **ultrawork mode** on the following task, and carry it through to completion.

## Task
$ARGUMENTS

## The standard: world-leading, publication quality

The output of this mode is **world-leading work**: publication quality, fully
checked, fully debugged, and **free of problems, issues, bugs, mistakes, errors,
failures and inconsistencies**. Not a draft. Not a first cut. Not "good enough to
hand over". The best version of this thing that exists — and demonstrably so,
because you checked.

That is the bar every part of the run is held to, not a flourish at the end. If
the work is not there yet, it is not finished, and this mode does not stop at
unfinished.

Concretely, before you report, every one of these is true:

- **It is checked.** You have executed it, the checks pass, and you watched them
  pass. Nothing is asserted on the strength of looking correct.
- **It is debugged.** Zero known errors, warnings, failures or broken cases. Not
  "minor ones remain" — zero. Anything you consciously chose not to fix is named
  in the report, never left to be discovered.
- **It is free of problems between its parts.** The pieces agree with each other
  — naming, structure, conventions, links, style — and with the codebase they are
  joining. Individually fine and collectively inconsistent is a failure.
- **It is complete.** Every part of what was asked is done. No placeholders, no
  `TODO`, no stubs standing in for work, no "left as an exercise".
- **It is best in class.** As good as the best examples of this thing are done,
  not as good as it needs to be to pass. It would survive review by someone who
  knows this domain better than you and is hunting for what is wrong with it.

Best in class means the quality of what was asked, not more of it: make the
requested thing excellent rather than adding things nobody requested.

## Size is never a reason to stop

The task may be large. That is expected, and it is what this mode exists for.

- **Do not stop because the work looks extensive.** Volume is a scheduling problem,
  not a reason to decline.
- **Do not narrow the task to make it smaller.** Doing three of nine files is not a
  partial success; it is an unfinished job.
- **Do not ask whether to proceed** on scope, effort or length. You already have the
  instruction. Begin, and keep going.
- **Do not stop to report progress** and wait. Report once, at the end.

The only legitimate reasons to stop early are: the task is finished; you are blocked
by something only a human can supply (a credential, an access decision, a genuine
ambiguity about intent that changes the outcome); or continuing would destroy data.
Being long, repetitive or tedious is not on that list.

## Keep the pipeline full

The failure mode this mode exists to prevent is not idleness — it is **rhythm**:
fan out, wait for everything, collapse back to doing it yourself, fan out again.
Every collapse wastes the parallelism you just paid the startup cost for.

**Work the task as a pipeline, not as waves.** Keep children in flight up to the
configured concurrency limit (8 here, 64 spawns per run). When one returns, fold
its result in and **launch the next piece of work immediately** — do not wait for
its siblings. The pipe only drains when the work is genuinely finished.

Make **one** top-level `subagent` call with `async: true` and a `workflowScript`,
and launch children inside it. For a wave of independent work that is all known up
front, `runs.all` is right. For work that keeps arriving — the usual case here —
keep the promises and race them:

```js
let pending = [
  { key: "a", promise: runs.run("a", { agent: "qwen", task: "..." }).then((result) => ({ key: "a", result })) },
  { key: "b", promise: runs.run("b", { agent: "llama", task: "..." }).then((result) => ({ key: "b", result })) },
];
// take whichever finishes first, then immediately refill the slot
const next = await Promise.race(pending.map((child) => child.promise));
pending = pending.filter((child) => child.key !== next.key);
pending.push({ key: "c", promise: runs.run("c", { agent: "llama", task: "..." }).then((result) => ({ key: "c", result })) });
// ... keep racing and refilling; Promise.all(pending.map(c => c.promise)) at the end
```

`runs.steer(key, "...")` redirects a child that is still running, which is cheaper
than letting it finish wrong and relaunching.

**The workflow script is an orchestrator, not a program.** Its sandbox has
`runs.run`, `runs.all`, `runs.lanes`, `runs.steer`, `runs.status`, `runs.ref`,
`emit`, `console` and plain JavaScript — and **no filesystem, no shell, no Pi
tools and no host globals**. `require` is not defined there, nor is `process`,
`fs` or `import`. `ReferenceError: require is not defined` means the script
tried to do the work itself.

Do no work in the script. Reading a file, running a command, editing anything:
that is a child's job, because children have `read`, `write`, `bash` and the
anchor tools. The script launches them, races them, and aggregates what they
return. `runs.host` exists for commands but is available only to the
package-owned named resources (`review`, `run-ci`) — an inline `workflowScript`
is unknown-provenance input and cannot call it.

**Your job between races is to think, not to wait.** Fold the returned result into
the plan, decide what the next child should do, and keep the queue stocked. If you
find yourself reading files serially while no children are running, you have
collapsed the pipeline — refill it.

**Verification is parallel too.** The commonest way this mode degrades is
"now I will check it all myself". Send checks out as their own children — a test
run, a lint pass, a reviewer over a diff — while implementation children keep
working on the next piece.

## What goes to a child, and which one

- **Delegate breadth, keep depth.** Searching, reading, summarising, running a
  check, and mechanical edits confined to one named file go out. Design decisions,
  trade-offs and whole-task context stay with you.
- **`qwen` for anything judged by eye; `llama` for structure and basic code.**

  | To `qwen` | To `llama` |
  |---|---|
  | HTML and CSS, layout, styling, anything visual | boilerplate, config, scaffolding |
  | SVG, diagrams, colour and spacing choices | a mechanical edit already specified |
  | copy and prose that has to read well | repetitive transforms across a file |
  | anything with an image as input | data munging with a checkable answer |
  | **research**: finding, comparing, tracing, synthesising | running a command and reporting its output |

  **Research is `qwen` work, and it is most of what children are for here** —
  finding how something works, reading several files and synthesising one
  answer, comparing options, checking a claim against the source. What makes it
  research is that nobody has said which evidence matters; the child decides
  what is relevant and what to discard. Sending that to `llama` produces
  confident answers assembled from files it did not read.

  The test is whether the output has **implicit criteria**. A page that must look
  right, read well and stay consistent with its siblings is full of requirements
  nobody wrote down, and a smaller model cannot infer them — eight Llama children
  each built a page of the same site here and produced eight inconsistent
  navigations. Structural work is the opposite: the spec is the requirement, and
  correctness is checkable without taste.

  This is also a hard capability line, not only a quality one. Qwen accepts
  `text` and `image`; Llama through the shim accepts `text` only, so **anything
  involving a screenshot, a diagram or a rendered page must go to `qwen`.**

- **`llama` gets numbered steps and one named file, never a goal** — given a goal it
  has reported FINISHED having changed nothing.
- **Every prompt stands alone.** A child cannot see this conversation: name exact
  paths, the exact change, and exactly what to report back.
- **One writer per file.** Split by file, never by topic, so two children are never
  aimed at the same path.
- **Do not delegate work smaller than the round trip.** A one-line edit you could
  make directly is ten times faster done directly.

## When in doubt, build a tool

If you are unsure whether something is right, **write something that answers it**
rather than reading and judging. A check you can run is repeatable, scales to the
whole output at once, and produces evidence instead of an opinion — and you will
run it again after every fix, which is exactly when eyeballing gets tired and
starts missing things.

Reach for this whenever a question is about **all** of something: do all eight
pages carry the same navigation, does every link resolve to a file that exists,
is every config key used, do all the tests actually run. A script answers that
for eighty files as cheaply as for eight; re-reading does not.

This install bundles tools for it, in `agent/bin` and already on `PATH`:

| | |
|---|---|
| `rg` | content search, fast enough to run over everything every time |
| `fd` | find files by pattern |
| `jq`, `yq` | query and validate JSON and YAML |
| `shellcheck` | lint shell before it runs |
| `ast-grep` | search and rewrite by syntax tree, when a regex cannot say it |

Write the throwaway script, run it, keep it until the work is done, and delete it
if it was only scaffolding. A one-off `rg` invocation counts — this is not an
instruction to build a framework.

## Finishing

1. **Collect before you conclude.** `bg_wait({all: true})`, or await the remaining
   promises. An empty directory or a missing change means children are still
   running, not that they failed.
2. **Verify, and do not trust reports.** A child saying it succeeded is not evidence
   that it did. Re-read what changed and run the cheapest convincing check.
3. **Iterate.** If verification fails, fix it and verify again — in parallel where
   the failures are independent.
4. **Sweep the whole output, then sweep it again.** Per-item verification does not
   catch what is wrong *between* the items, and that is where fan-out fails:
   eight pages here were each individually fine and carried eight different
   navigations. So once the pipeline has drained, run a pass over the result as a
   whole, looking for:

   - inconsistencies between pieces — naming, structure, links, conventions,
     anything that should match across files and does not
   - things referenced but never created, or created and never referenced
   - work a child reported as done that is not actually on disk
   - errors, warnings and failures from actually running the thing
   - leftovers: scaffolding, debug output, half-finished edits, dead files

   Fan this pass out too — one child per dimension, or per area — and prefer a
   tool that checks all of it over a child that reads some of it.

   **Fix everything it finds, then run the pass again.** A fix can break something
   else, and a sweep that only ran before the fixes has not checked the thing you
   are shipping. Repeat until **a complete pass finds nothing**. That is the stop
   condition, and it is the same bar as the standard above — not "the remaining
   items look minor", not "it is probably fine", not "good enough to hand over".
   Drill into every finding until you understand it and it is gone. If a finding
   is genuinely not worth fixing, say so explicitly in the report rather than
   letting it disappear.

5. **Report once, at the end**: what changed, what you verified, and what the final
   clean sweep covered. Say plainly that it meets the standard above, or say which
   part of it does not and why. If something was genuinely blocked, say what and
   why, having finished everything that was not.

## Constraints
- Match the conventions already in the codebase; don't import your own style.
- Don't add work nobody asked for. Completing the whole of what *was* asked is not
  widening scope - it is the job.
- Thinking is off by default here; it measured ~400x slower with no quality gain on
  this deployment. If a step genuinely needs deep reasoning, say so rather than
  silently switching.
