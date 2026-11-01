# `.pi` is never committed

`.pi/` holds session transcripts, and a transcript holds every file the agent
read and everything pasted into the session. In a git repository that is the one
directory that must never reach a remote.

The launcher writes `.pi/.gitignore` containing a single `*` the first time pi
starts inside a work tree, which ignores the whole directory including that file,
so `.pi` is invisible to git rather than merely untracked. **Check it is there
before any `git add`, and restore it if it is missing:**

```bash
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  && { [ -f .pi/.gitignore ] || { mkdir -p .pi && printf '*\n' > .pi/.gitignore; }; }
```

This applies to every repository you touch, not just the one the session started
in - a clone you made, a worktree, a sub-directory repo, a repo a sub-agent
created. Run the check in each.

- **Never `git add` a path under `.pi/`**, and never use `git add -f` to defeat
  the ignore. If something in there is genuinely part of the deliverable, copy it
  out to a normal path in the project first.
- **Never `git add` `.ralph/`**: `ralph_start` writes its loop state there, in the
  working directory, and it is not ignored by default.
- **Never remove or weaken `.pi/.gitignore`**, and do not "fix" it by adding
  `!.gitignore`: that un-ignores the file and puts `.pi/` back in `git status`,
  where the next `git add -A` picks it up.

If you find `.pi` already tracked in a repository - it was committed before this
was in place - say so rather than quietly rewriting history. `git rm -r --cached
.pi` untracks it going forward, but the transcripts stay in the history, and
whether to rewrite that is the researcher's decision.
