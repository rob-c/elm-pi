# Python-port treadmill, 2026-11-15

Five local source snapshots were bootstrapped with the existing pinned dependencies. Seventeen parent sessions used the real ELM gateway and Qwen/Qwen3.5-397B-A17B-FP8; each parallel case also launched two Qwen children. The installer smoke replies, captured-launch checks and deterministic extension replays are separate checks.

The final snapshot is `guarded`. Concurrent network-mode and jail edits in the shared checkout were excluded at the user’s request. The full-suite result below is from the frozen snapshot; it does not cover the independently changing checkout.

The [machine-readable record](python-port.json) includes every result, exact prompts, flags, software versions, source hashes, retained-test commands, token counts and limitations. The [patch](python-port.patch) contains only this treadmill’s changes relative to the initial dirty source snapshot, before the independent network work. The [scorer](python_port_score.py) preserves the checks used here.

## Results

| Launcher and snapshot | Task | Functional checks | Workflow checks | Driver exit | Whole run | Parent tool errors | Total tokens, including children |
|---|---|---|---|---:|---|---:|---:|
| python-before | log-parser.1 | fail | — | 0 | fail | 2 | 222,101 |
| python-before | numerics.1 | pass | — | 0 | pass | 4 | 481,913 |
| python-before | parallel.1 | fail | fail | 0 | fail | 9 | 1,859,001 |
| python-before | text-tools.1 | pass | pass | 0 | pass | 0 | 124,304 |
| bash-reference | log-parser.1 | pass | — | 0 | pass | 3 | 558,106 |
| bash-reference | numerics.1 | pass | — | 0 | pass | 1 | 356,441 |
| bash-behavior | parallel.1 | pass | pass | 0 | pass | 2 | 593,043 |
| bash-behavior | text-tools.1 | pass | pass | 0 | pass | 0 | 145,489 |
| python-after | log-parser.1 | pass | — | 0 | pass | 1 | 206,468 |
| python-after | numerics.1 | pass | — | 0 | pass | 0 | 381,840 |
| python-after | parallel.1 | pass | fail | 0 | fail | 3 | 784,606 |
| python-after | text-tools.1 | pass | pass | 0 | pass | 0 | 145,429 |
| python-guarded | log-parser.1 | pass | — | 1 | fail | 1 | 296,643 |
| python-guarded | numerics.1 | pass | — | 0 | pass | 1 | 327,207 |
| python-guarded | parallel.1 | pass | pass | 0 | pass | 7 | 927,185 |
| python-guarded | text-tools.1 | pass | pass | 0 | pass | 0 | 145,684 |
| python-timer | log-parser.1 | fail | — | 0 | fail | 0 | 145,766 |

`bash-reference` and `bash-behavior` together are the four-task Bash baseline. `python-before` uses the initial port. `python-after` has the launcher/UI fixes and scratch guidance. `python-guarded` adds the enforced scratch rule and saved-test guidance. `python-timer` repeats the parser after correcting the driver clock.

Functional checks independently inspect the requested files and behavior. Workflow checks verify recorded successful delegation or the exact todo sequence, plus a Markdown table for the text task and reproducible saved test files for the parallel task. A runnable retained test does not by itself prove that a child historically ran that exact file. The coding tasks use the existing hidden checks, demonstrated to fail the untouched seed and pass the reference solution before these runs.

## Failures that motivated changes

- Capturing Python’s model-list output timed out after 15 seconds even though the launcher had exited successfully: its forked proxy watchdog still held the output pipes. The watchdog now detaches standard streams. The same real captured launch then returned normally, as did the Bash reference.
- A failed interpreter probe with an unfamiliar exit status raised `KeyError`. It now gives the intended fallback/refusal. Empty tool exclusions returned the argument tuple in the wrong order; launcher and session arguments now retain their positions.
- The supposed Bash/Python comparison fixture invoked Python in both arms. It now invokes the actual Bash reference, with an independence check that removes Python from that fixture.
- `/help bash` reported no match in both baseline launchers. Help now searches active tool names and descriptions. Todo display now safely flattens multi-line text and strips control characters, and budgets actual terminal rows: the narrow-width replay fell from 111 rows to five, checked at widths 10, 40 and 80. Stored todo text remains unchanged. Resumed-session greetings, model-selection footer refresh and partial todo calls also have regressions.
- An async launch did not immediately arm the wait guard. Successful launch results now arm it, preserving one status check and native completion delivery.
- Parallel children created and deleted the same `.pi/tmp/venv`. Guidance alone failed in the intermediate run, so child commands that create or destroy that shared environment are refused with a private-directory recovery instruction. Prepared environment use and private child environments remain allowed.
- The intermediate parallel run delivered correct modules but broken pytest files: the required local module name shadowed a standard-library module. Inline assertions did not repair those tests. Guidance now requires running saved tests, fixing the runner/import setup, and preserving requested filenames. It recommends unittest for suitable new Python projects without a framework.
- The treadmill hid startup failures and corrupted split UTF-8 pipe chunks. It now returns failure status, retains startup/extension diagnostics, decodes streams safely, and terminates the driven process group. Empty seed projects, missing optional analysis Python and failed installer verification also have regression coverage.

The original Python parser also accepted an invalid clock time. Its hidden check was kept unchanged; this is a model-output failure, not evidence that a launcher change alone fixes reasoning. One run per task cannot establish general accuracy or speed. Heavy concurrent host load further rules out a latency claim.

The first final parser run passed its functional check but the driver timed it out after the host wall clock jumped approximately 358 seconds. Other simultaneous runs show the same difference between wall timestamps and the runner’s monotonic duration. The driver now measures deadlines and quiet periods with a monotonic clock; a deterministic clock-jump regression and a fresh parser run check the fix. The failed driver result remains in the table. Whole-run verdicts require zero driver and analyzer exits as well as passing artifact checks.

The fresh parser run exited normally but again accepted `25:00:00`, failing the unchanged hidden check. That remaining model-output failure is preserved. The changing-code guidance was present in its prompt, so this is not claimed to be solved by adding more instructions. These measurements demonstrate specific launcher, rendering and harness fixes; they do not establish that Qwen’s general coding accuracy is better than with the Bash baseline.

In the final parallel run, the children chose separate scratch directories without triggering the new runtime refusal; its blocked-command behavior is covered by 35 deterministic command cases. The parent reran the saved suites (16 and 20 tests) and the integration test (one test). Missing-command and global-pip attempts still occurred before virtualenv recovery in these installs without the optional analysis environment; their tool errors remain in the totals.

## Validation

The final frozen checkout used Python 3.9 and the project’s full test command:

```text
timeout 600 /usr/bin/python3 -m unittest discover -s tests
Ran 11128 tests in 572.916s
OK (skipped=37)
```

The command-guard check also loaded the extension through pi’s own loader and checked types:

```text
check-extension: templates/extensions/command-guard.ts
  events: session_start, session_shutdown, tool_call
  load: ok, with pi's own loader
  tests naming it: test_child_scratch, test_guard_vs_bash, test_matchers_agree, test_permission_mode_policy, test_permission_modes, test_permission_rules, test_read_only_auto, test_run_guards, test_self_development
  tests: Ran 2559 tests in 20.806s OK (skipped=6)
  types: ok

ok: command-guard.ts loads, registers 3 things, and is registered, documented and tested
```

Focused launcher comparisons, wait-guard checks, installed-TUI rendering, Python syntax, TypeScript and ShellCheck checks also passed. Each retained install log records 44 extensions loaded and zero failures. Dependencies were reused locally; the optional analysis Python environment was omitted. External MCP remains disabled by project policy; the real `pi mcp` refusal was verified, not an external MCP connection.

A bytecode test also needed an isolated HOME: Apple Python 3.9 changes its bytecode behavior when HOME is absent. Both the effective flag and the environment export/unset are now asserted. The earlier unversioned verification copy could not run Git-dependent tests correctly. The final frozen copy was initialized as a local checkout and its source indexed; no commit was made.

## Files changed

| File | Change |
|---|---|
| [python/elmpi/proxy.py](../../../python/elmpi/proxy.py) | Detach watchdog standard streams so captured launches return EOF. |
| [python/elmpi/interpreter.py](../../../python/elmpi/interpreter.py) | Handle arbitrary failed interpreter probe statuses without KeyError. |
| [python/elmpi/tools.py](../../../python/elmpi/tools.py) | Preserve argument ordering when tool exclusions are empty. |
| [pi.bash](../../../pi.bash) | Document equivalent existing watchdog and argument behavior in the reference. |
| [lib/sandbox.sh](../../../lib/sandbox.sh) | Document the existing interpreter fallback behavior used as reference. |
| [bootstrap.sh](../../../bootstrap.sh) | Retain failed model-list status and stdout, including missing-credential diagnostics. |
| [templates/extensions/help.ts](../../../templates/extensions/help.ts) | List and search active tools, including their descriptions. |
| [templates/extensions/empty-state.ts](../../../templates/extensions/empty-state.ts) | Suppress new-session greeting on a resumed conversation. |
| [templates/extensions/status-line.ts](../../../templates/extensions/status-line.ts) | Refresh the footer immediately on model selection. |
| [templates/extensions/todo.ts](../../../templates/extensions/todo.ts) | Bound actual terminal rows and sanitize display text without altering stored todos; handle partial calls. |
| [templates/extensions/command-output.ts](../../../templates/extensions/command-output.ts) | Narrow unknown metadata before adding colour, preserving existing structured output. |
| [templates/extensions/command-guard.ts](../../../templates/extensions/command-guard.ts) | Refuse a child creating or deleting the shared .pi/tmp/venv while allowing preprepared environment use. |
| [templates/extensions/wait-guard.ts](../../../templates/extensions/wait-guard.ts) | Arm polling detection on successful async launches without aborting notification delivery. |
| [templates/agents/qwen.md](../../../templates/agents/qwen.md) | Require separate scratch directories, cleanup confined to each child, and runnable saved tests. |
| [templates/agents/llama.md](../../../templates/agents/llama.md) | Require separate scratch directories, cleanup confined to each child, and runnable saved tests within its assigned scope. |
| [templates/skills/elm-delegation/SKILL.md](../../../templates/skills/elm-delegation/SKILL.md) | Include separate scratch directories in the parent delegation brief. |
| [templates/skills/changing-code/SKILL.md](../../../templates/skills/changing-code/SKILL.md) | Require retained, runnable tests and repair import/runner failures rather than substitute inline assertions. |
| [docs/tuning/harness/treadmill/batch.sh](../../../docs/tuning/harness/treadmill/batch.sh) | Reuse installed dependencies optionally; propagate bootstrap and session failures. |
| [docs/tuning/harness/treadmill/drive.mjs](../../../docs/tuning/harness/treadmill/drive.mjs) | Detect failed launches, preserve UTF-8, log extension errors, clean up the process group, and use monotonic deadlines. |
| [docs/tuning/harness/treadmill/analyze.py](../../../docs/tuning/harness/treadmill/analyze.py) | Keep startup diagnostics when no session transcript exists. |
| [docs/tuning/harness/treadmill/summary.py](../../../docs/tuning/harness/treadmill/summary.py) | Include driver and assistant failures in error counts. |
| [docs/tuning/harness/treadmill/score.py](../../../docs/tuning/harness/treadmill/score.py) | Use the recorded interpreter when the optional analysis environment is absent. |
| [tests/test_python_launcher.py](../../../tests/test_python_launcher.py) | Use an independent Bash fixture and pin the three launcher regressions. |
| [tests/test_treadmill.py](../../../tests/test_treadmill.py) | Exercise driver failure, decoding, cleanup, batch, and scorer behavior with local processes. |
| [tests/test_bootstrap_verification.py](../../../tests/test_bootstrap_verification.py) | Pin missing-credential, failed-launch, and model-policy diagnostics. |
| [tests/test_ext_help.py](../../../tests/test_ext_help.py) | Check active-tool listing and searches. |
| [tests/test_ext_empty_state.py](../../../tests/test_ext_empty_state.py) | Check resumed startup suppression. |
| [tests/test_ext_status_line.py](../../../tests/test_ext_status_line.py) | Check model-selection refresh. |
| [tests/test_ext_todo_widget.py](../../../tests/test_ext_todo_widget.py) | Exercise real installed TUI rendering at narrow widths and partial tool calls. |
| [tests/test_run_guards.py](../../../tests/test_run_guards.py) | Replay waiting immediately after an async launch. |
| [tests/test_child_scratch.py](../../../tests/test_child_scratch.py) | Replay child virtualenv creation and cleanup with shell parsing and allowed-use controls. |
| [tests/test_prompts.py](../../../tests/test_prompts.py) | Pin separate child scratch and saved-test instructions. |
| [tests/test_session_regressions.py](../../../tests/test_session_regressions.py) | Record the sessions and replays that motivated the fixes. |
| [tests/test_agent_environment.py](../../../tests/test_agent_environment.py) | Use shipped-source inventories rather than local scratch notes for documentation checks. |
| [tests/test_project.py](../../../tests/test_project.py) | Give the bytecode probe an isolated HOME; Apple Python 3.9 otherwise changes behavior before launcher settings are evaluated. |
| [INSTALL.md](../../../INSTALL.md) | Describe corrected extension behavior. |
| [docs/tuning/TREADMILL.md](../../../docs/tuning/TREADMILL.md) | Document failure reporting, cleanup, dependency reuse, and scorer fallback. |

Evidence files added beside this report: `python-port.json` (results and hashes), `python-port.patch` (the isolated source changes), and `python_port_score.py` (the independent scorer). `docs/tuning/README.md` links this experiment. To rescore the retained local workspace, run `python3 python_port_score.py WORK`.

The scratch guard covers the observed direct shell commands; it does not claim exhaustive shell ownership enforcement. Raw local transcripts are retained in the temporary treadmill workspace; their report paths are normalized in the JSON record.
