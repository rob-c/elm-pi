"""The installer's --help, word for word.

bootstrap.sh generates it from a heredoc in `usage()`; this is that text, copied
by tests/test_bootstrap_python.py (which reads the heredoc back) so the two
implementations cannot print two different pages.
"""

USAGE = """\
elm-pi installer. Installs into this directory; nothing goes system-wide.

  ./bootstrap.sh                  install everything, prompt for the ELM key
  ELM_API_KEY=elm-... ./bootstrap.sh --non-interactive

  --non-interactive   take the key from $ELM_API_KEY, never prompt
  --update            refresh pi, packages and extensions; keep your configs
  --force             re-download the tools and reinstall the npm packages
  --force-packages    reinstall the extension packages at the tested versions,
                      and pi too if it is not at its tested version

  --no-packages       pi only: no sub-agents, web access or anchor edit
  --no-tools          no bundled fd/rg/jq/yq/shellcheck/ast-grep/uv/mlr/resvg/pixi/ruff
  --no-python         no agent's Python: leave out (or remove) agent/python, the
                      uv-managed CPython and analysis stack every install has by
                      default (~1GB), and the index with it; `pi setup --no-python`
  --with-python       take --no-python back; `pi setup --python`
  --with-pypi-index   an offline search index of PyPI for the agent, `pypi-search`
                      (downloads ~1GB once, keeps ~390MB); implies --with-python
  --with-all          every optional part: --with-python and --with-pypi-index
                      (recorded as those two; nothing here opens the network -
                      that is `pi --remote`, per run); `pi setup --all`
  --no-pypi-index     take --with-pypi-index back, removing the index
  --no-skill-library  no K-Dense scientific-agent-skills in agent/skills/kdense
                      (a 245MB download once; the skills kept are 24MB);
                      --with-skill-library takes it back
  --no-shim           skip the Llama tool-call shim
  --no-patch          leave pi as shipped: /share, /bug and its subcommands stay,
                      and the permission gate runs in auto mode only
  --no-auth-lock      leave agent/auth.json writable, so /login works
  --reset-options     forget the --no-* flags and ELM_PI_TOOLS earlier runs
                      recorded, and use only what this run is given
  -h, --help          this text

The --no-* and --with-* flags and ELM_PI_TOOLS are recorded in agent/install-options and
repeated by every later run - pi update, pi update --extensions, re-running
the installer - so an update keeps the install you chose.

Environment: ELM_PI_PYTHON, ELM_PI_BUNDLED_PYTHON, ELM_PI_NODE_VERSION, ELM_PI_NPM_USERCONFIG,
PI_VERSION, ELM_PI_TOOLS, FD_VERSION, RG_VERSION, JQ_VERSION, YQ_VERSION,
SHELLCHECK_VERSION, ASTGREP_VERSION, UV_VERSION, MLR_VERSION, RESVG_VERSION,
PIXI_VERSION, RUFF_VERSION.

Your shell's conda/venv/pyenv Python, nvm/volta/Homebrew Node, node_modules
elsewhere on the machine, ~/.npmrc, ~/.npm and
PYTHON*/NODE_*/npm_config_* variables are ignored: see lib/sandbox.sh.
"""
