---
description: Reproduce a failure, fix it, and show both before and after
argument-hint: "[the failure, error or behaviour]"
---
Fix this: ${1:-the failing check in this project}.

1. Reproduce it first, and show the command with its real output. A failure you
   have not seen is a failure you cannot claim to have fixed.
2. Read the code the traceback names, and the code that calls it, before
   changing anything. Say in one line what the cause is - the line where the
   wrong assumption is made, not where it surfaced.
3. Make the smallest change that fixes the cause. Do not refactor, rename or
   reformat anything the request does not name, and do not weaken, skip or
   delete a failing check to get a pass.
4. Run the same command again and show its output, then the project's test
   suite if it has one.
5. Re-read your diff as the person reviewing it would.

Report: the cause, the change with its path, the commands and their real
output, and anything still wrong that you did not fix.
