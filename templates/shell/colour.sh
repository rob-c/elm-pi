# shellcheck shell=bash
# Sourced before every bash command (settings.json "shellCommandPrefix").
#
# pi reads a command's output through a pipe, so tools see no terminal and
# print no colour. command-output.ts shows a command's own colour to the user
# and gives the model plain text, so these wrappers turn colour on where a
# terminal would have it: output going straight back to pi. Output piped,
# redirected or captured with $(...) stays plain, so `git diff > fix.patch`,
# `git diff | grep '^+'` and `n=$(ls | wc -l)` behave as they always have.
# They are shell functions, so scripts and programs a command starts do not
# see them, and `command git` bypasses them. NO_COLOR turns all of it off.

[ -n "$BASH_VERSION" ] && [ -z "$NO_COLOR" ] || return 0

case "$OSTYPE" in
	darwin* | *bsd*) _pi_stat=(stat -L -f %d:%i) ;;
	*) _pi_stat=(stat -L -c %d:%i) ;;
esac
# What pi reads: this shell's stdout before the command runs. Read through fd 3,
# since inside $(...) fd 1 is the substitution's own pipe.
{ _pi_out=$("${_pi_stat[@]}" /dev/fd/3 2>/dev/null); } 3>&1

# True when this call's output goes straight back to pi. NO_COLOR is read
# again here, so `NO_COLOR=1 git diff` and an export inside the command count.
_pi_here() {
	[ -z "${NO_COLOR-}" ] || return 1
	local id
	{ id=$("${_pi_stat[@]}" /dev/fd/3 2>/dev/null); } 3>&1
	[ -n "$id" ] && [ "$id" = "$_pi_out" ]
}

# Only tools that exist get a wrapper, so `command -v` stays truthful.
_pi_has() { type -P "$1" >/dev/null; }

# git: only subcommands that show something. Config given with -c reaches
# hooks and aliases through GIT_CONFIG_PARAMETERS, and a hook that parses
# `git diff` must not get colour.
_pi_has git && git() {
	local i=1 sub=""
	while [ "$i" -le $# ]; do
		case "${!i}" in
			-C | -c | --config-env | --git-dir | --work-tree | --namespace) i=$((i + 2)) ;;
			-*) i=$((i + 1)) ;;
			*) sub=${!i}; break ;;
		esac
	done
	case "$sub" in
		diff | show | log | status | branch | grep | blame | shortlog | range-diff | reflog)
			if _pi_here; then
				command git -c color.ui=always -c color.diff=always -c color.status=always \
					-c color.branch=always -c color.grep=always "$@"
				return
			fi ;;
	esac
	command git "$@"
}

# BSD ls (macOS) reads CLICOLOR; GNU ls takes a flag, and its -G means something else.
if _pi_has ls; then
	case "$OSTYPE:$(type -P ls)" in
		darwin*:/bin/ls | *bsd*:/bin/ls)
			ls() { if _pi_here; then CLICOLOR=1 CLICOLOR_FORCE=1 command ls "$@"; else command ls "$@"; fi; } ;;
		*)
			ls() { if _pi_here; then command ls --color=always "$@"; else command ls "$@"; fi; } ;;
	esac
fi

# The forced flag goes first, so a colour flag the command gives wins.
_pi_flag() {
	_pi_has "$1" || return 0
	eval "$1() { if _pi_here; then command $1 $2 \"\$@\"; else command $1 \"\$@\"; fi; }"
}
_pi_flag grep --color=always
_pi_flag rg --color=always
_pi_flag fd --color=always
_pi_flag jq -C
_pi_flag tree -C
_pi_flag shellcheck --color=always
_pi_flag pytest --color=yes

# Older diffs have no --color, so ask before using it.
_pi_has diff && diff() {
	if _pi_here && command diff --color=always /dev/null /dev/null >/dev/null 2>&1; then
		command diff --color=always "$@"
	else
		command diff "$@"
	fi
}

_pi_has ruff && ruff() { if _pi_here; then CLICOLOR_FORCE=1 command ruff "$@"; else command ruff "$@"; fi; }

# `python -m pytest` is how a project's own environment runs its tests.
_pi_python() {
	_pi_has "$1" || return 0
	eval "$1() {
		if [ \"\${1-} \${2-}\" = \"-m pytest\" ] && _pi_here; then command $1 -m pytest --color=yes \"\${@:3}\"
		else command $1 \"\$@\"; fi
	}"
}
_pi_python python
_pi_python python3
unset -f _pi_flag _pi_python
