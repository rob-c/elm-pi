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
- `package.json` plus `package-lock.json`: pi and development tooling.
- `templates/packages.json` plus `templates/packages-lock.json`: pi extensions.
- `templates/`: generated agent code and initial configuration. Model strings use
  `@QWEN_MODEL@` and `@LLAMA_MODEL@`; `scripts/elm_config.py` renders them.

Do not edit generated files under `agent/` as the durable version of a change.

## Updating npm dependencies

Change an exact version in the appropriate manifest, regenerate its lockfile, and
run the complete checks. Never use `latest`, caret or tilde ranges in a committed
manifest.

Core and development tree:

```bash
PATH="$PWD/.node/bin:$PATH" npm install --package-lock-only --ignore-scripts
```

For the extension tree, copy `templates/packages.json` to a temporary directory
as `package.json`, run the same lock-only command there, and copy the resulting
`package-lock.json` to `templates/packages-lock.json`.

Runtime installs use `npm ci --ignore-scripts`. The only package script explicitly
re-enabled is the `better-sqlite3` native rebuild in the staged extension tree.
After `npm ci`, run `./scripts/repair-transitives.sh node_modules`; bootstrap and
CI already do this. It replaces only vulnerable copies nested by a dependency's
published shrinkwrap, using separately integrity-locked direct dependencies.

Both manifests also carry reviewed transitive security overrides. The pi package
publishes its own shrinkwrap, so a plain lockfile regeneration can reintroduce an
older nested dependency even when the root override is present. The project tests
enforce the safe versions. After regenerating either lockfile, run the full checks,
`npm audit`, and a clean `npm ci`; do not accept a lockfile that lowers one of
those enforced versions.

`npm run audit:locks` checks both runtime lockfiles against npm's advisory
service. It is intentionally separate from `./scripts/check.sh`, so the normal
local test suite remains deterministic and usable offline; CI runs both.

## Updating models or policy

Change `config/elm-pi.json`, not the rendered environment or generated agent files.
`configure.sh` records a gateway-resolved Qwen id in `agent/model-ids.json` and
updates every runtime consumer through `scripts/elm_config.py`.

When pi adds a provider, add its id and credential environment variables to the
manifest, then run the policy inventory and checks described in `LOCKDOWN.md`.
