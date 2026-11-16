"""The launcher's own --help text, word for word.

It is printed before pi's own, and it is the only place a researcher sees what
--fast, --remote or the permission modes do without reading INSTALL.md. The
text is kept identical to the one the reference launcher (pi.bash) prints:
tests/test_python_launcher.py fails if the two drift, because the documentation
tests check that copy against README.md and INSTALL.md, and a second copy that
quietly said something else would be worse than none.

`pi --help` runs this and then hands pi's half its own --help, so the two halves
read as one page.
"""

USAGE = """\
elm-pi: pi wired to the University's ELM gateway. Models are ELM-only - see
LOCKDOWN.md for what that blocks and how to lift it.

Flags added by this launcher:
  --fast              load only the local extensions and the permission gate:
                      no sub-agents, web access or anchor editing. Much
                      quicker to start
  --llama             run on Llama 3.3 70B through the tool-call shim
  --mistral           run on Mistral Small 4 119B, ELM's other model with
                      tool calling and images; Qwen stays the default
  --no-workflows      leave the `workflow` tool (pi-dynamic-workflows) out of
                      this run; it is offered by default
  --workflows         offer it even where PI_ELM_WORKFLOWS=0 leaves it out
  --with-all          every optional extra: sets up the agent's Python and the
                      offline PyPI index if they are not installed (once, ~2GB),
                      and offers every tool left out for size. Not --remote:
                      the web, the open proxy and computer use stay off
  --remote            allow this run to reach the internet: the web tools come
                      back on and the egress proxy records every destination
                      instead of refusing all but the ELM gateway and the
                      package sources (PyPI, conda-forge, container
                      registries). The model is not affected - inference still
                      goes to ELM and nowhere else, and no other provider
                      becomes reachable. The model is told to research with
                      the web tools rather than answer from memory
  --no-computer-use   with --remote, the web but not the screen: computer use
                      (seeing the screen, driving apps) stays off
  --help, -h          this text, then pi's own

Permission modes - how much the agent may do without asking:
  --manual            nothing runs without your yes: commands, edits, Python,
                      sub-agents and every other tool ask first; reading
                      files in the project does not. Where every new
                      session starts, unless auto has been made the default
  --read-only-auto    manual, except that a shell command which can only read,
                      and only inside the project (ls, cat, grep, find, cd
                      into it), runs without asking; everything that
                      changes something still asks
  --auto              the permission gate's rules: most commands and edits in
                      the project run, the risky ones (git push, sudo,
                      brew install, ...) ask first
  --yolo              every ask is answered yes, for this session only; a
                      deny is still a deny. Never saved, never the default
  A flag sets the mode for one run and leaves the default alone. In a session,
  /mode opens a menu of the modes: manual, read-only-auto or auto then offers
  "Change for this session" or "Change default mode" (saved in
  agent/permission-mode); yolo
  offers only "Change for this session only". Sub-agents run in their session's mode and
  ask through it. PI_ELM_PERMISSION_MODE set in the environment can only make a
  run stricter.

pi's own subcommands (auth, mcp, config, list, install, remove, update
--models) are not available: the key, packages and models are this install's.

Optional parts, added or taken back (recorded, so pi update keeps the choice):
  pi setup --no-python      remove the agent's own Python - uv-managed CPython with
                            numpy, scipy, pandas, matplotlib, Jupyter tools... (~1GB),
                            part of every install otherwise - and the index
  pi setup --python         put the agent's Python back
  pi setup --pypi-index     offline PyPI search, `pypi-search` (~1GB download,
                            ~390MB kept); adds --python
  pi setup --no-pypi-index  remove the index
  pi setup --all            both (what pi --with-all sets up before starting)

Useful environment:
  PI_ELM_WEB=1              web tools for one run, without opening the proxy
  PI_ELM_WORKFLOWS=0        leave the workflow tool out (the same as --no-workflows)
  PI_ELM_BANNER=0           no "Powered by ELM" banner when a session starts
  ELM_PI_PROXY_ALLOW=a,b    let this run reach these hosts as well
  ELM_PI_NO_PROXY=1         run unproxied (debugging)
  ELM_PI_NO_JAIL=1          run without the OS network fence (debugging)
  ELM_PI_PREVIEW_PORT=8765  host-loopback port for a web UI built in the session;
                            Linux chooses a free port when this is unset
  PI_ELM_NETWORK=offline    offline, trusted-remote or yolo, as a default for
                            every session started from this shell
  ELM_PI_SHARED_STATE=1     preserve existing shared session/memory permissions
  ELM_PI_ALLOW_EXTERNAL_MODULES=1
                            let pi load packages from node_modules outside this
                            install, which it otherwise refuses (debugging)
  PI_ELM_UNLOCK=1           lift the credential scrub and the argument guard
                            (which also refuses -e/--extension)
  PI_FORCE=1                start in home or another folder that is not a project, and
                            skip the busy-machine and inside-the-install warnings
  PI_ELM_STARTUP_CHECKS=1   restore pi's own startup network checks
  PI_CLIPBOARD_OSC52=0      copy to this machine's clipboard only, not also
                            through the terminal (on by default, for remote hosts)

Network modes - what this session may reach, and what the OS enforces:
  --offline           the ELM gateway only: no web tools, no PyPI, no package
                      registries, and no packet to anything but this install's
                      egress proxy, enforced by the OS
  --trusted-remote    the gateway, the package sources and the search providers
                      this install allows (proxyAllow in config/elm-pi.json),
                      through the proxy, with the OS allowing nothing else.
                      The default
  --remote            now the same as --yolo: every destination and every
                      protocol, for this session only, with the proxy recording
                      rather than gating and no OS fence. Never saved

pi's own flags follow.
"""


def optional_parts_section():
    """The `pi setup` part of the help, as `pi setup` with no flags prints it.

    The bash launcher pipes its help through `sed -n '/^Optional parts/,/^$/p'`,
    which prints the closing blank line as well; this is the same slice, taken
    from the same text rather than from a second copy of it.
    """
    lines = USAGE.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Optional parts"))
    end = next((i for i in range(start, len(lines)) if not lines[i]), len(lines))
    return lines[start:end + 1]
