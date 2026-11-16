# The launcher

This package is what `pi` runs. The install's `pi` is a dozen lines of bash that
find the install and hand over; `python/pi` beside this file chooses an
interpreter and starts `python/elmpi` with nothing of the account's Python in
reach; `python/elmpi` decides everything else - what a session may reach, which
extensions load, where transcripts go, what environment pi starts with.

The bash implementation it replaced is `pi.bash` in the install root: the
reference, not installed. Its guarded hand-over shares the Python jail helper.
`tests/test_python_launcher.py` runs both on the same install and compares exit
codes, pi's arguments, its whole environment and both streams, case by case.

```sh
pi --help                         # the launcher's help, then pi's
pi -p "what does this regex do?"
pi --fast --manual -p x           # a quick, fully asking run
./pi.bash -p "the same, as it was"   # the reference implementation
```

## The installer is here too

`python/elmboot` is what `bootstrap.sh` runs. `bootstrap.sh` is now a hand-over
of the same kind as `pi`: it finds an interpreter with `lib/sandbox.sh` - the
one named, else the one the install recorded, else the system's, else a
standalone CPython it downloads into `.python`, which is the one step that has
to be shell because there is no Python yet - and execs
`python/elmboot/__main__.py` with `-E -s -S -B -u`. The installer it replaced is
`bootstrap.bash`: the reference, which nothing runs.

`elmboot/cli.py` is the order of an install; each phase is the module named
for it (`elmboot/__init__.py` lists them). Downloads are still `curl`, with the
retry flags the machine's curl has, so a proxy, a CA bundle and a mirror behave
as they did; archives are checked with `hashlib` and unpacked by the system's
`tar` first, Python's `tarfile`/`zipfile` where that fails. `elmboot/run.py` is
`set -e` and the EXIT trap: a command that fails ends the run with its status,
and the pi release and extension tree a failed run replaced are put back.

Held to the reference three ways: `tests/test_bootstrap_python.py` runs both
on the same tree for the options, the environment, `agent/` and the settings
merges; `tests/test_bootstrap_installer.py` runs the reference's own tables of
cases - forty for a tool install, fourteen for the Node download, the pi
rebuild rules - through the Python phases with the same checks; and a full
install by each, in two folders, is compared line for line and file for file.

## The two shells, and the clean room behind them

`pi` is the only shell at the top, and its whole job is path resolution: find
the install through symlinks (the installer links `~/.local/bin/pi`, and that
link may itself be a link), and `exec` `python/pi`, refusing with a sentence if
the install has no `python/`.

`python/pi` is the only shell in this package, and it does three things: it
finds an interpreter, it starts it isolated, and it execs it.

```sh
exec "$PYTHON" -E -s -S -B -X utf8 "$PACKAGE_DIR/elmpi/__main__.py" "$@"
```

- `-E` - no `PYTHON*` variable is read, so `PYTHONPATH` and `PYTHONHOME` cannot
  reach it. The variables stay in the environment: they are the researcher's,
  and the agent's shell runs their project with them, as under `pi.bash`.
- `-s` - no user site directory.
- `-S` - no site-packages and no `.pth` file: nothing installed in the system,
  in conda or in a virtualenv is importable. The package is stdlib-only, so
  nothing needs them.
- `-B` - no `__pycache__` written inside the install.
- `-X utf8` - the same decoding whatever the account's locale is.

`elmpi/__main__.py` then removes the one `sys.path` entry that depends on where
the launcher was started from (Python puts the script's own directory first), so
a `json.py`, `os.py` or `sitecustomize.py` in the folder the agent is working on
cannot be imported by the code that decides what the agent may do.

The interpreter is `ELM_PI_PYTHON`, else the one bootstrap.sh recorded in
`agent/python-path`, else the first that starts from the system folders, the
install's own `.python`, then the absolute entries of `PATH` - never a relative
entry (a project's `./python3`), a folder, or a version manager's shim; anything
older than 3.8 is refused with a message rather than a traceback. `elmpi/interpreter.py`
has the full selection the bash launcher's `elm_select_python` does, including
the rule that conda, virtualenv and pyenv interpreters are never used silently.

## Where each decision lives

The blocks are the bash launcher's, in the same order; `elmpi/cli.py` is the
order itself.

| module | its job | in `pi.bash` |
| --- | --- | --- |
| `pi` (install root) | find the install, exec `python/pi` | the shebang and `HERE` |
| `python/pi` | find an interpreter, exec it isolated | `elm_select_python` at its shell level |
| `elmpi/__main__.py` | a safe import path, then hand over | - |
| `elmpi/cli.py` | the launch, in the order it has to happen | the whole script |
| `elmpi/console.py` | stdout for answers, stderr for everything else | `echo`, `printf` |
| `elmpi/errors.py` | a refusal's lines and exit code | `echo ... >&2; exit N` |
| `elmpi/paths.py` | what a folder's path really is, the entry point | `HERE`, `elm_policy_canonical`, `elm_normalize_session_dir` |
| `elmpi/environ.py` | the environment, PATH cleaning, `.env` as data | `elm_clean_path`, `elm_load_dotenv` |
| `elmpi/runtime.py` | `agent/runtime.env` | `. "$HERE/agent/runtime.env"` |
| `elmpi/interpreter.py` | which Python, and which not | `elm_select_python` |
| `elmpi/toolchain.py` | the agent's Python, pixi, private `TMPDIR`, the paths extensions read | the block after `elm_select_python` |
| `elmpi/argwalk.py` | pi's argument grammar: which options take a value | `elm_policy_takes_value` in `lib/policy.sh` |
| `elmpi/flags.py` | this launcher's own flags | `FAST=0; LLAMA=0; ...` and its loop |
| `elmpi/policy.py` | the ELM-only provider guard | `elm_policy_check_args` in `lib/policy.sh` |
| `elmpi/credentials.py` | the credential scrub | the `PI_ELM_UNLOCK` block |
| `elmpi/untrusted.py` | folders a session must not start in | `elm_untrusted_folder` in `lib/policy.sh` |
| `elmpi/banner.py`, `banner_text.py` | the "Powered by ELM" banner | the `ELM_BANNER` heredoc |
| `elmpi/extensions.py` | policy extensions, `--fast`, `--no-extensions` | `POLICY_EXTENSIONS`, `add_policy_extensions` |
| `elmpi/tools.py` | the tools left out of every request | the "web tools off by default" block |
| `elmpi/modes.py` | permission modes | the permission mode block |
| `elmpi/state.py` | transcripts: where, and how protected | `.pi/.gitignore`, the session dir block, `lib/state.sh` |
| `elmpi/proxy.py` | the egress proxy: adopt, start, keep alive | the egress proxy block |
| `elmpi/network.py`, `jail.py` | network mode, then the macOS sandbox or Linux namespace | the network mode block and shared Python hand-over |
| `elmpi/netns.py`, `relay.py` | Linux loopback-to-host proxy transport and host-to-loopback web-preview bridge | shared Python hand-over |
| `elmpi/preflight.py` | a saturated machine | the load preflight |
| `elmpi/updates.py` | `pi update`, `pi setup`, `--with-all` | the three intercepts |
| `elmpi/launch.py` | the hand-over to `pi.orig` | the stdin guard and the final `exec` |
| `elmpi/usage.py` | `--help` | `elm_usage()` |

## DNS stays on the host

The launcher starts `proxy/egress.py` before applying the OS fence. The proxy
checks each destination against the allowlist, then uses Python's
`socket.create_connection`, which calls the host's `getaddrinfo`. macOS keeps
its system resolver, including VPN/scoped DNS; Linux keeps its host resolver
and NSS configuration, including local host mappings and resolver stubs.
The launcher does not copy DNS settings into the jail, parse `resolv.conf`,
pin resolved addresses, or select a public resolver. Resolver errors are
logged as `FAILED`; there is no alternate public-DNS fallback.

On macOS the session reaches the proxy on the machine's loopback, the one
place its fence lets it connect to.
On Linux a loopback listener inside the empty network namespace relays bytes
over a Unix socket to the host-side proxy. Both send the original hostname in
HTTP CONNECT or an absolute HTTP URL, so neither needs DNS inside the jail.
Clients must honour the proxy settings; raw hostname connections inside the
jail are not the supported route out.

A nested session reuses an inherited loopback proxy only when its health
document reports the exact allowlist and upstream-proxy state the child needs.
This keeps ordinary sub-agents on one stable port without letting an offline
child inherit a trusted or open parent's broader policy. When policies differ
and the parent is not fenced (`--remote`, `ELM_PI_NO_JAIL=1`), the child starts
a separately scoped proxy and preserves the original corporate upstream
recorded by its parent.

Inside a fenced session there is no second proxy to start: it would be inside
the fence too, with that session's proxy as the only way out. A fenced session
exports `ELM_PI_FENCED` (its proxy's port; an internal launcher marker, not a
user setting), and a launch that finds it either uses the session's proxy -
asked three times, so one health check missed on a busy machine does not end a
sub-agent - or refuses in a sentence: a run started inside a session keeps that
session's network mode and hosts. On macOS such a launch also keeps the
session's fence rather than asking for one of its own: macOS applies a second
profile only when it is identical to the first, and a launch from another
folder writes a different one. The marker alone is not believed - the launcher
checks that it really is sandboxed, and applies its fence as usual if not.

On Linux the namespace is entered without `unshare --fork`, so the pid the
launcher was started as is pi's own: a `kill` of it reaches the session, and
the proxy's watchdog and both relays follow the process they are named for.

## A machine that cannot make the fence

`jail.unavailable()` is asked early, by both launchers (`pi.bash` through
`launch.py --fence-check`), so that a machine without a fence is a decision
rather than a failed exec. Offline is refused (`jail.refusal()`); any other
mode starts unfenced behind its proxy with `jail.warning()` printed under the
network line, `ELM_PI_NO_JAIL=1` set for everything the session starts - which
is why nothing started from it is asked or warned again - and
`ELM_PI_UNFENCED=fallback` as the marker the `/network` extension reads. No
warning is printed when unfenced was the request: yolo, `ELM_PI_NO_JAIL`,
`ELM_PI_NO_PROXY`. `bootstrap.sh` prints the same reason at the end of an
install.

## The saved default, and `/network`

`network.resolve()` reads, in order: this run's flag, `PI_ELM_NETWORK`,
`agent/network-mode` (what `/network` saved), then trusted-remote; a session
is told the saved default as `PI_ELM_NETWORK_DEFAULT`. The extension tightens
a running session through the proxy's `POST /__elm_pi_egress__/narrow?allow=`,
which keeps only hosts the proxy already allows and so needs no secret; there
is no route that widens a list.

## What the macOS fence leaves open

All of this machine's loopback, and Unix sockets under the session's `TMPDIR`
(when it is this account's alone) and its project folder. Limited to the
proxy's port and the shim's, as it first was, a session could not reach what
it had started: `curl` to its own server was refused, a Jupyter kernel never
answered, `multiprocessing.Manager` could not bind. The cost is that another
program listening on `127.0.0.1` is reachable from a session on macOS; on
Linux the namespace's loopback is its own. Nothing off the machine is
reachable, DNS included, and `/tmp` - where launchd keeps ssh-agent's socket -
is not one of the folders. `tests/test_fenced_launch.py` runs each of those
under the real profile.

When an upstream HTTP proxy is configured, this host resolves only the
upstream proxy's name. The original destination name is forwarded unchanged
for that proxy to resolve. Host/VPN DNS changes are handled by the OS on new
connections; existing tunnels keep their established connection.

`tests/test_host_dns.py` checks host resolution, resolver failures without
fallback, and upstream resolution using only local sockets.
`tests/test_network_modes.py` also sends a site-only name through a real macOS
sandbox to the host proxy. Its probe of an address off the machine expects the
fence's own immediate refusal (EPERM), which a site's external firewall cannot
produce, so a broken jail cannot look correct.
The Linux launcher verifies both sides of its relay against the proxy health
endpoint before exec, and each relay exits with pi; a dead relay therefore
fails the launch instead of producing a later model connection error.

The reverse direction is deliberately narrower: one server bound to
`127.0.0.1:$ELM_PI_PREVIEW_PORT` can be opened by the user at the same
host-loopback URL. Linux assigns a free port when none was requested, starts a
host TCP-to-Unix relay and an inside Unix-to-TCP relay, and exports the chosen
port before pi starts. This is inbound only and grants the namespace no route
back to the host or network. macOS needs no relay because its sandbox shares
the host network namespace while restricting outbound destinations.
`ELM_PI_PREVIEW_BRIDGED=1` is an internal launcher marker used only so the
server reaper can explain when a Linux server chose a different, unexposed
port; it is not a user setting.

## What is deliberately different

- **`agent/runtime.env` is parsed, not sourced.** The bash launcher sources it
  and would run anything appended to it. Here it is `export NAME=value` data,
  read with `shlex` - the file is generated by `scripts/elm_config.py`, so the
  values are the same, and nothing in it can execute.
- **`lib/*.sh` is not required.** The logic those files hold lives in this
  package; an install whose `lib/` was lost can still start this launcher, and
  `--help` still works.
- **Sub-agent children and `--with-all` use the install's `pi`**, the same
  command a person runs; the reference points both at `pi.bash`, which is why
  the comparison normalises that one value.
- **The proxy watchdog is a forked child** of the launcher rather than a bash
  subshell. It follows the same pid (`exec` keeps it), on the same port, with
  the same two-miss patience.

Everything a caller can observe - the arguments pi receives, the environment it
inherits, every line on both streams and every exit code - is the same. That is
what `DifferentialTests` checks, case by case, against the bash launcher.

## How it is held to the reference

```sh
python3 -m unittest tests.test_python_launcher -v
```

- `ReferenceTests` and `ReferenceDeletedFolderTests` run the functional cases
  in `tests/test_install_fixes.py` against `pi.bash` - the same test bodies,
  not a copy. The same bodies run against the installed `pi` there, so both
  implementations answer every case.
- `DifferentialTests` runs both launchers on identical installs and compares
  the exit code, pi's arguments, the environment it inherits, stdout and
  stderr.
- `DriftTests` reads the lists back out of `pi.bash` - the `--fast`
  conveniences, the permission modes and their ranking, the refused
  subcommands, the flags, the folder-refusal wordings - so a change there that
  the Python launcher did not follow is a failing test.
- `LauncherTextTests` compares the help text and the banner byte for byte.
- `IsolationTests` holds both shells to what they claim: path resolution and
  isolation flags only, no import from outside the package and the stdlib, and
  a launch a hostile `PYTHONPATH` or a project folder with a `json.py` in it
  cannot change.
