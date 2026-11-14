---
name: changing-code
description: "Fixing a bug, making failing tests pass, adding a function or writing code from a written spec - find the cause, then try to break your own change before reporting it."
---

# Changing code: fix the cause, then try to break the fix

Measured on 2026-11-14 (sixteen runs of eight harder tasks, each scored by a
check the session never saw): every failure was a change that made the
reported example work and went no further - a copy that still shared what was
nested inside it, a count right for the one group in the report and wrong for
the next, a parser that took a time no clock shows. None was hard; none was
tried.

1. **Reproduce it first.** Run the failing command and read the output before
   reading much code. If you cannot make it fail, say so and stop guessing.
2. **Name the cause in one sentence** - the line, and why it does what it does.
   A fix you cannot explain that way is a guess at the symptom.
3. **Fix it where it lives.** Not in the test, not in the caller that happened
   to show it, not by catching the error.
4. **Then try to break your fix.** Write three or four cases the report did not
   give and run them - a throwaway script or `python3 -c` is enough:
   - the neighbour of the example: a second key, group, file or caller;
   - the edges: empty, one item, zero, the largest sensible value, the value
     just outside what is allowed;
   - what is inside: a list or dict within the thing you copied or compared;
   - twice: the same call again, in another order, from two threads if threads
     are involved.
   If one fails, the cause in step 2 was not the whole cause.
5. **From a written spec**, turn each sentence into a case before writing code,
   the refusals too: "the level is one of A, B, C" means D is an error; a format
   `HH:MM:SS` means 25 hours is not a time. Say what you decided where the spec
   is silent, in one line, and do not ask unless two readings would give the
   user different results that matter.
6. **Keep what was not asked about as it was**: public names, return shapes,
   the tests, the order of results. If a faster or cleaner version returns
   something different on any input, it is a different function.

Report: the cause, the change (file and function), the command that failed
before and passes now, and the extra cases you ran with their results. A case
you thought of and did not run is not evidence.
