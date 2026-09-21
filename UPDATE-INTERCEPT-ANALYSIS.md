# Analysis: Intercepting `pi update` for elm-pi

## Current State

### i) Version Pinning Issue

**Current behavior:**
- `package.json` pins pi to `"^0.85.1"` (line in templates/package.json)
- `bootstrap.sh` has `PI_VERSION="${PI_VERSION:-^0.85.1}"` (line 18)
- Running `pi update --self` would update to latest pi from npm, **not** from GitHub

**Problem:**
The elm-pi project wants to track the **latest main branch from GitHub**, not a frozen npm version. The current setup:
1. Installs pi via npm in `bootstrap.sh` line 73: `npm install`
2. Uses npm semver range `^0.85.1` which only updates within minor versions
3. Does not automatically pull latest GitHub commits

### ii) Intercepting `pi update`

**Current pi update flow:**
When user runs `pi update`:
1. pi's `package-manager-cli.js` detects `--self` flag
2. Checks for managed install (`PI_MANAGED_INSTALL_ROOT` env var)
3. If managed, downloads from `https://pi.dev/api/installer/releases`
4. If not managed, runs npm/yarn/pnpm global update command
5. `--extensions` flag updates npm packages in `agent/npm/`

**What we need:**
1. Capture `pi update` (with no flags or `--self`) → re-run GitHub install script
2. Allow `pi update --extensions` → pass through to pi's normal update
3. Allow `pi update --models` → pass through to pi's normal update

## Required Changes

### 1. Modify the `pi` Wrapper Script

**File:** `/Users/rcurrie/src/elm-pi/pi`

**Change:** Add command interception before handing off to `pi.orig`

```bash
# --- intercept 'pi update' ---------------------------------------------------
# When invoked with 'update' (no --extensions/--models), re-run the GitHub
# installer to get latest elm-pi + pi, not just pi from npm.
INTERCEPT_UPDATE=1  # enable by default

if [ "$INTERCEPT_UPDATE" = "1" ]; then
    # Check if this is a bare 'pi update' or 'pi update --self'
    # but NOT 'pi update --extensions' or 'pi update --models'
    HAS_EXTENSIONS=0
    HAS_MODELS=0
    HAS_OTHER=0
    
    for arg in "$@"; do
        case "$arg" in
            --extensions) HAS_EXTENSIONS=1 ;;
            --models) HAS_MODELS=1 ;;
            update|--self) ;;  # these are OK
            -*) HAS_OTHER=1 ;;  # other flags present
        esac
    done
    
    # Intercept if: first arg is 'update', and no --extensions/--models
    if [ "${1:-}" = "update" ] && [ "$HAS_EXTENSIONS" = "0" ] && [ "$HAS_MODELS" = "0" ]; then
        echo "pi: updating elm-pi from GitHub (latest main branch)..." >&2
        echo "    This updates both elm-pi and the pi package." >&2
        echo "    For pi-only updates: pi update --extensions" >&2
        echo "" >&2
        
        # Re-run the bootstrap script with --update flag
        # This pulls latest from GitHub and re-installs everything
        exec "$HERE/bootstrap.sh" --update --non-interactive
    fi
fi
# ---------------------------------------------------------------------------
```

**Placement:** Insert this block after the ELM-only policy section (around line 140) and before the stdin guard section.

### 2. Update `bootstrap.sh` to Always Install Latest Pi

**File:** `/Users/rcurrie/src/elm-pi/bootstrap.sh`

**Current line 18:**
```bash
PI_VERSION="${PI_VERSION:-^0.85.1}"
```

**Change to:**
```bash
# Always install latest pi from npm (no version pin)
# Set PI_VERSION to a specific version only if you need to freeze it
PI_VERSION="${PI_VERSION:-latest}"
```

**Current line 73:**
```bash
npm install --no-audit --no-fund --loglevel=error
```

**This already respects the version in package.json, so we need to also update templates/package.json:**

### 3. Update `templates/package.json`

**File:** `/Users/rcurrie/src/elm-pi/templates/package.json`

**Current:**
```json
{
  "name": "elm-pi-agent",
  "private": true,
  "description": "Self-contained pi coding agent wired to Edinburgh ELM, university-hosted models only",
  "dependencies": {
    "@earendil-works/pi-coding-agent": "^0.85.1"
  }
}
```

**Change to:**
```json
{
  "name": "elm-pi-agent",
  "private": true,
  "description": "Self-contained pi coding agent wired to Edinburgh ELM, university-hosted models only",
  "dependencies": {
    "@earendil-works/pi-coding-agent": "latest"
  }
}
```

### 4. Shim Considerations

**File:** `/Users/rcurrie/src/elm-pi/shim/shim.py`

**Current behavior:** The shim is a Python HTTP proxy that:
- Listens on `127.0.0.1:8811`
- Intercepts Llama 3.3 requests
- Adds tool-call support by prompt engineering
- Passes through other models unchanged

**For update interception:** No changes needed to the shim itself. The shim only handles HTTP requests to the LLM API, not CLI commands.

**However**, if you want the shim to also be updated when running `pi update`:
- The shim is already updated because `bootstrap.sh --update` re-clones from GitHub
- Line 125 in `bootstrap.sh`: `fetch_tarball "$PREFIX"` or git pull updates all files including `shim/`

### 5. Update `install.sh` Documentation

**File:** `/Users/rcurrie/src/elm-pi/install.sh`

Add to the environment overrides section (around line 17):
```bash
#   ELM_PI_UPDATE=1          refresh pi and the extensions, keeping your configs
#   pi update                updates elm-pi from GitHub (latest main)
#   pi update --extensions   updates pi package and npm dependencies only
```

## Implementation Summary

### Files to Modify:

1. **`pi`** (wrapper script)
   - Add update interception logic before `exec "$ORIG"`
   - Check for `update` command without `--extensions`/`--models`
   - Re-run `bootstrap.sh --update`

2. **`bootstrap.sh`**
   - Change `PI_VERSION` default from `^0.85.1` to `latest`

3. **`templates/package.json`**
   - Change pi dependency from `^0.85.1` to `latest`

4. **`install.sh`** (optional, documentation)
   - Document the `pi update` behavior

### Behavior After Changes:

| Command | Behavior |
|---|---|
| `pi update` | Re-runs `bootstrap.sh --update`, pulling latest from GitHub (elm-pi + pi + shim + extensions) |
| `pi update --self` | Same as above (intercepted) |
| `pi update --extensions` | Passes through to pi, updates only `agent/npm/node_modules/` |
| `pi update --models` | Passes through to pi, updates model definitions |
| `pi update --all` | Would be intercepted (no specific flags) |

### Testing Strategy:

1. **Test interception:**
   ```bash
   cd /Users/rcurrie/src/elm-pi
   ./pi update
   # Should see bootstrap.sh output, not pi's update output
   ```

2. **Test pass-through:**
   ```bash
   ./pi update --extensions
   # Should update agent/npm/node_modules only
   ```

3. **Verify latest pi:**
   ```bash
   ./pi --version
   # Should show latest npm version, not frozen 0.85.1
   ```

4. **Verify GitHub sync:**
   ```bash
   git -C ~/.local/share/elm-pi log --oneline -1
   # Should show latest commit from main branch
   ```

## Edge Cases & Considerations

### 1. Non-Interactive Mode
The interception runs `bootstrap.sh --update --non-interactive` to avoid prompting for the ELM key (already exists in `.env`).

### 2. Local Development
If working on elm-pi locally with uncommitted changes:
- `bootstrap.sh` will pull from GitHub and may overwrite local changes
- Consider adding a check: if git has uncommitted changes, warn before updating

### 3. Network Issues
If GitHub is unreachable:
- `bootstrap.sh` will fail with appropriate error message
- User can still use existing installation

### 4. Version Compatibility
Using `latest` means:
- Breaking changes in pi could break elm-pi
- Consider using a minor version range like `^0.85` instead of `latest`
- Or pin to a specific version and update manually when tested

### 5. Shim Updates
The shim (`shim/shim.py`) is updated automatically when `bootstrap.sh --update` runs because it pulls the entire repository from GitHub.

### 6. Extension Updates
Extensions in `agent/extensions/` are refreshed from templates during `bootstrap.sh --update` (line 84-91 in bootstrap.sh).

## Alternative Approach: Environment Variable Control

If you want more granular control, add an environment variable:

```bash
# In pi wrapper, after line 25 (where other exports are set)
export ELM_PI_INTERCEPT_UPDATE="${ELM_PI_INTERCEPT_UPDATE:-1}"
```

Then users can disable interception:
```bash
ELM_PI_INTERCEPT_UPDATE=0 pi update
# This would run pi's native update instead
```

## Recommended Implementation Order

1. ✅ Modify `pi` wrapper to intercept `update` command
2. ✅ Change `bootstrap.sh` to use `latest` for PI_VERSION
3. ✅ Change `templates/package.json` to use `latest`
4. ✅ Test all scenarios
5. ✅ Update documentation in README.md or INSTALL.md
