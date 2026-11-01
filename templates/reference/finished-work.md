# Every file you produce is finished work

This applies to every session, and to anything a sub-agent wrote on your
behalf. The work is judged by its worst artefact, and that is reliably the file
nobody reopened after a child reported it done.

- **Match the file and the codebase.** Naming, structure, comment density,
  formality. Read a neighbouring file before creating a new one. Code that is
  individually reasonable and stylistically foreign is the clearest tell there is.
- **Name things for what they are.** Never `final`, `new`, `v2`, `_fixed`,
  `updated`, `enhanced`, `copy` or `untitled` - in files, directories, branches,
  functions or variables.
- **Leave nothing over.** No `.bak` or `.orig`, no commented-out alternatives, no
  debug prints, no dead code kept in case, no files from an approach you
  abandoned. Delete your scaffolding before you report. A script whose output you
  report is not scaffolding: it is the evidence, and it stays.
- **Leave nothing standing in for real content.** No `TODO`, `FIXME`, `XXX`, no
  `lorem ipsum`, no `your-name-here` or `example.com` where a real value belongs.
  If you cannot finish something, say so in the report - a sentence naming what is
  missing beats a stub that looks finished.
- **Leave nothing that only works here.** No absolute paths from this machine, no
  hostnames, no temp directories, and never a key, token or anything out of a
  `.env` written into a file that will be read somewhere else.
- **Comment the why.** The constraint, the gotcha, the reason this is not the
  obvious approach - and only where it is not evident. Never restate the code.
- **Write the specific thing asked for.** No interface with one implementation,
  no wrapper used once, no config option nobody requested, no `try/catch` that
  logs and continues, no guard on a value that is always set.
- **Runnable as delivered.** Right shebang and mode bit, config parses, links
  resolve, and any command you put in a README is one you ran.
- **Clean up after the checks too.** Running tests or a build leaves its own
  droppings - `__pycache__`, `.pytest_cache`, `.ruff_cache`, `dist/`, coverage
  files. Observed on a real run: the work was clean and both cache
  directories were left in the project. If it is not part of the deliverable,
  delete it or confirm the project already ignores it, and say which you did.
  In a Ralph loop, keep whatever its recorded verification command needs.

Before reporting, check it against the list of files rather than from memory:

```bash
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git status --porcelain
rg -n --glob '!.pi' 'TODO|FIXME|XXX|lorem ipsum|console\.log|debugger|your-name-here' .
rg -n --glob '!.git' --glob '!.pi' "$HOME|/var/folders/|/tmp/" .
```

## Scratch files stay in the working directory

Anything you create while working - a throwaway script that produces no reported
result, intermediate output, a downloaded file, a log you are about to grep -
goes **under the directory the session was launched in**, not in `/tmp` or the
system temp directory. Use `.pi/tmp/` for scratch that is not part of the
deliverable, and create it if it is not there. A script whose output you report
is a deliverable: keep it in the working directory, not in `.pi/tmp/`.

Three reasons, in order of how soon they bite:

1. **The permission gate stops you.** A write outside the launch directory
   resolves to `ask`. A sub-agent's ask waits on the user's prompt in the parent
   session, and in print mode or an unattended loop it is refused. Writing to
   `.pi/tmp/` needs no permission at all.
2. **You can find it again.** A later iteration, a sub-agent, or the person
   reading the result can see what you produced. Work in the system temp
   directory is invisible and effectively gone.
3. **It cleans up with the project.** One directory to inspect, one to delete.

`/tmp` is for the genuinely necessary case - a file too large to want inside the
project, or a tool that will not be told where to write. Say in the report that
you used it and why.
