# Editing: anchor-based (pi-hashline-edit-pro)

pi's own `edit`, `find` and `ls` are **off**: this install's tools are `read`,
`bash`, `write` and pi-hashline-edit-pro's anchor tools. `read` returns every
line as `anchor│content`, the anchor being five lowercase letters; edit with
`replace` (whole lines), `replace_match` (part of a line) or `insert`, giving
the file's `path` and the anchors rather than reproducing text. `grep` is the
package's search, not pi's: under a `=== path ===` header each hit comes back as
`lineNumber:│ anchor│content`, and those anchors can be edited without a `read`.
`undo_last_change` reverts the last anchor edit on a file - one level, it
survives a restart, and a `write` clears it.

Every anchor edit must name its file (`path`): this install turns on the
package's `requirePath`, because the protected-paths guard can only refuse an
edit to `.git`, `node_modules` or a `.env` file whose path it can see. `copy`
and `move` are switched off for the same reason - a move's destination comes
from an anchor, not from the path it names. Copy lines with `read` and `insert`.

Use `read` to read and `grep` to search, not `bash`. Use `bash` to list
files (`ls`, `fd`) and to run things.

Anchors matter most for Llama. The old `edit` tool required reproducing
`oldText` and `newText` byte-perfectly inside JSON, and Llama routinely emitted
raw newlines and unbalanced braces, producing invalid JSON and silent no-ops.

Under `pi --fast` none of this applies: the anchor tools are not loaded and
pi's builtin `edit` is the editor.

Notebooks (`.ipynb`) are edited with the `notebook_*` tools, cell by cell, never
with `write` - see `scientific-python`.
