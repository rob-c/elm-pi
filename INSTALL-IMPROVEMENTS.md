# Installation Improvements

## Changes Made

This document describes improvements made to the elm-pi installation process to address two key issues:

### 1. No More Exhaustive NPM Checks on Every Launch

**Problem**: Previously, running `bootstrap.sh` (and thus the install script) would always run `npm install` checks, which took significant time on every invocation.

**Solution**: Modified `bootstrap.sh` to skip npm installation when packages are already present:

- Added a new `--force` flag to force npm reinstall even when packages exist
- The `--update` flag continues to force reinstall (existing behavior)
- When neither flag is set, npm install is skipped if:
  - For main pi packages: `node_modules/@earendil-works/pi-coding-agent` exists
  - For agent packages: `agent/npm/node_modules/pi-subagents` exists

**Files Changed**:
- `bootstrap.sh`: Added `--force` flag and conditional npm install logic

**Usage**:
```bash
# Normal run - skips npm install if packages exist
./bootstrap.sh

# Force reinstall of all npm packages
./bootstrap.sh --force

# Update mode - refreshes pi and packages, keeps configs
./bootstrap.sh --update
```

### 2. Install Script Now Behaves Like Bootstrap --update

**Problem**: Re-running the install script from the website didn't automatically update existing installations.

**Solution**: Modified `install.sh` to detect existing installations and automatically pass `--update --force` to `bootstrap.sh`:

- Detects existing install by checking for `node_modules` or `agent/npm/node_modules`
- When an existing install is found, automatically treats it as an update
- Preserves all user configs, sessions, and memory (existing bootstrap behavior)
- Updated help text to clarify this behavior

**Files Changed**:
- `install.sh`: Added existing install detection and automatic update behavior

**Usage**:
```bash
# First-time install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"

# Update existing install (same command!)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

## Benefits

1. **Faster subsequent runs**: No more waiting for npm checks when nothing needs updating
2. **Proper update behavior**: Re-running the installer now updates both elm-pi and pi packages
3. **Preserves user data**: Configs, sessions, memory, and .env are never overwritten
4. **Explicit control**: Use `--force` when you want to ensure fresh npm packages

## Testing

To verify the changes work:

1. Run `bootstrap.sh` twice - second run should skip npm install
2. Run `bootstrap.sh --force` - should reinstall npm packages
3. Re-run install.sh on existing install - should update automatically
4. Verify configs in `agent/` are preserved after updates

## Backward Compatibility

All changes are backward compatible:
- Existing flags continue to work as before
- New `--force` flag is optional
- Default behavior is now smarter but doesn't break existing workflows
- Manual `--update` flag still works as expected
