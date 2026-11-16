---
description: Write the project's AGENTS.md from what is actually here
argument-hint: "[anything a newcomer must know]"
---
Write `AGENTS.md` for ${1:-this project}, from what is in the directory now, for the
next agent who starts work in it with no memory of this conversation.

Find out, do not assume: the build, test and lint commands, and the exact
invocation of each - **run every command you write down** and paste the line
that worked; the layout, in the order a newcomer meets it; the conventions the
code actually follows (naming, error handling, units, config); what is
generated and must never be edited; what is fragile or slow; and anything that
has bitten before.

Keep it to 20-40 lines of instructions, not description: rules a reader can
follow, with the command to run and the path to read beside each. No badges, no
architecture essay, no restatement of what the code obviously does, and no
invented command that you did not run.
