# Installing elm-pi on a new machine or host

Verified on macOS 15.8 (Intel) and written to work unchanged on Apple Silicon and
Linux x64/arm64; the Linux distributions tested are under
[Linux distributions](#linux-distributions). Requires: `curl`, `tar`, and an ELM API key. `git` is
optional — the installer falls back to a source tarball without it. Python 3.8+
is used when the system has one (never conda, a virtualenv or pyenv); otherwise
the installer downloads a standalone CPython into the install.

---

## The short version

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

That is `install.sh`: it checks the machine, fetches this repository to
`~/.local/share/elm-pi`, runs `bootstrap.sh`, and links `~/.local/bin/pi`.
Use the `bash -c "$(curl ...)"` form rather than `curl | bash` — piping replaces
stdin, and bootstrap would not be able to prompt you for the key.

If the directory is already on the host (git clone, `scp -r`, tar):

```bash
cd ~/.local/share/elm-pi
./bootstrap.sh
```

The source checkout must travel as a unit: the launch scripts, `config/`, `lib/`,
`scripts/`, `templates/`, shim, proxy and docs are all used by install
or validation. Installed software and runtime state are downloaded or generated.
`.gitignore` already excludes the key, the installed software and all runtime
state, so the repository is safe to push.

Bootstrap installs Node into `.node/`, pi into `node_modules/`, the pi packages
into `agent/npm/`, generates `agent/` from `templates/`, asks for your ELM key,
resolves the model id from the gateway, smoke-tests a completion, and verifies
the ELM-only policy, and builds the agent's Python. About 2.0 GB on disk - 1.0 GB
of it the agent's Python, which `--no-python` leaves out - and 5 minutes on a
warm network; `--with-all` adds the offline PyPI index (~0.4 GB, after a ~1 GB
download it deletes) - ~2.4 GB in all. A new install
says this before it downloads anything, and stops there if the filesystem has
too little room (`ELM_PI_IGNORE_DISK_SPACE=1` goes ahead anyway); so does an
existing install that gains an optional part. `install.sh` syntax-checks the
source it downloads; `ELM_PI_RUN_TESTS=1` runs the whole test suite on it
first as well, a few minutes more.

Unattended:

```bash
ELM_API_KEY=elm-... ./bootstrap.sh --non-interactive
# or, from scratch:
ELM_API_KEY=elm-... /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

Re-running either is safe: neither overwrites `.env`, sessions, or a config
you have edited, and both repeat the options the install was made with (below).
A re-run installs the tested versions in `config/versions.json` when a pull has
changed them, and otherwise leaves pi and the packages alone. `pi update`
fetches and validates current source, then installs the latest pi and packages
while keeping configs; `pi update --extensions` goes back to the tested set.

Installer knobs, if the defaults do not suit:

| Variable | Default |
|---|---|
| `ELM_PI_PREFIX` | `~/.local/share/elm-pi` — where the install lives |
| `ELM_PI_BINDIR` | `~/.local/bin` — where `pi` is linked |
| `ELM_PI_BRANCH` | the branch the install was made from (`agent/install-options`), else `main` |
| `ELM_PI_REPO` | the repository the install was made from, else `rob-c/elm-pi` on GitHub |
| `ELM_PI_UPDATE` | `0`; `1` passes `--update` through to bootstrap |

To remove everything: `rm -rf ~/.local/share/elm-pi ~/.local/bin/pi`.

---

## Linux distributions

Installed and run in containers on 2026-11-12. Each started from the
distribution's own image with only `curl`, `tar`, `python3` and `git` added, then
ran the real `install.sh` and a `pi --auto -p` session against a stand-in gateway.
In that session the model called `bash`, and the command ran:

| Distribution | Python the install uses | Not installed |
|---|---|---|
| Ubuntu 24.04, 26.04 | the system's (3.12, 3.14) | |
| AlmaLinux 8 | a standalone 3.12: the system's is 3.6 | `resvg` |
| AlmaLinux 9 | the system's (3.9) | `resvg` |
| AlmaLinux 10 | the system's (3.12) | |
| Arch Linux | the system's (3.14) | |
| NixOS, with nix-ld | Nix's `python3` on `PATH` | |

All ran on arm64 except Arch, which ran on x86_64 under emulation. `resvg`, used
to render SVG, is built against glibc 2.35. RHEL 8 and 9 and their rebuilds have
an older glibc, so bootstrap skips it with a warning; everything else works.
`xz` and `unzip` are not needed: a tool archive that `tar` cannot open is
unpacked with Python's own `tarfile` and `zipfile`.

**NixOS** needs two changes:

- **Start the installer with `bash`, not `/bin/bash`.** NixOS has no
  `/bin/bash`:
  `bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"`.
- **Turn on nix-ld.** Node, the standalone Python and the command-line tools
  are built for an ordinary glibc system, and look for its loader at
  `/lib64/ld-linux-x86-64.so.2` (or `/lib/ld-linux-aarch64.so.1`). Add
  `programs.nix-ld.enable = true;` to `/etc/nixos/configuration.nix`, run
  `sudo nixos-rebuild switch`, then log out and back in, which sets `NIX_LD`.
  nix-ld's default libraries are enough. Without it, the installer stops before
  downloading anything and says this.

**Not supported:**

- **musl systems** such as Alpine: the installer stops with that loader message.
- **FreeBSD**: `install.sh` stops at "unsupported OS". nodejs.org publishes no
  FreeBSD Node, and most of the bundled tools have no FreeBSD build. It could not
  be tried here either: Docker Desktop runs a Linux VM, and FreeBSD's own
  container images (`freebsd/freebsd-runtime`) need a FreeBSD host. On this one
  they exit with a segmentation fault.

---

## Step 1 — Get an ELM API key

Keys are **issued on request, not self-service**. In the ELM web UI, submit the
API-key request form describing your use case; it goes to an approval queue.

Check status from the browser console on an ELM tab (⌥⌘I → Console):

```js
await (await fetch("/api/elm-key-requests?page=0&size=20", {credentials:"include"})).json()
```

Look for `"status": "KEY_ISSUED"`; the key is in `elmKeyValue`, with an
`expiryDate` (12 months, typically). Keys look like `elm-xxxxxxxx-xxxxxxxxxxxxxxxx`.

**Check before you request** — you may already have one issued.

Two things people get wrong:

- `/api/key-requests` (no `elm-` prefix) is a *different, older* queue that issues
  raw OpenAI `sk-...` keys hitting OpenAI directly. Not what you want.
- ELM has two APIs. `/api/*` is the web app's cookie-authenticated backend;
  `/api/v1/*` is the OpenAI-compatible gateway and accepts **only**
  `Authorization: Bearer <key>`. Being logged in to ELM in your browser buys you
  nothing at the API level.

---

## Step 2 — Run bootstrap

```bash
./bootstrap.sh
```

| Flag | |
|---|---|
| `--non-interactive` | take the key from `$ELM_API_KEY`, never prompt |
| `--update` | the latest pi and extension packages, kept only if the checks pass; keep configs (what `pi update` runs) |
| `--force-packages` | reinstall the extension packages at the tested versions, and pi too if it is not at its tested version (what `pi update --extensions` runs) |
| `--no-packages` | pi only: no sub-agents, web access or anchor editing |
| `--no-tools` | do not bundle fd, rg, jq, yq, shellcheck, ast-grep, uv, mlr, resvg, pixi and ruff (and so no agent Python either) |
| `--no-python` | leave out the agent's own Python environment, `agent/python` (~1 GB), which every install has otherwise - and the index with it; removes them from an install that has them; also `pi setup --no-python` |
| `--with-python` | take `--no-python` back; also `pi setup --python` |
| `--with-pypi-index` | build an offline search index of PyPI for the agent (`pypi-search`); downloads ~1 GB once, keeps ~390 MB; implies `--with-python`; also `pi setup --pypi-index` |
| `--with-all` | every optional part: `--with-python` and `--with-pypi-index` (recorded as those two). Nothing that opens the network - that is `pi --remote`, per run. Also `pi setup --all`, and `pi --with-all` sets it up on first use |
| `--no-pypi-index` | take the index back, removing it |
| `--no-shim` | no Llama tool-call shim (Qwen unaffected) |
| `--no-auth-lock` | leave `agent/auth.json` writable, so `/login` works |
| `--no-patch` | leave pi's `/share` and `/bug` commands in place |
| `--force` | re-download the tools and reinstall pi and the npm packages, at the tested versions |
| `--reset-options` | forget the options earlier runs recorded, and use only this run's |
| `-h`, `--help` | the flag list, which now lives in one place in the script |

**The options are remembered.** The `--no-*` flags and `ELM_PI_TOOLS` are
written to `agent/install-options`, together with the branch and repository
`install.sh` fetched, and every later run repeats them: re-running the
installer or `./bootstrap.sh`, `pi update` and `pi update --extensions`. An
update therefore keeps the install you chose rather than reinstalling what you
declined, or re-locking `auth.json` after `--no-auth-lock`. A flag given on a
later run is added to the record. To take one back, start the record again
with only the flags you want:

```bash
./bootstrap.sh --reset-options --no-shim     # now: everything except the shim
```

`install.sh` accepts `--reset-options` and passes it through. An install made
before the record existed has its flags inferred from what they left behind,
except `--no-patch` and a tool subset.

`pi --remote` is the flag for work that needs the web. It is on the launcher,
not the installer, so it is a decision per run rather than per host:

```bash
pi --remote                 # web tools on, egress proxy recording not gating
pi --remote --fast -p "..." # open proxy, but --fast loads no web tools
```

It lifts exactly two things — the web tools come back on, and the egress proxy
stops allowing only the ELM gateway and the package sources (PyPI,
conda-forge, container registries) — and adds one: computer use
(`@injaneity/pi-computer-use`), which lets the agent see the screen and drive
apps and browsers through the accessibility API. It loads in that session
only, never in its sub-agents; on macOS the first use asks for Accessibility
and Screen Recording for its helper, which lives in `agent/helpers/`. **The model policy is untouched**: the
credential scrub, the argument guard and the catalogue strip all stay, so
inference still goes to ELM, no other provider becomes reachable or visible,
and Qwen is still the model. Telemetry and the version check stay off, as they
are in every mode. Every destination the run reaches is recorded in
`agent/egress.log`.

Narrower options, when you know where you are going:

```bash
ELM_PI_PROXY_ALLOW=api.exa.ai pi    # one extra host, nothing else
PI_ELM_WEB=1 pi                     # tools on, proxy unchanged (they will fail)
```

Whatever these flags decide, `agent/settings.json`'s `packages` list is written
to match on every run. It is copied from `templates/settings.json` (emptied by
`--no-packages`), not edited in place — editing in place could only ever
remove, so an install that had once been run with `--no-packages` kept an empty
list for ever after, installed the package set on the next run and then loaded
none of them. A package added to the list by hand is named and removed.
Everything else in that file is yours and is left alone. A package that is
listed but missing or incomplete in `agent/npm/node_modules` is reinstalled,
and the install stops if it is still incomplete, because at runtime it is
silent: pi starts offline, so it does not fetch it either.

---

## What bootstrap does, and the manual equivalent

Useful when a step fails, or when a host needs something done differently.

### 1. Node, bundled

pi needs Node ≥ 22.19. The official prebuilt tarball is extracted into `.node/`,
after a SHA-256 check against `SHASUMS256.txt`.

> **Do not `brew install node` on an Intel Mac.** There is no bottle for that
> combination any more, so Homebrew compiles V8 from source — over an hour.

```bash
V=v24.21.0; ARCH=x64        # arm64 on Apple Silicon
TAR=node-$V-darwin-$ARCH.tar.gz
curl -fsSL -o "/tmp/$TAR" "https://nodejs.org/dist/$V/$TAR"
curl -fsSL -o /tmp/SHASUMS256.txt "https://nodejs.org/dist/$V/SHASUMS256.txt"
grep " $TAR\$" /tmp/SHASUMS256.txt | shasum -a 256 -c -   # must say OK
mkdir -p .node && tar -xzf "/tmp/$TAR" -C .node --strip-components=1
```

### 2. pi

`package.json` asks for `latest`; `config/versions.json` holds the version this
repo last tested, which every install but `--update` takes (see CONTRIBUTING.md).
`--force-packages` also brings pi back to that version when `pi update` moved it
on, since the packages were tested against it.
Bootstrap runs `npm install --omit=dev --ignore-scripts` in a sibling staging
directory, patches and starts the staged CLI, then swaps its `node_modules` into
place. The tree it replaced is kept until the end of the run and put back if
anything after the swap fails.
The prebuilt pi bundle does not need dependency install scripts.

### 3. `agent/` from `templates/`

`PI_CODING_AGENT_DIR=./agent` (set by the launcher) is what keeps this deployment
self-contained — without it pi writes to `~/.pi/agent` and collides with any other
pi install.

| Generated file | Purpose |
|---|---|
| `agent/models.json` | the ELM provider: base URL, `$ELM_API_KEY`, Qwen and Mistral (Llama is the shim's) |
| `agent/settings.json` | defaults, packages, extensions, retry, `sessionDir` |
| `agent/AGENTS.md` | loaded by every top-level session: delegation policy, model choice, the short form of every working rule. Sub-agents do not see it (nor `APPEND_SYSTEM.md`); their rules are in `agent/agents/*.md` |
| `agent/reference/` | the detail behind the short rules in AGENTS.md and APPEND_SYSTEM.md (finished work, `.pi` and git, project memory, anchor editing, the egress proxy, reporting, asking, fits and figures, the ELM service), read by the model when the situation comes up rather than sent with every request |
| `agent/extensions/elm-only.ts` | the ELM-only policy — always refreshed |
| `agent/extensions/elm-shim.ts` | registers the Llama tool-shim provider |
| `agent/extensions/protected-paths.ts` | blocks writes to `.env`, `.git/`, `node_modules/` It also refuses writes into the elm-pi install the session runs on - its guards, launcher and configuration - outside `.pi` folders: elm-pi is developed in a clone (the repository's AGENTS.md, `scripts/dev-setup.sh`), and an install changes through `pi update`. |
| `agent/extensions/trust-guard.ts` | never grants project trust to home, the filesystem root or a folder that holds credentials (`untrustedFolders` in `config/elm-pi.json`), and does not let a saved "Trust parent folder" there pass down to the folders beneath (see [LOCKDOWN.md](LOCKDOWN.md)) |
| `agent/extensions/command-guard.ts` | refuses a `bash` command the permission gate's rules deny when it is spelled so they miss it: quoted or escaped (`'ssh' host`), by full path, after `sudo`, `env`, `xargs`, `command` or `exec`, inside `bash -c`, or with extra whitespace (see [LOCKDOWN.md](LOCKDOWN.md)); and a `python -m http.server` not bound to `127.0.0.1`, which would serve the folder to the whole network The same for the shell: a command that would change the running install - `rm`, `mv`, `touch`, `sed -i` and the like on its files, `cp`/`rsync`/`ln` into it, a redirection, or `git` changing its tree - is refused; reading or copying out of it is not. In sub-agents, direct creation or destructive cleanup of the shared `.pi/tmp/venv` is refused, as is removing `.pi/tmp` itself; the refusal gives a `mktemp` command for private scratch. Existing shared environments may still be used to run tests, and the parent may prepare them. This narrow rule follows two parallel Qwen runs that chose the same virtualenv despite unique-scratch instructions; in the first, one child deleted it while its sibling was still using it. |
| `agent/extensions/claim-guard.ts` | sends Mistral or Llama back, once, when a run made no tool call but its reply says something was added, changed or run - and Qwen too when it is a sub-agent, where a test5 child reported "Created new file" having made no call (see [Mistral Small 4](#mistral-small-4-the-other-model-with-tools-and-images)) A run counts as making no call when none of its calls succeeded: test13's workflow agent had every write refused and reported "The stylesheet file has been created". In a sub-agent, a tool call made earlier in its session backs a later reply, and no session is sent the note more than twice: a child retried after a 429 was otherwise sent it 189 times in 16 minutes. |
| `agent/extensions/repeat-guard.ts` | stops a run that makes the same failing tool call over and over: at 3 identical failing turns in a row it tells the model so, at 8 it ends the run, so a sub-agent stuck that way ends and reports instead of looping to its 30-minute timeout (see [Sub-agent fan-out](#sub-agent-fan-out)) A sub-agent also has a budget of turns for its whole session: told once at 30 to finish and report what is left, stopped at 60. Two children in one driven session took 140 and 98 turns of small edits - 21M of that session's 26M tokens - with nothing failing for the other rule to count; children that wrote a page took 3 to 32. |
| `agent/extensions/image-mentions.ts` | attaches the images a message names by path (`figures/fit.png`, a Desktop screenshot's path with spaces, a path dropped into the terminal) to that message, as a pasted image is, for a model that sees images; sub-agent tasks too. Hidden folders are skipped; at most 8 images, 20 MB each; only files whose first bytes are a PNG, JPEG, GIF or WebP (the gateway refuses a request holding anything else) |
| `agent/extensions/owner-guard.ts` | a file a running child's task says to make is that child's. A task's files are its outputs - the paths it says to create, write, save, edit or fix - not every path it mentions ("links to: index.html, about.html", "use the shared styles.css"): in test7 every task listed all five pages for its navigation bar, and the first version, which counted mentions, let a child rewrite a finished sibling page. In a sub-agent: its first turn names its siblings' files and says not to wait or poll for them, a change to one is refused, and `write` over a file someone else changed after it started, unread, is refused. In the parent: a change to a running child's file is refused until that child's completion notice or the run's end. Each forked child records what it wrote and was refused, and the parent's first turn after the run ends starts with that list (under `pi -p`, `bg_wait`'s result ends with it), so it reports who did what from the record, not the children's reports (that turn is started by the run's notice, which pi adds to the session only after the turn's start: test8 and test9 never got the list until the guard read it from the event). Replayed through this guard, test6's nine overwrites and the parent's seven edits, and test7's rewrite and three edits of siblings' pages, are refused, and every child's own page goes through. Bash is not checked. It also refuses to start children side by side when what they share is not there yet: a non-page file two tasks name that does not exist (test9's `css/style.css`, one child's job while four built on it), or, for tasks that make pages or documents, a shared stylesheet, navigation or footer they are told to use with no existing file named to take it from (test6, test8). Replayed: test6, test8 and test9's launches are refused, test7's, whose parent wrote the stylesheet first, goes through. A task that is to start after the others (test12: "COORDINATOR TASK: After the other 4 agents complete their pages") is refused too: tasks started side by side start together. Chains and single children are not checked. A child that is one of several and was told to make a page or document creates only the files its task names, files in a folder its task names ("images/"), and scratch (a hidden folder, or the temp folder outside the project): in test10 three page children took on the user's "download images" and wrote twelve placeholder drawings, two over each other's, into a folder only the gallery's task named. Replayed, those twelve writes and test6's and test7's unasked stylesheet and README are refused and every child's own page goes through. A child writing code is not limited this way A shared file named one folder up that is there without the `../` gets that said, not "write it first" (test14: `../css/style.css` from pages beside `css/style.css`). Tasks told to take their styling, navigation or footer from a page a sibling is writing ("Match the exact CSS classes ... from index.html", in a driven session on 2026-11-13) are refused at launch, as is the shared ask said noun-first ("footer consistent with other pages"); a menu that only links the other pages is not copying them. A launch that tells a child other than `researcher` to search the web is refused too: a `qwen` child has no web tools, and one told to "use web_search" ran 32 turns from memory (2026-11-13). In a session without web access, a task telling a child to download from the web is refused at launch too. With the web, a launch whose tasks have two or more children each downloading pictures is refused too: fetched at once they get rate-limited and repeat each other's searches; one place fetches, then the pages are launched. A relative file a task names counts as there when it is in a folder the task names too ("the website at /…/red-squirrel-website/" and `images/…`): without that, a launch was refused three times over pictures already downloaded, and the parent wrote every page itself. |
| `agent/extensions/server-reaper.ts` | stops, when the session ends, a web or dev server (`python3 -m http.server`, `npx serve`, `vite`, `flask run` and the like) that a bash command started in the background: the new listening port is recorded with its process group, and the command's result gives the user-visible `127.0.0.1:$ELM_PI_PREVIEW_PORT` URL or explains that a Linux server chose an unbridged port. At quit (or the end of `pi -p`, a new or resumed session, a sub-agent finishing) it gets SIGTERM, with a line on stderr. `view` can still render an HTML file without a server. test4, test5 and test7 each left one running. Other background jobs are left alone |
| `agent/extensions/report-guard.ts` | refuses creating a new README, SUMMARY, REPORT, NOTES, *_VERIFICATION or similar Markdown file unless the request asks for one (a user message, or a sub-agent's task, that names the file or says readme, report, summary, notes, document, docs or write-up): a report goes in the reply. test6 and test7 wrote a README and a link-verification report unasked, after AGENTS.md said not to. Editing an existing file and anything under `.pi/` are never refused; checks `write` and bash redirects "Report" alone does not count as asking for one - "Report: the files you wrote" asks for a reply - so it takes "a report", "write a summary", a named file, readme, docs or a write-up. A `subagent` launch or `workflow` script that tells an agent to write a report-like file the user did not ask for, and that is not already in the project, is not started (test11: a workflow told its verification agent to write VERIFICATION_REPORT.md). A README beside a software project's manifest (`pyproject.toml`, `package.json`, `Cargo.toml` and the like) is part of the project, not a report, and is not refused: one was, in a session asked for "a proper package layout" (2026-11-13). |
| `agent/extensions/date-note.ts` | adds today's date (this machine's time zone) to the system prompt as a section of its own. pi gives none, and test7's pages all said "© 2024". The first version returned a whole replacement prompt, which pi sends instead of the sections, so the sections of extensions loaded after it (pinned instructions, `--remote`'s research instruction) never reached the model; a test now refuses any extension that does that |
| `agent/extensions/wait-guard.ts` | refuses `bg_wait` in an interactive session, where a sub-agent run wakes the session when it ends: the model is told to end its turn instead of holding the session (it did for 6.5 minutes in test5, after the prompt already said not to). `pi -p` and sub-agents keep it. Once refused in a turn, the other ways of waiting are refused for the rest of it (test9 then ran `sleep 5`, `sleep 10`, two status checks and read the run's log): a bash command that only sleeps, a `subagent` status check, and reading a run's files under async-subagent-runs Refused, it was still called four times in a row (2026-11-13), so the launcher no longer offers `bg_wait` to a session its runs wake - only to `pi -p`, `--mode json`, `--with-all` and sub-agent children - and here a second `subagent` status check in one turn is the refused wait. A successful async launch also arms sleep/poll detection immediately: in python-before parallel.1 (2026-11-15), calls to the wrong status tools never armed it, so the parent kept sleeping and changing files its children were still writing. A command that reads a running run's own files under `async-subagent-runs/` is refused from the first time: a manual session read its child's log again and again, each read put to the user to allow. Told twice, a third refused wait in one turn is held inside the guard - until a sub-agent's notice is queued, or two minutes - before it is answered: the wait the model wanted, with no model request spent on it (a parent was refused eight times in 45 s). It is never ended with an abort: that was tried, and pi-subagents, which takes any abort for the user pressing Esc, stopped waking the session - in three driven sessions of three the children finished and the site was never checked. The same shell command three times running, with no other call between, is a wait too: a parent ran one `ls` of its site 91 times while its children wrote the pages - 195 turns, 8M tokens, and in manual mode an ask for each. It also takes `contact_supervisor`, a sub-agent's tool, out of the top session's tools: two of four driven sessions called it there and got an error. |
| `agent/extensions/ultracode-note.ts` | in a session without the `workflow` tool, replaces the note `/ultracode` and `/effort` add to each message (call the `workflow` tool, fan out widely) with one line saying the tool is not here and to fan out with `subagent` instead (see [Dynamic Workflows](#dynamic-workflows-and-the-one-control-it-lacks)) |
| `agent/extensions/permission-mode.ts` | `/mode`: a menu to change the permission mode (manual, read-only-auto, auto, yolo) and keeps it in the footer; the permission gate, patched by `patch-pi.py --gate`, applies it (see [Permission modes](#permission-modes)) In manual mode a system-prompt section says `read`, `grep`, `find`, `ls` and `view` never ask, so looking is not put to the user through bash (a manual session put 31 dialogs to its user in 16 minutes, seven of them `ls`, `grep` and `cat`). |
| `agent/extensions/todo.ts` | adds a `todo` tool for multi-step work, and keeps the list **on screen**: a live panel above the editor showing `plan 2/5` and the items, capped at five terminal rows with a count of the rest, repainted when the list changes and after a resume (the list otherwise lives in scrollback and is lost at the next tool result - the plan's item 12). Long items are clipped to the current terminal width and multiline items are displayed on one row; the full text stays in the list. Nothing of the panel is sent to the model |
| `agent/extensions/remote-research.ts` | in a `pi --remote` session (and its sub-agents) only, which the launcher marks with `PI_ELM_REMOTE=1`: a system-prompt section telling the model to ALWAYS research with the web tools, cite what it used, and say what it could not confirm, rather than answer from memory. It also says that what the model writes for the user (pages, reports) is facts to look up too - before handing the writing to a `qwen` child, which has no web tools - with one number for one fact across pages, and that pictures of a real thing are real ones from the web (Wikimedia Commons, by `Special:FilePath`), looked at and credited on the page - test9 wrote an alpaca site from memory with seven random picsum.photos images. With computer use on as well (`PI_ELM_COMPUTER_USE=1`, the top-level session only: a sub-agent child inherits the variable but has no computer use, so in a child (`PI_SUBAGENT_CHILD`) the section is taken out - which reaches a child started fresh; a forked child is sent its parent's system prompt unchanged by pi-subagents, to reuse the parent's prompt cache, so it still reads the section, with no tools to act on it), a second one for driving Safari: Safari is for the web, and a page or figure on this machine is looked at with `view` (a live run checked its pages through Safari's accessibility outline and never saw them); press Return after typing a URL, and when finished minimise the window and bring the terminal back to the front Under `--remote` it also refuses a download of a Commons file name - `Special:FilePath/<name>` or an `upload.wikimedia.org` path - that no search result, message or task in the session has shown: a child guessed eleven, each a 404, before searching (2026-11-13). Without `--remote`, a request to download something from the web gets a note right after it: this session cannot reach the web, say so in the first reply with `pi --remote` as the way, and call any stand-in a stand-in (2026-11-13: 21 labelled yellow boxes were reported as "downloaded/generated"). Its refusal of a guessed name runs Commons' search for what the guess was after and lists the exact titles it finds, which then count as seen (a session was refused five times in a row, guessing anew each time); its example search encodes the words with `--data-urlencode`, since one with raw spaces broke. Spaces in a quoted `Special:FilePath` URL are written as `%20` before the command runs: curl refuses them ("URL rejected: Malformed input"), twice in driven sessions. |
| `agent/extensions/pinned-instructions.ts` | `pin_instruction`: standing instructions kept in the system prompt, where compaction cannot summarise them away |
| `agent/extensions/skill-router.ts` | adds the skills a request needs (see [Skills](#skills-and-the-skill-router)) A request for agents in a session that has none (`pi --fast`) gets one note saying so: one called `subagent` and `workflow`, was told each was not found, and built the site alone without a word. |
| `agent/extensions/view-outputs.ts` | shows Qwen its figures: image and PDF files a command writes are attached to its result, `view` renders PDF pages (with their text) and TIFF/BMP, and an HTML page as a browser draws it (headless Chrome or Chromium, through the egress proxy, else Quick Look; only when asked, never for pages a command writes), and a PDF given to `read` is rendered. Uses the bundled `mupdf` (WebAssembly; nothing downloaded at run time). SVG, EPS/PS, HEIC and PSD go through a command-line converter first (rsvg-convert, Inkscape, ImageMagick, Ghostscript, epstopdf; sips and qlmanage on macOS) when the machine has one. A page's view also says which files it asks for are missing, which pages it links to do not exist, which remote hosts the egress proxy refused (from its log, during that render), and when a host serves placeholder pictures - test7's gallery drew six refused picsum.photos images as broken and was called "Perfect!". `paths` shows up to six files together with a request to list every difference; a URL is answered with "view its .html file". A file the stylesheet asks for is named once as the stylesheet's, not as every page's. Each `view` of a page also compares what every page in its folder repeats - header, navigation, footer, copyright year, stylesheets - and names each difference, and a stylesheet or script no page loads (test8 and test9 were shown their pages, told to list the differences, and called four footers and a "© 2024" among "© 2026"s consistent). An image is attached only when its first bytes are one and a PNG or JPEG is whole: test9 saved seven "error code: 522" replies as .jpg, and attaching them made the gateway refuse that request and every later one with 400 "cannot identify image file". Such files are reported for what they hold, and any image already in a session that is not one is left out of its requests. A page that draws a local "image" that is not one (test10's saved "Wikimedia Error" page) says so. The site comparison also names stylesheets, scripts and pictures no page uses and pages no page links to (test10 left seven unused files and its scaffold template.html in the site), and views called together in one turn no longer tell each other the comparison was "given before". The header compared is the site's - the first `<header>` holding the navigation or a link home - not a page's own title banner (test11 was told "5 versions" of those). And a final reply that calls the pages consistent over this run's last comparison listing differences, or a page fine over its last view reporting something broken, is sent back once before the run settles with what the view said (the closing replies of test8, test10, test11 and test13 each did that; `tests/test_session_regressions.py` replays them). A command fetching from a placeholder host (picsum.photos and the like) is told those are arbitrary pictures. Headless Chrome's own calls to Google (updates, sign-in, safe browsing - eleven per render) are sent to a closed port by a proxy auto-config script, so they neither fill the egress log nor, under `--remote`, reach Google; the page's own hosts still go through the egress proxy Pictures a page loads from another site - an `<img>`, or one an `onerror` handler swaps in - are named as not local (test14 gave four missing pictures `onerror` stand-ins from via.placeholder.com; test15 had one page on Unsplash), and the "list every difference" note comes only with two or more pages, not photos (test15). Pages a run changes and never views - by its own tools, a sub-agent or a workflow agent - are checked at its end when the reply calls them consistent or fine: compared across their folder, and each page's missing and broken files (2026-11-13: five pages with three footers, viewed by nobody; six pages with fourteen missing pictures, called "100% Self-Consistency Verified"). A picture is attached only if MuPDF decodes it, and before each request every image in the conversation is decoded once and one that does not decode is left out: a session wrote eleven 129-byte "JPEGs" - a JFIF header and nothing more - and the gateway's "400 Failed to load image" ended it (2026-11-13). A download or unpacking command that adds over 100 MB or 2,000 files to the project gets a note saying how much, where, and to keep only what the work uses (a frog website's agents left a 410 MB image dataset and two cloned repositories in the folder, 2026-11-13). The end-of-run check looks at pages changed since the user last asked, not since the run began: the run that ends a delegated job starts after the sub-agents have written every page, and a site whose stylesheet asked for a missing picture was called "100% self-consistent ... Verified" unanswered. In a sub-agent the check answers only for that agent's own page: differences between pages, and links to pages its siblings have yet to write, are the launching session's to compare once they are all there. Over six batches 45 of 210 sub-agents were sent back for them, 19 for more than 20 turns. A page that draws a file from `.pi/` is told so ("Kept in scratch"): it shows on this machine and nowhere the site is copied to - one site's eight pictures were all there, and the reply said its image paths were validated. |
| `agent/extensions/install-notes.ts` | when the agent installs something (pip, pixi, docker pull, brew), adds what, where it lives and how to remove it to that command's result for the report, and logs it in `agent/installs.log` |
| `agent/shell/colour.sh` | sourced before every `bash` command (`shellCommandPrefix` in `settings.json`): `git` (diff, show, log, status, branch, grep, blame, shortlog, range-diff, reflog), `ls`, `grep`, `rg`, `fd`, `diff` (comparing folders, the colour option it adds is taken back out of the header diff prints for each pair of files), `jq`, `tree`, `shellcheck`, `pytest`, `python -m pytest` and `ruff` colour their output when it goes straight back to pi, and stay plain in a pipe, a redirect or `$(...)`, as they would in a terminal. They are shell functions, so scripts a command runs do not see them; `NO_COLOR=1` turns them off |
| `agent/extensions/command-output.ts` | gives the model a command's output without escape codes or progress-bar redraws (pi passes them on as printed). The model's copy is the text the command gives without colour: tabs and control bytes are kept, and a long output is cut at the lines pi would have kept without colour, since pi counts colour codes towards its 50KB limit. It also draws a finished `bash` result for people: a coloured exit line (`✓ exit 0 · 1.2s · 40 lines`), the first 4 and last 12 lines with a count of the error and warning lines hidden between them, the command's own colour when it printed any (see `colour.sh` above; kept in the result's `details`, which the provider never sends) and otherwise colour by kind of line (errors, warnings, passes, diffs, `file:line`). Ctrl+O shows everything |
| `agent/extensions/workflow-model-scope.ts` | keeps Dynamic Workflows agents on ELM models |
| `agent/extensions/workflow-script.ts` | lets a `workflow` call name its checked script file - `workflow({ script: ".pi/tmp/<name>.mjs" })` - and runs that file, so what runs is what `workflow-check` passed and the script is not typed twice (test15, 2026-11-13: the model retyped a checked script, and the copy did not parse). Refuses a script whose prompts name a text constant that nothing uses - test15's page tasks said "copy sharedStyles verbatim" and none of them held the CSS - and adds the line a syntax error's "(176:11)" points at. `permission-mode.ts` and `report-guard.ts` read a named file too, as pi loads a folder's extensions in no set order. |
| `agent/extensions/notebook-outputs.ts` | `notebook_summary` shows an output's first five lines; when one is cut, a note says which cells and how to read one whole with `notebook_read_cell_output`, and a read that names a markdown cell gets the notebook's code cells. In a decay-chain notebook the peak-activity table was cut after two rows, both reads named markdown cells, and the reply gave a peak time that was in no output (23.65 min; the notebook said 38.32). |
| `agent/extensions/verify-guard.ts` | sends a turn back, once and at most twice a session, when it wrote a code file and ran nothing in that turn: in the ten-session, 200-problem treadmill batch of 2026-11-14 (`docs/tuning/README.md`), two sessions wrote all twenty files and executed none, replying "Done." twenty times - 40 and 41 requests against the other eight sessions' 60-63. A written file is not a known-working one, and `claim-guard` cannot catch this because the writes succeeded. Any executing call counts whether it failed or not - `bash`, a python tool, a notebook run, a sub-agent launch - and only files whose extension can be executed count, so writing a README, a config or a `.csv` is not this guard's business |
| `agent/extensions/help.ts` | `/help`: this session's commands, its skill commands and the tools offered to the model - read from `pi.getCommands()` and `pi.getActiveTools()`, with descriptions from `pi.getAllTools()`, so removed templates and disabled tools are not listed. `/help <word>` filters commands and tools on name and description. Costs no model turn and no tokens until typed; it is the reflex first command a first session did not have |
| `agent/extensions/empty-state.ts` | on a new session, with a screen, three lines naming `/help`, the prompt templates this install actually has in `agent/prompts`, and where `INSTALL.md` and `agent/reference` are. Nothing on a resumed or forked session, including one resumed from the command line, nothing in `pi -p` (there is no screen), and nothing it cannot check: the template names are read from the directory pi loads them from |
| `agent/extensions/status-line.ts` | one footer line naming the model when it is not the install's default and `web` when the session has `web_search` (which is what `pi --remote` buys), and nothing at all for the ordinary session. It refreshes immediately when a model is selected and at each turn. Both change what a whole session can do and neither shows after launch: a `--remote` session's 403 is how a gateway gets blamed for a proxy |
| `agent/extensions/network.ts` | `/network`: shows what this session may reach - offline, trusted-remote or yolo - and changes it, in a menu like `/mode`'s (`/network offline` goes straight to the second one; `default` names trusted-remote). A tighter mode can be taken for this session, or for this session and new ones: the proxy is told to keep only the shorter list and, for offline, the web tools are switched off. A looser one can only be made the default for new sessions (`agent/network-mode`), because a running session cannot be opened up: the OS fence cannot be taken off a process already inside it, and the proxy takes a narrower list from anyone but a wider one from nobody. The menu gives the command that starts again in the wider mode and continues the conversation. It keeps the mode in the footer, and says once, inside pi, when the session is running without its fence because this machine could not make one. Asked for on 2026-11-16, to sit beside `/mode`. |
| `agent/extensions/subagent/config.json` | fan-out budget: 12 concurrent, 64 per run |
| `agent/bin/pi` | symlink to the launcher, so sub-agent children find `pi` whatever PATH looks like |
| `agent/pixi/` | pixi's global tools, environments and cache (`PIXI_HOME`), when the agent has used it |
| `agent/python/` | unless `--no-python`: the agent's Python - uv-managed CPython, `env/` (the venv on PATH), uv's cache |
| `agent/helpers/` | the computer-use helper, created on first use in a `pi --remote` session |
| `agent/web-search.json` | DuckDuckGo then Exa; `unpdf` for PDFs |
| `agent/install-options` | the options this install was made with, repeated by later runs |
| `agent/installed-versions.json` | the exact pi and package versions installed, written after the checks pass |

`agent/` is generated. Put durable changes in `templates/`, commit them, and run
`pi update` on each host so the validated source reaches it.

### 4. pi packages

pi resolves `npm:<name>` from `agent/npm/node_modules`. Bootstrap installs
`templates/packages.json` with `npm install --ignore-scripts` in a staging
directory, at the versions in `config/versions.json`, and swaps the tree into
place once every listed package is present. No package install script runs.

The set is sixteen packages (computer use loads only with `pi --remote`); `templates/packages.json` is the list. The ones
that shape the agent most:

| Package | |
|---|---|
| `pi-subagents` | sub-agent fan-out (`subagent`, `bg_wait`, `subagent_supervisor`) |
| `pi-hashline-edit-pro` | anchor-based editing: its own `read` and `grep` (with 5-letter line anchors), `replace`, `replace_match`, `insert` and `undo_last_change`. pi's built-in `edit` is turned off |
| `pi-web-access` | web search and fetch — off by default, see `pi --remote` above |
| `pi-python` | a persistent Python interpreter as a tool (`python`): cells run in one long-lived process, so data stays loaded between steps. Project `.venv` first, else `python3`; figures it saves are shown to the model like any others |
| `@xl0/pi-lovely-notebook` | `.ipynb` editing cell by cell (`notebook_summary`, `notebook_edit_cell`, `notebook_insert`, ...) without breaking ids or outputs; `notebook_read_cell_output` shows a cell's plots as images |

> pi packages run with full system access. Review before adding more.

`pi install` and `pi remove` are refused by the launcher, with a message
saying why: every bootstrap and `pi update` rebuilds the set from
`templates/`, so a package added that way would be removed again. Add one in
`templates/packages.json` and `templates/settings.json` (CONTRIBUTING.md), or
try a local extension for one session with
`PI_ELM_UNLOCK=1 pi -e /path/to/extension.ts` (plain `-e` is refused; LOCKDOWN.md).

The rest of pi's subcommands go the same way, because each manages something
this install manages itself: `pi auth` (the only credential is the ELM key in
`.env`; `./configure.sh` after changing it), `pi mcp` (pi's MCP support is
off), `pi config` (which package resources load is `templates/settings.json`),
`pi list` (what runs is `agent/installed-versions.json`) and
`pi update --models` (ELM's models are `agent/models.json`). Before this they
did not even reach pi: the launcher puts options of its own in front of yours,
and pi recognises a subcommand only as its first argument, so `pi auth login x`
became a prompt to the model. `patch-pi.py` also makes pi itself refuse them,
for the unwrapped `pi.orig`, and takes them out of `pi --help`.

### Permission modes

How much the agent may do before it asks you:

| Mode | What runs without asking |
|---|---|
| `manual` (where new sessions start) | reading files in the project (`read`, `grep`, `find`, `ls`, `view`, notebook reads) and the tools that only talk to you or keep the session's own notes (`todo`, `ask_user_question`, `pin_instruction`, `bg_wait`, ...). Everything else asks: every `bash` command, every edit, `python`, notebook changes, sub-agents, workflows, and any tool not named in `permissionModes.manualNoPrompt` |
| `read-only-auto` | what manual lets through, and shell commands that can only read, and only inside the project: `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `rg`, `find`, `diff`, `file`, `stat`, `du`, `sort`, `uniq`, `cd` into the project and a few more, alone, piped or chained. One redirection to a file, variable, substitution, writing flag (`find -exec`, `sort -o`) or path outside the project on the line and the whole line asks. Edits, other commands, `python`, sub-agents and web calls ask exactly as in manual |
| `auto` | the permission gate's rules as written: most commands and every edit in the project; the ones its `bash` rules mark ask (`git push`, `sudo`, `gh`, `brew install`, `pi update`, `pi --yolo`, ...) ask first |
| `yolo` (one session only) | everything that would ask |

In every mode a refusal stays a refusal (`ssh`, `.env`, system package
managers, the command guard), access outside the project folder asks (yolo
answers it), and the ELM-only policy and the egress proxy are unchanged.

Sub-agents in manual, and in read-only-auto, ask once, at launch. The ask carries a note - "if you allow
it, the agents this starts work in auto mode" - and allowing it does that: the
process pi-subagents starts for the run switches itself to auto
(`permission-mode.ts`), so its agents write and run in the project without a
prompt for each call, and what auto asks about (`git push`, installs, ...) is
forwarded to you as before. Your own session stays in its mode. Before this, a
five-page website in manual was a prompt for every page each child wrote. The
call pi-subagents makes before each child of a parallel or chain run starts
(`subagent_launch`) is part of the launch too, and does not ask again: the
launcher adds it to manual's no-prompt list when `approvedAgents` is `"auto"`
(live, 2026-11-13: a two-child launch was one prompt, where it had been three).
`permissionModes.approvedAgents` in `config/elm-pi.json` is `"auto"` as shipped;
`"manual"` puts every one of their calls back to you. Workflow agents
(the `workflow` tool) are not covered: they cannot ask, so in manual and read-only-auto what would ask
is refused for them, and they can only read. So in those modes a `workflow` call whose
script asks its agents to write or run something is refused before it starts,
pointing to `subagent` or `/mode auto` (`permission-mode.ts`); one whose agents
only read and report runs. test13 (2026-11-13), `/ultracode` in a manual session,
ran nine agents for thirteen minutes and 629k tokens that each reported "BLOCKED".
"Allow for this session" works in manual and read-only-auto too, so a command you approved does
not ask again.

| To choose | |
|---|---|
| inside a session | `/mode` opens a menu of the four modes, marking this session's and the default. Manual, read-only-auto or auto, then **Change for this session** or **Change default mode** (new sessions start that way too); yolo, then **Change for this session only**. `/mode manual`, `/mode auto` and `/mode yolo` skip the first menu. Escape changes nothing; the footer shows the mode |
| one run | `pi --manual`, `pi --read-only-auto`, `pi --auto`, `pi --yolo`: the default is left alone |
| where new sessions start | manual as shipped (`permissionModes.default` in `config/elm-pi.json`), or whichever of manual, read-only-auto and auto **Change default mode** last saved in `agent/permission-mode` (the agent's tools may not touch it; delete it to go back to the shipped default). Never yolo |

Yolo always ends with its session: it is never saved, so the next session,
`pi --continue` and `--resume` included, starts in the default. A sub-agent
runs in the mode of the session that started it, and each of its asks is
forwarded to that session and asked there; a session changed with `/mode`
passes the new mode to the sub-agents it starts afterwards. A yolo session's
sub-agents run as auto and send their asks to it, where they are answered yes:
yolo is never handed on, so nothing the agent starts from its own shell gets
it. With `-p` there is nobody to ask, so in manual or read-only-auto mode whatever
would ask is refused (in read-only-auto the reading commands still run): `pi --auto -p`
for a one-shot run that has to run other commands or edit. A
`PI_ELM_PERMISSION_MODE` already in the environment of a run started from a
shell can make it stricter but never looser, so the agent cannot loosen a
session by setting it, and `pi --yolo` typed by the agent asks you first.

The modes are applied by the permission gate (`@gotgenes/pi-permission-system`),
which already forwards sub-agents' asks to your session. It has a yolo setting
of its own, but that is one switch for every session of the install, and
nothing for the other direction, so `patch-pi.py --gate` adds a small,
anchored patch that makes it read the session's mode on every decision. If a
gate upgrade moves the code it anchors to, the install stops rather than
running manual sessions as auto ones. On an install whose gate is not patched
(`--no-patch`, or `--no-packages`, which has no gate) `pi --manual`,
`pi --read-only-auto` and `pi --yolo` refuse to start, and a session that would
have started in manual or read-only-auto starts in auto and says so: those installs chose to go without.

**read-only-auto** needs no patch of its own. To the gate it is manual - the
launcher exports `PI_ELM_PERMISSION_MODE=manual` with `PI_ELM_READ_AUTO=1` -
so every call is still an ask, and the gate's `authorizerChain`
(`agent/extensions/pi-permission-system/config.json`) names one reviewer,
`elm-read-only-auto`, registered by `command-guard.ts`. It sees each ask before
you do and allows it only when the whole command line can do nothing but read
inside the project; anything else it passes on to you unchanged. It reads the
line with the guard's own shell parser, never as text, and it can allow or pass
on, never deny. Measured over eight manual sessions with that reviewer: 38 of
172 dialogs (22%) were for reading in seven of them. In its first three
sessions 24 reading commands ran unasked and none was asked about. LOCKDOWN.md
lists exactly what passes; `tests/test_read_only_auto.py` holds 32 commands
that run and 66 that must still ask.

**How sub-agent children find pi.** `pi-subagents` spawns each child by resolving
the pi CLI from `process.argv[1]`, then from package resolution, and if both fail
it falls back to `{ command: "pi" }` — a bare PATH lookup. When this install's
command was still called `elm-pi` there was no `pi` on PATH at all, so on hosts
where the first two routes failed that fallback found nothing and sub-agents
would not start.

Three independent fixes, any one of which is sufficient:

- the launcher exports `PI_SUBAGENT_PI_BINARY="$HERE/pi"`, the documented
  override, which short-circuits resolution entirely;
- `bootstrap.sh` creates `agent/bin/pi -> <install>/pi`. `agent/bin` is pi's
  managed-binary directory (`fd`, `rg`) and pi prepends it to `PATH` for every
  child process it spawns, so a bare `pi` lands on the launcher whatever the
  inherited PATH looks like;
- the installer links `~/.local/bin/pi` at the launcher, so a bare `pi` is the
  wrapped one for you as well as for children.

Children go through the **launcher** rather than `cli.js` on purpose: the
ELM-only policy, the `.env` key and the bundled Node then apply to them too. The
launcher sets `PI_ELM_CHILD=1` before exec so nested invocations skip the load
preflight instead of printing one warning per child.

### 5. The Llama tool-call shim

ELM's vLLM instance for Llama 3.3 was started without
`--enable-auto-tool-choice` / `--tool-call-parser`, so **any** request carrying
`tools` returns HTTP 400 — Llama cannot call tools on ELM natively. `shim/shim.py`
lifts tool definitions into a system prompt, strips `tools`, and parses the JSON
call back out of the reply, re-emitting it as OpenAI `tool_calls`.

`elm-shim.ts` starts it on demand on `127.0.0.1:8811` and reuses a running one, so
a fan-out of sub-agents does not start dozens of copies. Qwen never goes through
it. No shim, no Llama sub-agents; everything else is unaffected.

One bug was fixed while porting it here. OpenAI clients append `/v1/chat/completions`
to the base URL they are given, and `ELM_BASE_URL` already ends in `/api/v1`, so
the passthrough branch built `.../api/v1/v1/chat/completions` and the gateway
answered `400 Unknown or unsupported endpoint`. It went unnoticed because only
requests carrying `tools` had ever been exercised, and those take the shimmed
branch, which builds its own path. `_url()` now strips the duplicate segment;
passthrough, shimmed tool calls and `GET /v1/models` are all verified.

### 6. The key, the model id, the smoke test

`.env` is written mode 600 and is gitignored. Then `./configure.sh`:

- queries `GET /api/v1/models` with your key — **the gateway is authoritative**;
  the published Information Services model list was seven months stale when
  checked, naming Llama 3.3 and EuroLLM and not mentioning Qwen at all
- picks the best match for a substring (default `qwen`) and **merges** it into
  `agent/models.json` and `agent/settings.json`, leaving your other settings alone
- sends one completion and prints the reply

Run it again any time: `./configure.sh`.

**Not `./configure.sh llama`.** This install deliberately exposes exactly one
Llama, `elm-shim/meta-llama/Llama-3.3-70B-Instruct`, which reaches tool calling
through the local shim. ELM's own endpoint for that model was started without a
tool-call parser and returns 400 to any request carrying tools, so a second
`elm/meta-llama/...` entry would only ever be picked by mistake from `/model`.
`configure.sh` sets the Qwen model only: `configure.sh llama`, or any substring
that matches a model that is not Qwen, refuses with exit 2 and changes nothing.

Model ids are exact: `Qwen/Qwen3.5-397B-A17B-FP8` — vendor prefix, capital Q,
`-A17B-FP8` suffix. Not `qwen-3.5-397b`. The other university-hosted models are
`mistralai/Mistral-Small-4-119B-2603` (offered here as `elm/...`, `pi --mistral`),
`meta-llama/Llama-3.3-70B-Instruct` and `utter-project/EuroLLM-22B-Instruct-2512`;
everything else your key can see is a commercial model proxied through ELM.

**`maxTokens` from ELM's metadata is the context window, not the output budget.**
ELM reports 262144 for Qwen — that belongs in `contextWindow`, with a smaller
`maxTokens` for output (81920; see [Output length](#output-length-81920-tokens)).
Conflating them produces 400s partway through a session rather than a clean
error at startup.

---

## Verify the install

Bootstrap runs checks 1 and 4 for you.

**1. Only ELM models are offered** — with commercial keys in the environment:

```bash
ANTHROPIC_API_KEY=x OPENAI_API_KEY=x ./pi --list-models
```

```
provider  model                                context  max-out  thinking  images
elm       mistralai/Mistral-Small-4-119B-2603  262.1K   81.9K    yes       yes
elm       Qwen/Qwen3.5-397B-A17B-FP8           262.1K   81.9K    yes       yes
elm-shim  meta-llama/Llama-3.3-70B-Instruct    128K     8.2K     no        no
```

**2. A round trip completes:**

```bash
./pi -p "Reply with exactly: hello from Qwen"
```

**3. Tool calling actually works** — the one that matters. A coding agent drives
everything through tool calls; a model that chats fine but never emits them will
never edit a file:

```bash
mkdir -p /tmp/pitest && cd /tmp/pitest
printf 'def add(a, b):\n    return a - b\n' > calc.py
pi --auto -p "Read calc.py, fix the bug in add, write it back. Then say DONE."   # --auto: a one-shot run in manual cannot edit
cat calc.py          # expect: return a + b
```

**4. The policy holds:**

```bash
./pi --model anthropic/claude-opus-5 -p x     # exit 2, refused by the launcher
```

If 3 fails while 2 succeeds, test the gateway directly:

```bash
auth_header=$(mktemp)
trap 'rm -f "$auth_header"' EXIT
chmod 600 "$auth_header"
printf 'Authorization: Bearer %s\n' "$ELM_API_KEY" > "$auth_header"
curl -fsS -H "@$auth_header" -H "Content-Type: application/json" \
  https://elm.edina.ac.uk/api/v1/chat/completions \
  -d '{"model":"Qwen/Qwen3.5-397B-A17B-FP8",
       "messages":[{"role":"user","content":"Read /etc/hosts using the tool."}],
       "tools":[{"type":"function","function":{
         "name":"read_file","description":"Read a file",
         "parameters":{"type":"object","properties":{"path":{"type":"string"}},
                       "required":["path"]}}}],
       "tool_choice":"auto"}'
```

You want `finish_reason: "tool_calls"` and a populated `tool_calls` array. If it is
empty, that model's vLLM deployment has no tool-call parser — server side, report
it to the ELM team.

---

## Measured behaviour

Numbers from this deployment, not from documentation. They are why the config
looks the way it does.

### The first interactive launch, and why it used to crawl

The first `pi` on a fresh install took far longer than every launch after it, and
none of that time was pi's own startup. Reading `dist/bundle`, interactive mode
does four things over the network while it comes up:

| What | When | Cost |
|---|---|---|
| downloads `fd` and `rg` from GitHub into `agent/bin` | **awaited before the prompt is drawn** | two release lookups + two tarballs, and a 10s/120s timeout each if GitHub is slow |
| `npm view <pkg> version` for every package in `settings.json` | after the prompt appears | one npm process per package, concurrently with the TypeScript transpile below |
| asks `pi.dev` for the latest pi version, and reports the install | after the prompt appears | one request each |
| refreshes the remote model catalogue | after the prompt appears | one request, useless here — the ELM catalogue is `agent/models.json` |

Only the first one blocks, and it only blocks once, because pi keeps the binaries
it downloads. There is a second first-launch cost behind it — the TypeScript
transpile, below — but this is the one that holds the prompt back. The fix is to
have the binaries there already:

Downloads are cached per user, keyed `tool/version/asset`, under
`~/.cache/elm-pi/tools` (`ELM_PI_TOOL_CACHE` moves it). A fresh install on a
machine that has done this before extracts what is already on disk rather than
fetching ~105 MB again, while still getting its own binaries in `agent/bin` —
the cache saves the download, not the ownership. Cache hits are checksummed on
every reuse exactly like a fresh download, so a corrupted or tampered entry
fails the install rather than being installed; `--force` bypasses the cache and
re-fetches.

- **`bootstrap.sh` installs `fd` and `rg` into `agent/bin`** (pinned versions,
  sha256-checked against `templates/tools.sha256`), whether or not the machine
  already has them. The install owns its tools — `rm -rf` this directory and they
  go with it — and the launcher puts `agent/bin` first on `PATH`, so the agent's
  `bash` tool gets the same two binaries the `find` and `grep` tools use.
  `--no-tools` skips this and leaves pi to find a system `fd`/`rg`.

### The rest of the toolbox

`fd` and `rg` are there because pi needs them. Nine more are there because the
*model* keeps reaching for them and cannot rely on finding them — not on a Mac,
and not on a login node someone else administers:

| | | |
|---|---|---|
| `jq` | JSON on the command line | macOS 15 ships it, most Linux images do not |
| `yq` | the same for YAML | CI configs, k8s manifests, conda envs |
| `shellcheck` | lints shell before it runs | this install is mostly bash; it found a stray character in `install.sh` the first time it was pointed at it |
| `ast-grep` | structural search and rewrite, by syntax tree rather than by regex | the thing `rg` cannot do |
| `uv` | Python interpreters, environments and packages | builds the agent's Python, below, and installs into it |
| `mlr` | Miller: reshape, sort, join and summarise CSV, TSV and JSON | data files too big to read into the context |
| `ruff` | Python linter and formatter | the check run on every script the agent writes |
| `pixi` | conda-forge packages without sudo - GDAL, HDF5, ROOT, Ghostscript, ffmpeg, compilers | `pixi exec --spec <pkg> <cmd>` runs one without installing it; `pixi global install` keeps it in `agent/pixi` |
| `resvg` | SVG to PNG with no system libraries | how the agent sees an SVG figure on any host |

All eleven are a single static binary from the project's own GitHub release,
pinned and sha256-checked, installed the same way and deleted the same way.
`ELM_PI_TOOLS=fd,rg,jq` installs a subset: `shellcheck` and `ast-grep` alone are 35 MB
and 51 MB.

### Software the machine does not have

The agent works through it in order, preferring whatever changes least (the
`installing-software` skill). It checks what is already installed, including
environment modules on a cluster, and searches for an existing package before
writing one: `pypi-search` (with `--with-pypi-index`), `conda-search` (conda-forge
package names with their summaries, through prefix.dev's public API),
`pixi search`, `docker search`. Then the isolated options - a Python package
into its own environment; **pixi** for anything on conda-forge, run once with
`pixi exec` or kept with `pixi global install`, all under `agent/pixi`; a
container for anything large - and then **Homebrew**, where the
machine has it. Each `brew install`, upgrade or removal asks you first, and,
once approved, runs past the egress proxy (through a campus proxy if there is
one) and is logged in `agent/egress.log`: a formula downloads from wherever its
source lives - on a Mac without a bottle for it, the project's own site - which
no allowlist can name. Casks, third-party taps and formula files are refused.
**apt, dnf, yum, zypper, pacman and apk** are refused outright: the agent tells
you the exact command for your distribution and what it is for. So is installing
into the system's Python - pip's `--break-system-packages`, uv's `--system` and
the variables that set them: in a test session Homebrew's Python refused a plain
`pip3 install`, and the model added the flag and put 92 packages into the Python
the rest of the Mac uses. Whatever it
installs, it says beforehand what and why, and its report lists where each
thing lives and how to remove it.

### The agent's Python

Part of every install since 2026-11-14 (`--no-python` leaves it out; an
install made before then gains it on its next update). In driven test sessions
every task that needed numpy, scipy, matplotlib or Jupyter - 5 of 5 - worked
around its absence: a pip-built `.venv` in the project, and once a
`pip install --break-system-packages` into Homebrew's Python. Bootstrap
builds `agent/python`: a uv-managed CPython
(`python.version` in `config/elm-pi.json`), a venv with pip, and the packages in
`python.packages` - numpy, scipy, pandas, matplotlib, openpyxl, xlsxwriter,
pyarrow, h5py, uproot, iminuit, sympy, jupytext, nbformat, nbconvert,
ipykernel and pytest. The launcher puts it on `PATH` after `agent/bin`, so `python3` and
`pip` in the agent's shell are this environment - unless pi was started from an
active venv or a conda env other than `base`, which then stays first. The egress
proxy lets PyPI through, so the agent can `pip install` what a task needs into
it in any session. Re-runs keep what it installed; the configured list is
upgraded by `--update` and reinstalled by `--force`. The choice is recorded,
so `pi update` keeps it; `pi setup --no-python` removes `agent/python`, and
with it whatever the agent installed there. An install without it gives the
agent the `python3` on PATH, which it does not install into.

PyPI no longer has a search API (`pip search` fails, and its search page is a
JavaScript challenge), so finding a package for a job needs the web.
`--with-pypi-index` builds one into the install instead: `agent/pypi-index.db`,
an SQLite full-text index of every package's name, summary, keywords and
classifiers (682,448 packages), and `pypi-search` to query it, ranked by match
and then by downloads. It is built from a published snapshot of PyPI's metadata
(`pypiIndex` in `config/elm-pi.json`, pinned to a revision and checked file by
file against its sha256): a 1 GB download that is deleted after a one-minute
build, and fetched again only when the pinned revision changes. A snapshot is
months old by nature, so the agent confirms versions with `pip index versions`.

### Containers

Software that pip cannot supply - a full TeX Live, pandoc - the agent runs in
Docker or Podman, if the machine has one running (Docker Desktop or a Podman
machine on macOS; either on Linux). Installing the engine is yours to do; elm-pi
only governs how the agent uses it. Images can be pulled, and every container
runs with `--network=none` - the permission gate refuses a `run` or `create`
without it, because a container's traffic does not pass through the egress
proxy. `push`, `login` and remote engines are refused, `build` and `compose`
ask. The `containers` skill has the commands and the images (for LaTeX:
`texlive/texlive:latest-medium`, or `latest` for everything); LOCKDOWN.md has
the reasoning.

`fd` and `rg` are also the two pi will otherwise download for itself, so they
are the two that must be there before the first launch. The others only need to
exist by the time the model types them.
- **The launcher sets `PI_OFFLINE=1`**, pi's own `--offline`, which disables the
  remaining three. It covers startup network operations only: ELM requests, web
  search and anything you type are untouched. `PI_ELM_STARTUP_CHECKS=1 pi`
  restores pi's default behaviour for a run.

Updates then happen when you ask for them, which is what `pi update` is for.

### Startup time: where it goes, and how to cut it

`pi` itself starts in well under a second. The npm package set is what you wait
for: they ship **raw TypeScript**, so every launch transpiles and imports them from
several hundred files. Measured with `PI_TIMING=1` and `/usr/bin/time`, reporting
CPU time (user+sys) because that is the number that does not move with machine load
— taken at load ~8 on 12 threads, where wall ≈ CPU. **These figures are
historical:** they were taken when the set was three packages (`pi-subagents`,
`pi-hashline-edit-pro`, `pi-web-access`). It is now sixteen and has not been
re-measured, so read them as the shape of the cost rather than today's figures.

| Configuration | CPU per launch |
|---|---|
| pi + local extensions only (what `--fast` loads) | **1.4s** |
| \+ `pi-subagents`, `pi-hashline-edit-pro` | 3.0s |
| \+ `pi-web-access` | 3.2s |

So: `pi-subagents` + `pi-hashline-edit-pro` ~1.6s,
`pi-web-access` ~0.2s, pi and the local extensions ~1.4s.

`@tmustier/pi-ralph-wiggum` adds `ralph_start` and `ralph_done`, and a `/ralph`
command: a Ralph Wiggum loop that works a task across **fresh sessions** rather
than one growing context. It costs 0.1s of startup, measured at 6.18s against
6.08s with it removed.

It is worth knowing when it beats an ordinary long session, since the two look
similar from outside. One session accumulates context, which is why
`pi-auto-compact` is here. Ralph restarts each iteration, so context rot never
happens and state lives in the repo and `.ralph/<name>.md` instead. Long
verifiable grinds — make the suite pass, work through a backlog — suit Ralph;
work where the thread of reasoning matters wants one session.

Its completion gate is the part that makes it safe to leave alone: before
emitting `COMPLETE` it must record a final verification command that a separate
monitor can rerun in a fresh shell from the same worktree, and an item whose
test cannot be rerun externally must be marked blocked rather than complete.
That matters here, where a Llama child will report success having changed
nothing.

`@pify/btw` adds a side thread: `/btw <question>` asks a **read-only**,
codebase-aware agent while the main session keeps its place, and the exchange
stays out of the main context unless `--save` is passed. `/btw:new` starts a
fresh thread, `/btw:tangent` asks without the main session's context when you
want an uncoloured read, and `/btw:model` and `/btw:thinking` set what answers
it. Measured at 5.23s of startup against 5.29s without — free, inside the noise.

It earns its place here for two reasons. Read-only means it is safe to use
mid-run, including during an unattended loop, with no chance of a second writer
touching the tree. And context is the scarce resource on this deployment —
`pi-auto-compact` exists because of it — so a channel that answers a question
without spending any is worth more here than the convenience.

`pi-next-prompt` suggests your next prompt, the way Claude Code does: when a
reply finishes, the likely follow-up appears in grey in the empty editor. `Tab`
or `→` takes it, typing hides it, `Esc` dismisses it until the next reply. It
asks the session's own model - ELM, nothing else, no key or provider of its
own - by resending the request pi just sent plus one short instruction, so the
prompt cache covers almost all of it. It is still one extra Qwen request per
finished reply, charged to the allocation like any other, and the suggestion
arrives a few seconds after the reply. It runs only in the interactive TUI:
`pi -p`, sub-agents and workflow agents never trigger it. One file, no
dependencies; to drop it, remove it from `templates/settings.json` and
`templates/packages.json` and re-run `./bootstrap.sh`.

**No footer extension is loaded.** `pi-powerline-footer` was dropped for
`pi-zentui`, and `pi-zentui` was then dropped as well: it used a captured
extension context across the session replacement `pi-dynamic-workflows` performed
during evaluation, so every workflow run logged `This extension ctx is stale after session
replacement or reload` against it. The run completed anyway, and an ordinary
sub-agent fork never triggered it, but a footer is not worth an error on every
workflow. pi's own status line remains.

Either is easy to put back. `pi-powerline-footer` cost nothing measurable — 3.48s
against 3.55s without it, inside the run-to-run variance — but it carries one
trap: setting `cost.currency` to anything but USD turns on a background FX-rate
fetch from `cdn.jsdelivr.net`, which the egress proxy refuses and logs, and which
tells you nothing here because prices are zero in `agent/models.json`.

`pi-zentui` costs processes rather than milliseconds, which is worth knowing if it
is ever reinstated: its statusline shells out to `git` (`rev-parse`,
`status --porcelain=2`, `stash list`, `describe`) and runs `--version` probes to
label the toolchain. All read-only and all through `execFile` with an argument
array rather than a shell — but they run inside the extension, so they do not pass
the permission gate that the agent's own `bash` tool does. Nothing in it reaches
the network.

**Three levers, in order of payoff:**

1. **`pi --fast`** for one-shot work. Loads only local extensions — the policy
   set (the ELM-only guard, protected paths, trust guard, pinned instructions,
   command guard and the permission gate), plus `todo`, the skill router,
   `/mode`, `/network` and, with `--remote`, the research instruction (and the claim, repeat,
   server, report and date guards) —
   and keeps pi's built-in `edit` tool. No sub-agents, web search or anchor
   editing. The policy set is the same one loaded when you pass
   `--no-extensions`/`-ne` yourself, and a missing policy file stops the launch
   rather than running without it.
   Measured on the three-package set:

   | | wall | CPU |
   |---|---|---|
   | `pi -p "Reply with exactly: OK"` | 4.68-5.07s | 4.18-4.53s |
   | `pi --fast -p "..."` | **1.43-1.51s** | **1.13-1.20s** |
   | `pi --fast --llama -p "..."` | 1.65-2.33s | 1.29-1.33s |

   End to end on a real edit task (read `calc.py`, fix the bug, write it back):
   **8.01s → 3.49s**, both producing the correct edit.

2. **`./bootstrap.sh --no-packages`** drops the npm set entirely rather than
   skipping it per run, for an install that only ever answers one-shot
   questions. (`pi-hermes-memory` used to be the single biggest item here, and
   `--no-memory` existed to drop it; both are gone.)

3. **Machine load.** Wall time is CPU time multiplied by whatever else the machine
   is doing. The same launch measured 4.7s wall at load 8 and 32-47s wall at load
   350 while CPU barely moved. If pi feels slow, check `uptime` before changing
   any config. If it is slow on an *idle* machine, try excluding the install
   directory from endpoint-protection real-time scanning: 589 npm packages of
   small files is the profile on-open scanning punishes hardest. (Plausible, not
   measured — toggling Defender needs admin rights.)

### The transpile cache: 21s cold, 3.3s warm

The packages are transpiled by jiti, which caches the result in `$TMPDIR/jiti`
and reuses it on every later launch. Measured here with the package set of the
time (three packages) loaded, CPU time, by pointing `TMPDIR` at an empty
directory:

| | CPU |
|---|---|
| cold cache — transpiling ~400 modules | **21.4s** |
| warm cache | **3.3s** |

That is the difference between "the first launch took twenty seconds" and "pi
starts in about three". The cache is real and it works; what it is not is
permanent. It is cold after an install, after a tmp cleaner sweeps it, after a
package update changes the sources, and on the next login node, each with its
own `/tmp`.

So the cost is now paid where waiting is expected rather than where it is not:

- `bootstrap.sh` fills the cache at the end of the install, and says so while
  it does it. `scripts/check-extensions.mjs` loads every extension with pi's
  own resource loader, as a session does, which fills the cache and is also the
  load check: an extension that fails to load gets the packages reinstalled
  once, then stops the install. It needs no ELM key.
- `pi update` fills it again after updating the packages, since new sources
  mean a cold cache.
- `ELM_PI_OWN_TMP=1` moves `TMPDIR` inside the install, so the cache survives
  tmp cleaners and follows a shared home directory between machines. Off by
  default: it moves `TMPDIR` for everything pi runs, the agent's own `bash`
  tool included, so a model that unpacks something large spends home-directory
  quota rather than scratch space. Worth setting on a multi-node estate with an
  aggressive `/tmp`, not worth it on a laptop.

Per-package cost, re-measured warm on the three-package set (`pi
--list-models`, CPU, same machine): pi and the local extensions 0.84s,
`pi-subagents` +0.65s, `pi-hashline-edit-pro` +0.23s, `pi-web-access` +0.16s.
`--fast` remains the single biggest saving available, and skips every package.

**Three things that do not help**, all measured rather than assumed:

- `NODE_COMPILE_CACHE`: 6.5s → 6.4s CPU, and 3.46s → 3.45s on the re-measure.
  V8's bytecode cache covers modules Node itself loads; jiti evaluates the
  packages' modules itself, so they are never offered to it.
- V8 heap tuning (`--max-semi-space-size=32` and `=64`): 3.46s → 3.47s and
  3.39s. Noise.
- `PI_OFFLINE=1`: no difference to `pi -p` (4.2-4.8s wall either way). Print mode
  runs none of the startup checks in the first place, and the model catalogue is
  refreshed when you open the `/model` picker, not on this path. It is set by
  default anyway, for the interactive launch it does change — see above.

Bundling the packages with esbuild was considered and rejected: `pi-subagents`
spawns child processes by path, so bundling changes third-party semantics for a
win the `--fast` path already delivers. It was a stronger objection when
`pi-hermes-memory` was installed and loaded a native SQLite binding; that
package is gone, and with it the only native dependency in the set.

### Qwen is faster than Llama here — Llama is not a speed optimisation

Measured against the gateway directly, so machine load does not enter into it:

| | Qwen 3.5 397B | Llama 3.3 70B |
|---|---|---|
| ~180 tokens out | 2.7-3.0s, **68-76 tok/s** | 3.7-5.7s, 30-47 tok/s |
| 8 concurrent | 2.1s wall, **399 tok/s** | 3.4s wall, 295 tok/s |
| 12 concurrent, all Qwen | **2.5-2.7s wall, 535-566 tok/s** | |
| 12 concurrent, 6 + 6 split | 3.7-4.0s wall, 309-347 tok/s | |

A 397B MoE with 17B active parameters beats a 70B dense model on the same tp4
hardware, and Qwen scales cleanly to 12 concurrent requests. **Splitting a fan-out
across both models is slower than sending it all to Qwen** — the Llama half sets
the wall time.

Llama still has its uses — a fallback when Qwen is rate-limited, and possibly a
cheaper allocation charge (ELM's `guidanceCost` is only visible in the web UI, so
that is unverified). It is reached with:

```bash
pi --llama -p "..."                                    # via the shim
pi --model elm-shim/meta-llama/Llama-3.3-70B-Instruct  # the long form
```

Both go through the local tool-call shim, which buffers the whole response before
re-emitting it, so Llama also loses streaming. That buffering is also why Llama
replies are capped at 8192 tokens (`maxTokens`, set in `elm-shim.ts`): pi gives
up on a connection that sends nothing for 300 s and retries, and at 30-47 tok/s
a 16384-token reply takes 350-550 s, so long replies timed out and were
generated again. `agent/AGENTS.md` tells the session to send sub-agents to
`qwen`, and the `delegate` agent is described as Llama, for numbered steps
only.

### Mistral Small 4: the other model with tools and images

`mistralai/Mistral-Small-4-119B-2603` is the model EDINA's own `pi-elm-models`
package registers beside Qwen. Checked against the gateway with an ELM key on
2026-11-11, before it was added here:

| | |
|---|---|
| Tool calls | correct, streamed and not, and a tool result answered in the next turn |
| Images | read rendered text (`QUARK 4729`) and a bar chart correctly, one try each; plain colour squares were misnamed (red as black at 16 px, brown at 256 px) |
| Reasoning | none unless asked: `reasoning_effort: "none"` and no field both give 0 reasoning tokens, `"high"` gives them |
| `developer` role | **refused**: 400 `Unknown message role: developer` |
| Speed | 150-190 tok/s on one stream (40,000 tokens in 214 s) |

The `developer` refusal is why its entry carries `supportsDeveloperRole: false`,
and why bootstrap.sh reapplies that `compat` to an existing install: pi sends a
reasoning model's system prompt as `developer` unless told not to, so without it
every request fails. Through pi itself (`pi --mistral`) it read a file, ran a
command, wrote and ran a script, and read the chart through `read`.

#### Images: Qwen against Mistral

Measured on 2026-11-12 (`docs/tuning/2026-11-12/vision-summary.json`; the pages,
the requests and the scoring are `docs/tuning/harness/vision_pages.py`,
`docs/tuning/harness/vision_eval.py` and `docs/tuning/harness/vision_score.py`). Each model got
the same images through ELM, sent as pi sends them, five times over. Qwen ran with
thinking off, its default here; Mistral ran with thinking high, its default, and
with thinking off. Five images had known answers: a bar chart, a line chart,
coloured shapes to count, a table and a rendered web page. Four pairs asked for
every visible difference: a web page with four planted changes, a chart with
three, a page with three subtle ones (two nav items swapped, two headings
reworded), and the same page twice.

| | Qwen, thinking off | Mistral, thinking high | Mistral, thinking off |
|---|---|---|---|
| Reading the charts, table and page: answers right | 101/105 | 99/105 | 104/105 |
| Counting the shapes | 15/15 | 11/15 | 14/15 |
| Planted differences found, over the three changed pairs | 96% | 84% | 65% |
| Differences reported that are not there, per comparison | 0.4 | 1.1 | 8.2 |
| ... when the two images are the same page | 0.6 | 1.2 | 12.8 |
| The page's overflowing "Everywhere" card named, unasked | 1/5 | 0/5 | 0/5 |
| Median time per request | 4.8 s | 3.5 s | 1.9 s |

Qwen's four misses in reading were the word "Everywhere" given as `null` where
the question asked for numbers; all five of its descriptions name it. So all
three models read about equally well, and they compare very differently:

- **Mistral with thinking off invents changes**: 12.8 per comparison of a page
  with itself, among them header colours, button colours and a "Key Fact" box
  said to have become "Did you know".
- **Mistral with thinking high misses colour changes and still invents some.** It
  noticed the navbar turn from green to blue in 1 run of 5, and on the subtle
  page it reported 2.4 changes that were not there.

Image description and consistency work therefore goes to `qwen`, including from
a `pi --mistral` session (AGENTS.md: "Images go to `qwen`"). Even Qwen named the
overflowing card in only 1 run of 5 without being asked. So a check for a
layout fault asks about it by name, and every difference a model reports is
confirmed in the page's source before it is passed on.

#### Why it first did badly, and what fixed it

It is smaller than its name. 119B is the total; it is a mixture of 128 experts
of which 4 run, **6.5B parameters active per token** (model card), against
Qwen's 17B and Llama 3.3's 70B, all of them active. And as first set up here it
was sampled at **temperature 1.0**: the model ships no sampling defaults, so
vLLM falls back to 1.0, while Mistral says 0.0-0.7 with reasoning off and 0.7
with reasoning on. Asked for a random number twelve times with no temperature
sent, it gave eight different ones; at 0.15, the same one eleven times.

Seventeen small agent tasks (eleven: find a function, rename by numbered steps,
fix a bug, add a function, a data question, summarise a file, docstrings on 12
functions...; and six written afterwards to check nothing was tuned to the
first eleven), each three times through `pi --auto -p`, checked by script,
2026-11-11:

| Mistral, as set up | All 17 | The 6 later ones | Reported work it had not done | Median |
|---|---|---|---|---|
| As first added (temperature 1.0) | 33/51 | 8/18 | 3 | 7.7 s |
| With written rules against false claims | 34/51 | 10/18 | 3 | 7.8 s |
| Temperature 0.15 | 38/51 | 9/18 | 3 | 6.0 s |
| 0.15 and the claim guard | 35/51 | 8/18 | **0** | 7.6 s |
| **Reasoning on, temperature 0.7, and the claim guard** | **46/51** | **15/18** | **0** | 9.5 s |
| Qwen, for reference | | 18/18 | 0 | 15.4 s |

On the first eleven, the reasoning-on Mistral passed 31 of 33, where Llama
passed 23 and Qwen 33. So that is how it is set up: `reasoning_effort` high by
default (`modelThinkingLevels` in `agent/settings.json`), temperature 0.15 when
reasoning is off and 0.7 when on (`samplingParams` in `agent/models.json`). Its
reasoning is short - tens of tokens, two seconds more a task - unlike Qwen's,
which measured 400x slower and stays off.

A later run, on those tasks and eight harder ones (moving a function between
modules, debugging, tests that must catch a planted bug, a fit), set each
model's settings against alternatives, side by side. Mistral with reasoning on
passed 72 of 75 at 0.7, 69 at 0.4 and 73 at 0.15, so 0.7 stays; it passed every
hard-task run, as Qwen did, in under three-quarters of the time (14.5 s a task
against 20.1 s). Qwen's shipped profile beat both
alternatives (41 of 42, against 39 without its presence penalty and 40 with its
thinking-mode sampling). A temperature sweep after that changed nothing either:
Qwen was level from 0.2 to 0.7 and a little lower at 1.0, Mistral with reasoning
off was level from 0 to 0.7, and Llama's best (0.3, at the shim) was within what
four identical runs at 0 had spread over. Nor did the rest of the sampling
settings, tested on 50 tasks including 25 harder ones, with each shipped setting
run twice side by side to show the noise: top_p, top_k, min_p and the presence
penalty for Qwen, top_p for Mistral and the shim's temperature for Llama. Mistral
at top_p 0.8 once looked 6 points better; run again on its own, under a rule
written before it started, it was 1.4 points better with p 0.63, and stays as it
was. Every number, run and script is in [docs/tuning](docs/tuning/README.md).

Its one stubborn failure, with reasoning off: asked to add a function and "reply
with one line saying what you did", it replied that it had added it, with no
tool call at all, in 12 runs out of 12. Others report the same on Mistral's own
API ("Task completed" and nothing done). A written rule against exactly that did
nothing; `agent/extensions/claim-guard.ts` catches it instead. A run with no tool
call whose reply says something was added, changed or run is sent back once
with a note, and in all six runs where it fired the task then passed. It cannot
catch a claim after tool calls that did not do the work - one run in the
reasoning arm called four tools and reported a function that is not in the
file - so a child's report is still not evidence. Mistral's own coding agent's
rules (Vibe's prompt) were tried as well and added nothing measurable.

So it now takes the routes Llama had: pi-task-models' `fast` profile and the
`frontier` fallback, with reasoning on. Sub-agents still run on Qwen, which
passed everything; `delegate` and `--llama` are unchanged.

It also takes the compaction summary when Qwen cannot write it (the `balanced`
fallback, which was Llama), with reasoning off, as Mistral's own CLI uses it.
Measured with pi's own `compact()`, two runs each, on a real 74K-token session
and a generated 159K-token one with eight facts planted in it:

| Facts kept | Qwen | Mistral | Llama |
|---|---|---|---|
| Real session (of 11) | 10, 11 | 9, 10 | 9, 10 |
| Long session (of 8) | 5, 6 | 5, 4 | 4, 3 |
| Time per summary | 44-63 s | **7-13 s** | 16-24 s |

As good as Llama or a little better, and twice as fast. It is not a question of
size: pi cuts every tool result to 2,000 characters before summarising, so even
the 159K-token session went out as about 25K tokens, well inside Llama's 128K.

For pi-next-prompt's suggestions it is no better: blind, Qwen's were better in 4
of 11 sessions and Mistral's in 3, and both answered in about 0.7 s. Suggestions
come from the session's own model, which keeps the gateway's prompt cache, and
that is unchanged.

#### What the gateway could do

The tool-call parsing is sound: 1,018 Mistral replies, not one with a raw
`[TOOL_CALLS]` marker in its text, the sign of a vLLM older than 0.20. Three
things for ELM's operators that would help every client, not only this one:

- **a default temperature** for Mistral (`--override-generation-config
  '{"temperature": 0.15}'`), since clients that send none get 1.0;
- **mistral_common 1.13.1 or later**, which maps the `developer` role to
  `system` instead of refusing it;
- **Mistral Medium 3.5**, which Mistral says supersedes its coding models, if a
  Mistral model for agent work is wanted.

### Output length: 81920 tokens

`maxTokens`, the most one reply may produce, is 81920 for Qwen and Mistral. It
was 32768, a guess; 81920 is what EDINA's own `pi-elm-models` package sets, and
it was checked against the gateway on 2026-11-11 before it was adopted:

| | Qwen | Mistral |
|---|---|---|
| `max_tokens` / `max_completion_tokens` 81920 | accepted | accepted |
| 1,000,000 | 400: `cannot be greater than max_model_len=262144` | the same |
| One streamed reply past 32768 | 43,893 tokens, counted to 9,000 and stopped by itself (1,966 s) | 40,000 tokens, forced with vLLM's `ignore_eos` (214 s) |

Nothing on the gateway cut either stream, and pi's 300 s no-data timeout never
comes into it while tokens arrive. That Qwen reply averaged 22 tok/s, so a reply
near the limit is a half-hour wait, not a quick one.

A larger limit takes nothing from the usable context. pi clamps each request's
limit to the room left in the window, and compaction here is pi-auto-compact at
70% of `contextWindow`, which does not read `maxTokens` (pi's own, which reserves
a fixed 16384, is off). What changes is the end of a full session: a reply cut
short by that clamp now stops below the configured limit, which pi treats as
recoverable - one compact and retry - where a reply at a 32768 limit was final.
Thinking gains most: reasoning tokens count against the same limit.

bootstrap.sh moves an install's 32768 to 81920 and leaves any other value you
set alone.

### Thinking is off by default

Same task, same 32K output budget:

| | thinking off | thinking on |
|---|---|---|
| Latency | 0.7s | 286.7s |
| Answer | caught both bugs | caught one, missed the other |

~400x slower and worse. At smaller output budgets it is worse still: reasoning
consumes the whole allowance and `content` comes back empty with
`finish_reason: "length"`. `/thinking` turns it on per session when a task
genuinely warrants it.

### Prefix caching gives ~8x

ELM's vLLM does prefix caching, measured directly:

| | Latency |
|---|---|
| 30,215-token prefix, first call | 3.34s |
| Same prefix, repeat | **0.40s / 0.55s** |
| Fresh prefix | 3.01s |

pi's half is verified too, by capturing its real request bodies through a
streaming-preserving proxy: the `developer` system message is byte-identical every
turn, each message list is a strict verbatim extension of the last, and TTFB fell
from 3.02s to 0.96s **while the prompt grew** — the cache signature.

So: `AGENTS.md` and long stable context are nearly free, and **turn count, not
prompt length, is what to optimise**. Nothing needs enabling. The skill router
is built to keep this: it adds skills as a message after the request rather
than changing the system prompt, which would change the first bytes of every
request and lose the cache (see [below](#skills-and-the-skill-router)).

Compaction (`pi-auto-compact`) starts at **70%** of the context window, an
installer-owned setting (`autoCompactThreshold`; it was 50%). Each compaction
re-sends the history uncached and the next request starts cold, so compacting
early costs more than the context it frees. Standing instructions recorded
with `pin_instruction` (`pinned-instructions.ts`) are put back into the system
prompt on every run, so compaction cannot summarise them away.

Two settings were tried and removed: `compat.sendSessionAffinityHeaders` /
`sessionAffinityFormat`, and `PI_CACHE_RETENTION=long`. Neither produced a
measurable gain.

### Sub-agent fan-out

| Concurrent sub-agents | Wall time | Result |
|---|---|---|
| 3 | 98s | all correct |
| 6 | 110s | all correct |
| 12 | 269s | all correct |
| 20 | 264s | all correct |

Wide fan-out is close to free past the fixed startup cost. But delegation is
priced per round trip: forcing it on a four-file docstring task turned a
36-second direct edit into a 560-second run that never finished. `AGENTS.md`
therefore keys the rule to **work size, not file count**.

At 20 children some results came back as "previews omitted by budget" — tell
sub-agents to report tersely or raise `maxOutput`.

A `qwen` child starts with a copy of the parent's conversation, which includes
the parent launching the run the child is part of. In test4 (2026-11-12) two
children finished their file and then took that launch for their own. They
called `subagent({ action: "status" })` on the parent's run, a tool children do
not have, 394 and 705 times. Every call was answered "Tool subagent not found",
until pi-subagents' 30-minute timeout. That came to about 75 million input
tokens, most of the session's use, and it set off the 429s the parent hit too.
pi-subagents already tells every child to treat the inherited conversation as
reference only, and `qwen.md` now says the parent's runs are not the child's;
`agent/extensions/repeat-guard.ts` catches what wording misses. Since
2026-11-13 a `qwen` child starts fresh anyway (`defaultContext: fresh`): a
forked child sent the parent's whole conversation - about 35k tokens in a
driven run - with every one of its turns, half of all its input, and the gateway
reports no cached tokens. `owner-guard.ts` finds a fresh child's launch, and so
its siblings' files, in the parent's session (`PI_SUBAGENT_PARENT_SESSION`). It tells the
model after 3 identical failing turns in a row, and at 8 it ends the run.

Each sub-agent is a full Node process. A 32-worker run drove load average to 104
on a 12-thread laptop and made every new pi invocation hang, which is why the
launcher warns above 1.5x core count and starts anyway: a shared login node or a
busy desktop sits over that line most of the day, and a refusal there costs more
than the slow start it prevents. `PI_FORCE=1` drops the warning too;
`PI_STRICT_LOAD=1` restores the old refusal, which is what you want in a batch
job or a cron run.

### Retry under a gateway storm

Verified by injecting faults through a local proxy: five injected 503s, then a
success, backing off 2/4/8/16/32s — exact doubling from `baseDelayMs`, and the
agent run continued as if nothing had happened.

The default `maxRetries: 3` gives ~14s of tolerance; against a 429 storm on a
shared university gateway pi surfaced `429: Rate limit exceeded` after ~15s.
`retry.provider.maxRetries` stays at **0** — SDK-level retries can swallow
out-of-quota errors before pi sees them, blocking the agent until the provider
quota resets. pi uses its own backoff and ignores `Retry-After`.

The gateway's 429s say `Retry-After: 1`, and profiled through a logging relay
they come after a burst of large requests - ~100k prompt tokens inside a minute,
which three or four steps of a session at 25-30k tokens each reach. With a 2s
base the waits were 2, 4, 8 and 16s: one turn lost 30s to a refusal the gateway
had asked to be retried after one. So `baseDelayMs` is **1000**: a short
refusal clears in a second or three.

The tuning runs of 2026-11-11 and 12 ran with `maxRetries` at 6, which allows
about 63s of waiting (1s doubling to 32s). 581 of 3,298 sessions met at least one
429, and 559 of those carried on. The other 21 used every retry and failed. The
waits measured 1.1, 2.1, 4.2, 8.2, 16.2 and 32.2s, with no spread: every session
refused in the same second came back in the same second. So since 2026-11-12:

- `maxRetries` **10**: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512s - ~1023s, about
  17 minutes, before a turn fails. An overnight run waits out a long storm
  instead of stopping at it. A tool that gives up on a session sooner is making
  that choice itself.
- `maxAgentDelayMs` **512000**. pi caps each wait at 60s unless told otherwise,
  which would have flattened the schedule after 64s.
- Jitter: `patch-pi.py` scales each wait by a random 0.75-1.25, because pi has
  no setting for it. Sub-agents refused together then come back at different
  times. Three 429s in a row were retried after 0.8, 2.1 and 4.5s.

`httpIdleTimeoutMs` **120000**: a request that sends nothing for 120s - no
headers, no first token, no next chunk - is ended and retried. pi's default is
300s. Measured over 41,261 successful requests to ELM on 2026-11-11 and 12, the
429 storms of the tuning runs included, the longest wait before a reply began
was 58.4s and none passed 60s (Mistral's thinking streams too, so it never
counts as silence). The two streams that did stall ran 477.6s and 1126.6s
before the 300s timer ended them; one was eight minutes of a test session. 120s
is twice the longest healthy wait and ends a dead stream three minutes sooner
(`docs/tuning/2026-11-12/stall-summary.json`).

That timer starts once a request has been sent. One that stalls while it is
still going out - on 2026-11-13 a request carrying a page screenshot, whose
upload the gateway stopped acknowledging - is not covered by it, and waited 921s
for the kernel to give up on the connection. The egress proxy now drops a
connection whose sent data has gone unacknowledged for 120s
(`TCP_USER_TIMEOUT` on Linux, `TCP_RXT_CONNDROPTIME` on macOS), and pi retries
it at once; a slow link that is still acknowledging is not affected. Where the
kernel has neither - WSL 1 defines the first and answers "Protocol not
available" - the proxy keeps the limit itself: each send through a tunnel is
given up, and logged as `DROPPED`, once the connection has taken no data for
120s. That backup sees an upload that has stalled, which is the case above; it
cannot see a request small enough to sit whole in the kernel's own buffer,
which only the kernel's limit covers.

pi retries an error whose text says rate limit or 429, a 5xx, a connection
error, refused or reset connection, other side closed, socket hang up, fetch
failed, a DNS failure (`ENOTFOUND`, `EAI_AGAIN`), a timeout, or a stream that
was terminated or interrupted. It does not retry a 400, or a 429 that says the
quota or billing is used up, since both are final. A failed attempt stays in the
session file but is left out of what the model is sent, and `pi -p` prints
nothing for it, so a retry that worked is seen by neither the model nor you.

Checked on 2026-11-12 against a stand-in gateway that fails on purpose. It ran
over HTTPS, through the launcher's egress proxy, from an Ubuntu 24.04 container,
with packet loss and outages applied on the link to the gateway. Every case
ended in the normal reply:

| Fault | What happened |
|---|---|
| 429 three times | retried after 0.8, 2.1 and 4.5s |
| connection reset with no reply; a 502 HTML page; a 503 | retried |
| reply cut after its first chunk, by a reset or by a clean close with no finish | retried, the partial reply dropped |
| no reply at all, or a reply that stops halfway | retried once `httpIdleTimeoutMs` passed (120s here; 10s in the test) |
| gateway down for 6s (connection refused) | retried until it was back |
| DNS failing for 12s | retried until it resolved |
| 20% packet loss, 80 ± 40ms delay | normal, 6s |
| 40% packet loss, 150 ± 50ms delay | normal, 13s |
| 30s of total packet loss partway through a reply | TCP carried the reply across it |
| Llama through the shim: two 429s, then a reset | retried |
| a 429 and a reset after the tool had run | retried; the tool ran once |

Downloads at install time retry too: Node, the tools, the standalone Python and
the PyPI index. They retry five times, waiting curl's own 1 to 16s, and give up
after 120s. They retry any failure where curl has `--retry-all-errors` (7.71 and
later); elsewhere they retry only timeouts, refused connections and 5xx
responses. `configure.sh`'s two calls to the gateway retry only those transient
failures, so a wrong key fails at once.

### What every request carries

Every request to ELM starts with the same fixed part: pi's own instructions,
`APPEND_SYSTEM.md`, `AGENTS.md`, the list of skills, and the definition of every
tool. Measured through a logging relay, that was ~24k tokens before a word of
the conversation - 56.5k characters of system prompt and 35 tools (36.3k) - on
every step of every session and sub-agent. Cached, it costs little time; it
still fills the context window and counts against the gateway's limits.

So the fixed part holds rules, and detail lives where it is read on demand:

- `AGENTS.md` and `APPEND_SYSTEM.md` carry the short form of each rule and
  point to `agent/reference/` (finished-work checklist, `.pi` and git, project
  memory, anchor editing, the egress proxy, reporting, asking, fits and
  figures, the ELM service) for the rest - 20.3k characters to 8.5k, and 12.1k
  to 7.3k. `APPEND_SYSTEM.md` also tells the model where this install keeps
  what it might be asked about - the reference files, the skills, the settings
  and these documents - so it reads them when a question needs them.
- Skill descriptions are one line each (4.9k characters to 2.3k); the skill
  router adds a skill's full text when a request needs it.
- Tools used only on request are not offered (`excludedTools` in
  `config/elm-pi.json`): the `workflow` tools unless `pi --workflows`, and five
  notebook tools with simple substitutes. (Since 2026-11-13 the `workflow` tools
  are offered by default, `pi --no-workflows` leaving them out, which puts about
  6.9k characters back on each request.)

Result, same first request: system prompt 56.5k to 40.4k characters, 35 tools to
28, **~24.0k prompt tokens to 17.8k** as counted by the gateway.

### Latency variance is pi, not ELM

Identical pi tasks have ranged from 8s to 98s. Twelve identical calls straight to
ELM measured min 2.89s, median 3.43s, max 5.53s. The spread comes from pi's agent
loop taking more turns on some runs. Do not tune config against a single timing
sample — the noise is larger than most config effects.

### Extensions: add them one at a time

Same survey task, same directory:

| Extensions loaded | Result |
|---|---|
| none (`--no-extensions`) | 18s, correct |
| `protected-paths` + `todo` | 77s, correct |
| \+ `notify`, `session-name`, `model-status` | 540s timeout, no output |
| \+ `git-checkpoint`, `dirty-repo-guard` | 540s timeout, no output |

`git-checkpoint` and `dirty-repo-guard` act on git state and hang outside a
repository; the others were not isolated individually. Only the three that measure
clean ship here. Add any more one at a time and time a known task before and after.

### Llama needs steps, not goals

With anchor editing in place:

| Task given to Llama | Result |
|---|---|
| Single file, "fix the bug" | works, 18s |
| Two files, "read each and add docstrings" | **claimed FINISHED, changed nothing** |
| Two files, numbered steps | **both correct, 17s** |

The difference is planning, not editing. Give a Llama sub-agent a numbered list of
concrete actions and exact paths, and always verify its report. Anything that
needs deciding *what* to do goes to Qwen.

---

## Dynamic Workflows, and the one control it lacks

`@quintinshaw/pi-dynamic-workflows` is **installed and loaded**, which is what
provides `/ultracode`, `/deep-research`, `/adversarial-review`, `/code-review`,
`/codebase-audit` and the `/workflows` TUI.

`/ultracode` and `/effort` drive the `workflow` tool, which is offered unless
the session was started with `pi --no-workflows` (or `PI_ELM_WORKFLOWS=0`; it was
opt-in, with `pi --workflows`, until 2026-11-13). In a session without it the package still
adds its note - call the `workflow` tool, fan out widely - to every message of
16 characters or more, and twice (test3, test4) Qwen then spent 11 to 14 turns
switching between the two script dialects for a tool it did not have.
`agent/extensions/ultracode-note.ts` replaces the note there, in what the model
is sent, with one line: the tool is not loaded, fan out with `subagent`.

It is enabled knowingly, not safely. Its model-policy hook can be overridden by
code that calls the package directly - an extension, or the SDK - which is weaker
than the strict ELM-only promise the rest of this install keeps; the package was
held out of the default set for exactly that reason, and was then enabled
deliberately. A workflow *script* cannot: in 3.15.1 `agent()` passes on a fixed
set of options (label, model, tier, thinking, schema, timeout, retries, thread,
phase, agent type, isolation, cwd), and the per-run resolver is not one of them. What remains true is
that `agent/extensions/workflow-model-scope.ts` is a **required** extension:
bootstrap refuses to finish without it, and a test asserts it stays in
`requiredExtensions`. The guard is therefore always present — it is simply not
unoverrideable.

What it has no equivalent of is `modelScope`. pi-subagents takes
`enforce: true, strict: true, allow: ["elm/*", "elm-shim/*", "inherit"]` from
settings and no child can leave those providers. Dynamic Workflows can route through
tiers in `agent/workflows/model-tiers.json`, whose documented examples are
`openai-codex/gpt-5.4-mini` and `openai-codex/gpt-5.5`. The installer still deploys
`agent/extensions/workflow-model-scope.ts` as the guard, and it refuses models
outside the configured ELM providers.

Measured on this install:

- A workflow agent pinned to `openai-codex/gpt-5.4` is refused before any session
  is created. The run store records `MODEL_SPAWN_REJECTED` and the policy's own
  text, "This install is restricted to university-hosted models", against a total
  spend of about 3 tokens.
- With `inheritMainModel: true` in `agent/workflows/settings.json`, untagged
  agents inherit the session model. A two-agent workflow recorded
  `elm/Qwen/Qwen3.5-397B-A17B-FP8` for every model reference in its run store and
  nothing else.
- It does **not** turn worktree isolation on by itself. A two-agent workflow that
  edited `m.py` and created `README.md` wrote both into the working directory, and
  `git worktree list` showed only the main tree.

Two things to know before relying on it.

**The policy is weaker than the one it stands in for.** The package documents
per-run `AgentRunOptions.preSpawnModel` and instance
`WorkflowAgentOptions.preSpawnModel` as outranking the process resolver, so code
that sets its own wins. A workflow script cannot reach either (see above), but an
extension can. `strict` scope in pi-subagents has no such hole.

**Its agents run in this pi process, with the guards listed in its settings and no
others.** A workflow agent is a session pi creates in-process, not a pi-subagents
child, and it loads no extension unless `providerMiddlewareExtensions` in
`agent/workflows/settings.json` names it (bootstrap writes that list and drops any
other). It names the policy - `elm-only`, the permission gate, `protected-paths`,
`command-guard`, `cc-safety-net`, `pinned-instructions`, `trust-guard` - and the
guards that act within one agent's own session: `report-guard`, `server-reaper`,
`repeat-guard`, `claim-guard`, `date-note` and `view-outputs` (with its `view`
tool). Measured live (2026-11-13), one agent per guard, in parallel: a server
without `--bind 127.0.0.1` refused by command-guard; `.env` refused by
protected-paths; `git push` refused by the gate ("requires approval, but no
interactive UI is available"); `view` drew an image and the agent had today's
date; two servers started in the background were stopped by server-reaper as
their agents ended. `owner-guard` is loaded for the one rule that needs no task:
a workflow agent - told apart by its run's `store_put`/`store_get` tools - may not
replace, unread, a file another changed after it started. Measured live
(2026-11-13): agent A slept 3 s and wrote `shared.txt`; agent B, which had run
`sleep 8` meanwhile, was refused replacing it and said so, and the file kept A's
word. Two limits: a change in an agent's first 1.5 s is not caught (allowance for
coarse or skewed file times, as on network home folders), and a change made during
the agent's own command counts as its own only if that command names the file -
the first version counted B's `sleep 8` as having written A's file. The rest of it reads
pi-subagents' tasks and environment, which a workflow agent has neither of: there
is no who-wrote-what list and no check of shared files before a run. Not loaded,
and why: `remote-research` (workflow agents have no web tools);
`image-mentions`, `skill-router`, `wait-guard`, `permission-mode` (nothing to
do there).

The permission mode reaches them: the gate reads it from the environment, which
they share. A question the gate would put to you is refused instead, since a
workflow agent has nobody to ask, so in `manual` and `read-only-auto` a workflow agent can read and
nothing else, and in `auto` what the rules mark "ask" (git push, brew install,
...) is refused. `yolo` was not measured.

Two probes on the way found something the guards did not then cover: a workflow
agent given six steps made no tool call at all and returned six made-up results
("File written: .env" - no file was written), twice; another replied "started"
to "use the bash tool to run ... echo started" without running it. claim-guard
now also sends back any sub-agent whose task said to use a tool or run a command
and whose run made none, and in the last probe it did: the agent was sent back,
ran the command, and its server was then stopped by server-reaper.

**It replaces the session, which breaks extensions that hold on to a context.**
`pi-zentui` was removed over this. A Dynamic Workflows run produced `This extension
ctx is stale after session replacement or reload` against
`pi-zentui/extensions/zentui/index.ts` on every run; the run completed, and an
ordinary `qwen` sub-agent fork never triggered it, so it is specific to the
replacement Dynamic Workflows performs. pi's own message names the contract an
extension has to keep — do not use a captured `pi` or command context after
`newSession`, `fork`, `switchSession` or `reload`; move post-replacement work into
`withSession` — so the defect is the extension's, and Dynamic Workflows is only
what exposes it. Worth checking against any extension added later that draws
persistent UI.

And one observation about the output rather than the plumbing: in that two-agent
run, one agent changed `v()` to return 2 while the other wrote a README saying it
returns 1, because it had read the file first. Individually correct, collectively
wrong, and nothing in the workflow caught it. That is the failure a cross-checking
sweep exists for, which is the argument for keeping the standards even when the
orchestration comes from somewhere else.

## Skills and the skill router

`agent/skills` holds seventeen skills from `templates/skills`: physics methods
(fitting, statistics, uncertainties, histograms, derivations, numerical
methods, constants, documents), scientific Python and C++, changing code (a bug,
failing tests, code from a spec: `changing-code`), installing software
and running containers, the sub-agent and workflow orchestration rules, and
developing elm-pi itself (a plugin, in a clone: `developing-elm-pi`). pi lists each skill's name and description
and leaves loading it to the model, which measured unreliable here: asked for a
half-life, the model never read `data-fitting` and used the method that skill
forbids.

So `skill-router.ts` matches each request you type against a keyword table and
adds the best two matching skills in full, and names up to two more by path.
They go in as a message **after your request**, shown as a dim
`skills: ...` line (expand it for the paths) and stored in the session — not
as a hidden section of the system prompt, which changed the first bytes of the
request and cost ELM's prefix cache the whole history each time. Each skill is
added at most once per session; it comes back only after a compaction has
summarised it away. The keywords are deliberately narrow: ordinary software
requests ("add a regression test", "make the magic number a named constant")
add nothing, and neither does the idiom "fits in with".
`tests/test_skill_router.py` runs both kinds of request through it.

One rule looks at the machine as well as the request. A request for slides,
notes or a paper rarely says "compile", so on a machine with no TeX
(`latexmk`, `pdflatex`, `xelatex`, `lualatex` or `tectonic` on `PATH`)
`containers` goes in beside `physics-documents`. That skill says how to build in
Docker or Podman, with time limits, and that an unbuilt document is reported
as unbuilt. The rule came from a real session: asked for a Beamer deck, it
found no TeX, waited 13 minutes on a `docker run` while Docker Desktop was
still starting, and reported a deck it had never compiled as complete.

Sub-agents are routed by their task alone, with the agent's own instructions
cut out first. Runs not started by a prompt you typed — auto-compaction,
loop drivers, sub-agent completion notices — add nothing. The first
`subagent` or `workflow` call of a session is refused until the orchestration
skill it needs has been read, with the path to read.

## Sessions, memory and artefacts

### Prompt templates

`templates/prompts` holds five `/` commands, rendered into `agent/prompts` on
every bootstrap: `/explain`, `/fix`, `/review`, `/init` and `/plot`. pi turns
each file into a command whose name is the file's, expands the text into your
request when you type it, and shows its `description` in the completion menu -
so they cost nothing until used, which is why they are templates and not more
lines in `AGENTS.md` (whose size is capped).

| Command | What it asks for |
|---|---|
| `/explain <file or output>` | the code or data explained for a physicist who has read none of it: quoted lines, the assumptions made about inputs, what looks wrong and whether it was checked. Changes nothing |
| `/fix <failure>` | reproduce it, name the cause in one line, make the smallest change, re-run the same command, re-read the diff. Never weakens a check to get a pass |
| `/review <diff or files>` | a review that runs the code before judging it: wrong results, claims no command backs, edge cases, evidence with units. Findings with `path:line`; changes nothing |
| `/init` | the project's `AGENTS.md` written from what is in the directory - build and test commands it has run itself, layout, conventions, what is generated and must not be edited |
| `/plot <what>` | a figure with units on both axes, error bars from the data's own uncertainties, residuals under the fit - then `view` of the file it wrote and a report of what is actually in it |

Each takes its argument with a default, so a bare `/plot` is a complete request.
A template this repo drops is removed on the next bootstrap; one you add to
`agent/prompts` yourself is never touched (`.elm-pi-managed` lists ours).
`tests/test_prompts.py` holds their format, their substitutions against pi's
documented list, and their presence by name in this file.

## Sessions, memory and artefacts

`sessionDir: ".pi/sessions"` is **relative**, so it resolves against the working
directory and each project keeps its own history. This also fixed an accumulation
problem: sessions had reached 1.9 GB across 699 files in one central directory.

Transcripts contain whatever the agent read, which may include secrets, so in
a git work tree the launcher writes `.pi/.gitignore` containing `*`: the whole
directory is invisible to git, and `git add -A` cannot stage it. Nothing needs
adding to the project's own `.gitignore`.

Precedence is `--session-dir` > `PI_CODING_AGENT_SESSION_DIR` > `sessionDir`.

Durable project facts go in that project's own `AGENTS.md`, which pi loads from
the working directory and its ancestors on every session, so they travel with the
repo. `agent/AGENTS.md` carries the policy for what belongs there (durable,
project-specific, not derivable from the code — and never secrets).

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `401 Missing or invalid Authorization header` | No bearer token. Cookies don't work on `/api/v1`. |
| `401 Invalid API key` | Key wrong, revoked or expired — check `expiryDate` on the request record. |
| `Model not found` for an ELM model | Wrong case or missing vendor prefix. Copy it verbatim from `/api/v1/models`, or re-run `./configure.sh`. |
| `Model not found` for a commercial model | Working as designed — see [LOCKDOWN.md](LOCKDOWN.md). |
| Empty response, `finish_reason: "length"` | Reasoning consumed the output budget. Raise `maxTokens` or keep thinking off. |
| Chats fine, never edits files | No `tool_calls` from the backend. Test the gateway directly (verify step 3). |
| 400s partway through a session | `contextWindow` set higher than the model supports. |
| `pi -p "..."` hangs at a prompt | Not a bug: print mode reads stdin and a terminal never sends EOF. The launcher closes stdin when it is a TTY; if you bypass the launcher, add `< /dev/null`. |
| `pi -p "..."` reports a command or edit refused, or the agent says it may not run anything | Manual mode, where new sessions start (or read-only-auto): a one-shot run has nobody to ask, so whatever would ask is refused. `pi --auto -p "..."` for that run, or `/mode auto` then **Change default mode** in a session to start in auto from now on. |
| `pi: this machine is busy ...` | Informational. It starts anyway, just slowly. `PI_FORCE=1` silences it. |
| `pi: the folder this shell is in has been deleted` | The shell is still in a folder that was removed (by `rm -rf`, a branch switch or a rebuild), even if a new one now exists at the same path. `cd "$PWD"` re-enters the new one; otherwise `cd` somewhere that exists. There is no override. |
| `pi: not starting in /Users/you - your home folder` | The folder pi starts in is the project, and nothing inside it is asked about, so home, `~/Documents`, `/` and credential folders such as `~/.ssh` are refused. `cd` to a project folder (or `mkdir ~/scratch` for a quick question). `PI_FORCE=1` starts there anyway. The list is `untrustedFolders` in `config/elm-pi.json`. |
| On a remote host, `/copy` or a selection never reaches your own clipboard | The launcher sends every copy through the terminal as OSC 52, and the terminal must accept it: iTerm2 needs *Settings > General > Selection > Applications in terminal may access clipboard*, tmux needs `set -g set-clipboard on`, and Terminal.app does not support it at all. Allow writes only, never reads. Copies over ~75 KB do not fit in OSC 52. To paste, use the terminal's own paste (Cmd+V): pi's Ctrl+V reads the clipboard of the machine pi runs on, which over SSH is the remote one. `PI_CLIPBOARD_OSC52=0` turns the OSC 52 copy off. |
| `env: node: No such file or directory` | Launcher bypassed, or `.node/` missing — re-run `./bootstrap.sh`. |
| `this system has no /lib64/ld-linux-x86-64.so.2` (or `/lib/ld-linux-aarch64.so.1`), or `cannot execute: required file not found` | NixOS without nix-ld, or a musl system such as Alpine. See [Linux distributions](#linux-distributions). |
| `/bin/bash: No such file or directory` running the install command | NixOS: start it with `bash -c "$(curl ...)"` instead. |
| Llama sub-agents unavailable | The shim could not start (pi shows an `elm-shim:` warning), usually because port 8811 is taken. `ELM_SHIM_PORT` moves it; the macOS network profile allows all of the machine's loopback, so any port works. |
| `pi: ⚠  WARNING - this session is NOT fenced by the OS` | This machine could not make the OS fence, so the session started without it: the proxy still filters what well-behaved programs reach, and a program that ignores proxy settings is not stopped. The lines under the warning say why. Linux fences a session in a user and network namespace; Ubuntu 23.10 and later keep those from unprivileged programs through AppArmor, and an administrator allows them with `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` (and a file in `/etc/sysctl.d/` to keep it). WSL 1 has no namespaces at all: `wsl --set-version <distribution> 2` from Windows. `bootstrap.sh` says the same at the end of an install on such a machine. `pi --offline` is refused there until the fence works; `ELM_PI_NO_JAIL=1 pi ...` runs unfenced without the warning. |
| `missing required tool(s): curl` from `bootstrap.sh` | Ubuntu ships without curl: `sudo apt install -y curl`, then run it again. Nothing was downloaded. |
| A website built by the agent is not reachable in your browser | Have the server bind `127.0.0.1:$ELM_PI_PREVIEW_PORT` and open the URL elm-pi reports. Linux bridges only that port out of its network namespace; set `ELM_PI_PREVIEW_PORT` before starting pi to request a fixed port. An explicitly occupied port is refused rather than exposed differently. |
| Sub-agents fail to start, or something reports `pi: command not found` | pi-subagents falls back to a bare `pi` on PATH when it cannot resolve the CLI. Fixed three ways — the launcher exports `PI_SUBAGENT_PI_BINARY`, `bootstrap.sh` creates `agent/bin/pi`, and the installer links `~/.local/bin/pi`. Re-run `./bootstrap.sh` if `agent/bin/pi` is missing. |
| `pi: command not found` in a new shell | The installer adds `~/.local/bin` to your shell profile; open a new shell, or `export PATH="$HOME/.local/bin:$PATH"` for the current one. |
| `pi` runs something other than this install | Another `pi` is earlier on PATH — the installer warns when it sees one. `command -v pi` shows which wins; either remove it or put `~/.local/bin` ahead of it. |
| Want vanilla pi, to tell wrapper bugs from pi bugs | `~/.local/share/elm-pi/pi.orig`. It is the unwrapped CLI with pi's own `~/.pi` config, so it starts with no models until you configure one. |
| Startup hangs with no output at all | Seen in clusters, cause unknown; ruled out config, extensions, the launcher, ELM itself and leftover processes. Wait and retry rather than changing config — a change made during a bad window will look causal and is not. |
