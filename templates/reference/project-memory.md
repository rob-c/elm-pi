# Project memory

**There is one store, and it is the project's own `AGENTS.md`.** This install
has no memory *tool*: `pi-hermes-memory` was removed, and with it `memory_add`,
`memory_replace`, `memory_remove` and `memory_search`. Asked to remember
something, write it to the project's `AGENTS.md` rather than reaching for a tool
that is not there.

pi loads it from the working directory and its ancestors, so it is read on every
future session there, by anyone. Use it when the fact belongs to the project
rather than to you: the deploy target, the canonical test command, a convention
the team follows. Everything recorded this way travels with the repo, which is
the point.

**When the user asks you to remember something**, record it if it is durable,
project-specific, and not obvious from the code: the deploy target, which test
command is canonical, an API quirk to work around, a convention the team
follows, a decision and its reason. Append a bullet under a `## Facts` heading,
creating the file if it does not exist.

**Do not record**: anything derivable by reading the code, transient state, secrets
or key material, or notes that only matter to the current conversation.

Keep entries one line where possible and correct existing bullets rather than
stacking contradictory ones. If a fact turns out to be wrong, fix it in place.

A standing instruction for this session's work - units, notation, which file is
authoritative - is a pin (`pin_instruction`), not a memory entry.

Session transcripts are separate: they go to `.pi/sessions/` in the working
directory and are not memory - they are a log.
