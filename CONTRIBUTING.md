# Contributing to elm-pi

The repository is both source code and an installer. Changes should leave a fresh
install reproducible, an existing install upgradeable, and the ELM-only policy
intact.

## Before a commit

```bash
./scripts/check.sh
```

This runs Bash and Python syntax checks, unit and policy tests, ShellCheck when it
is installed, and TypeScript checking when the locked development tree is present.
CI runs the same checks on Linux and macOS.

## Sources of truth

- `config/elm-pi.json`: Node version, model defaults, allowed and built-in
  providers, scrubbed credential variables, web-tool names and required local
  extensions.
- `package.json`: pi and development tooling.
- `templates/packages.json`: pi extensions.
- `templates/`: generated agent code and initial configuration. Model strings use
  `@QWEN_MODEL@` and `@LLAMA_MODEL@`; `scripts/elm_config.py` renders them.

Do not edit generated files under `agent/` as the durable version of a change.

## Updating npm dependencies

Both manifests ask for `latest` and no lockfiles are committed. What an install
gets depends on how it was asked:

- **`--update`**, which is what `pi update` runs: the latest of every direct
  dependency, as published now.
- **Anything else** - a fresh install, `--force`, `pi update --extensions`, a
  re-run that rebuilds a tree: the direct dependencies listed in
  `config/versions.json`, the versions this repo last ran its checks against.
  A dependency the file does not list resolves to `latest`. `PI_VERSION=x.y.z`
  overrides pi for one run.

Adding a package is one line in `templates/packages.json`, plus `npm:<name>`
in `templates/settings.json` if pi should load it as an extension.

```bash
./bootstrap.sh --update      # re-resolve and reinstall both trees
```

`--update` and `--force` are the only things that move an existing install
forward: the manifest digest in `node_modules/.elm-pi-lock.sha256` skips the
reinstall when the dependency list has not changed, and it cannot see `latest`
moving on the registry.

An update is kept only if it passes the run's checks: pi has to load
`agent/models.json` with Qwen in it, and both config files have to match the
schemas the new pi ships (`scripts/check_config.py`). Otherwise the previous pi
and extension trees are put back. Each run that passes writes the exact
versions it is running to `agent/installed-versions.json`. To move the tested
set forward, update a checkout, try it, and commit what it recorded:

```bash
./bootstrap.sh --update && ./scripts/check.sh
cp agent/installed-versions.json config/versions.json
```

Runtime installs use `npm install --ignore-scripts`. The one package script
explicitly re-enabled is the `better-sqlite3` native rebuild in the staged
extension tree.

What this trades away, deliberately: transitive dependencies are not pinned, so
a build is still not exactly reproducible, a bad upstream release can reach an
install on its next `pi update` - though one that breaks the config is rolled
back rather than kept - and nothing enforces
a minimum version of a transitive dependency. `npm audit` is no longer run by
the checks or by CI. If any of that becomes a problem, the mechanism to restore
is in git history before this change: exact versions in both manifests, committed
lockfiles, `npm ci`, `scripts/repair-transitives.sh`, `scripts/audit.sh`, and the
two tests that enforced them.

## Updating models or policy

Change `config/elm-pi.json`, not the rendered environment or generated agent files.
`configure.sh` records a gateway-resolved Qwen id in `agent/model-ids.json` and
updates every runtime consumer through `scripts/elm_config.py`.

When pi adds or renames a provider, `tests/test_project.py` fails and names it;
add its id to `builtinProviders` and its credential environment variables to
`providerCredentials`, as described in `LOCKDOWN.md`.
