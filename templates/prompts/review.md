---
description: Review work for correctness, units and honest reporting - change nothing
argument-hint: "[what to review: a diff, files, a result]"
---
Review ${1:-the uncommitted changes in this project} as a sceptical colleague
would before it goes into a paper or into other people's hands. Change nothing.

Read the code and, where there is one, run it - a review that says "looks
correct" without running anything is not a review. Look for, in this order:

1. **Wrong results**: wrong formula or index, an unweighted fit to counts, a
   mean over mixed units, silent `dropna`, an uncertainty that does not follow
   from the data, a number in a reply that is in no output.
2. **Claims**: anything stated as done, verified or complete that no command in
   the work shows. Say which claim and which command is missing.
3. **Edges**: empty input, one element, a zero denominator, off-by-one at both
   ends, a path or unit that changes mid-file.
4. **Evidence**: every number with units, and an uncertainty where one is
   meaningful; chi2/ndf for a fit, with the residuals looked at.

Report findings as a list ordered by severity, each one line with `path:line`,
what is wrong, and what would show it. Then one line naming what you did not
examine. No praise, no summary of what the code is for.
