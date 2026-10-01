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

Both manifests ask for `latest` and no lockfiles are committed, so every install
resolves whatever the registry currently publishes. Adding a package is one line
in the appropriate manifest, plus `npm:<name>` in `templates/settings.json` if pi
should load it as an extension.

```bash
./bootstrap.sh --update      # re-resolve and reinstall both trees
```

`--update` and `--force` are the only things that move an existing install
forward: the manifest digest in `node_modules/.elm-pi-lock.sha256` skips the
reinstall when the dependency list has not changed, and it cannot see `latest`
moving on the registry.

Runtime installs use `npm install --ignore-scripts`. The one package script
explicitly re-enabled is the `better-sqlite3` native rebuild in the staged
extension tree.

What this trades away, deliberately: a build is no longer reproducible, a bad
upstream release reaches every install on its next update, and nothing enforces
a minimum version of a transitive dependency. `npm audit` is no longer run by
the checks or by CI. If any of that becomes a problem, the mechanism to restore
is in git history before this change: exact versions in both manifests, committed
lockfiles, `npm ci`, `scripts/repair-transitives.sh`, `scripts/audit.sh`, and the
two tests that enforced them.

## Updating models or policy

Change `config/elm-pi.json`, not the rendered environment or generated agent files.
`configure.sh` records a gateway-resolved Qwen id in `agent/model-ids.json` and
updates every runtime consumer through `scripts/elm_config.py`.

When pi adds a provider, add its id and credential environment variables to the
manifest, then run the policy inventory and checks described in `LOCKDOWN.md`.
