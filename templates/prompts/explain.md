---
description: Explain code, data or output, changing nothing
argument-hint: "[file, function or output that puzzles you]"
---
Explain ${1:-the files this project is built from} for a physicist who has read
none of it and will not take a description on trust.

- Read the real files first. Quote the lines you are explaining, with their
  path, and say what each one does and why it is written that way rather than
  the obvious alternative.
- State the assumptions the code makes about its inputs (units, ranges, dtypes,
  ordering, what is never None) and what happens when one is violated. If you
  are not sure, read the callers or run it - do not guess.
- Name anything that looks wrong, and say whether you checked it or suspect it.
- Change nothing in the project. If a run would make it concrete, run it on a
  copy or in `.pi/tmp/`, and show the command and its output.

End with the two or three sentences a reader needs to hold in their head, and
nothing else.
