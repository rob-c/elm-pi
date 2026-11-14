"""templates/extensions/notebook-outputs.ts: a notebook summary's cut output previews, and reads that name a
markdown cell. From auto20 (2026-11-14): the peak-activity table was cut after its second row, two reads named
markdown cells, and the reply gave a peak time that was in no output."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

# The shape of auto20's summary: a markdown cell cut, a code cell whose source is cut but whose output is
# whole, and the code cell whose output was cut.
SUMMARY = """<meta nbformat=4.5 kernel=- cells=11 language=python />
<cell index="7" id="a1" type="md" lines="9">
## Step 4: Plot
[8 more lines]
</cell>
<cell index="8" id="a2" type="code" lines="30" n_exec="4" outputs="1">
import matplotlib.pyplot as plt
[29 more lines]
<output index="0" type="stream" name="stdout">
Plot saved to bateman_activities.png
</output>
</cell>
<cell index="10" id="95cdad53" type="code" lines="19" n_exec="5" outputs="1">
# Find maximum activities and when they occur
[14 more lines]
<output index="0" type="stream" name="stdout">
Maximum activities and times:
Nuclide    Max Activity    Time (min)
----------------------------------------
Po-218     2.2360e-01      0.00
Pb-214     1.9506e-02      10.93
[8 more lines]
</output>
</cell>"""

NOTEBOOK = json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
    {"cell_type": kind, "metadata": {}, "source": "x", **({"outputs": [], "execution_count": None} if kind == "code" else {})}
    for kind in ("markdown", "markdown", "code", "markdown", "code", "markdown", "code")]})


def after(test, event, files=None):
    """What the extension's tool_result handler makes of `event`: the added note, or None."""
    return run_extension(test, "notebook-outputs", f"""
        const event = {json.dumps(event)};
        const result = await registered.handlers.tool_result[0](event, ctx);
        out(result ? result.content.slice(event.content.length).map((c) => c.text).join("") : null);
    """, files=files)


class NotebookOutputsTests(unittest.TestCase):
    def test_a_cut_output_is_named_with_the_call_that_reads_it_whole(self):
        note = after(self, {"toolName": "notebook_summary", "isError": False,
                            "input": {"path": "bateman.ipynb"}, "content": [{"type": "text", "text": SUMMARY}]})
        self.assertIn("The output previews of cell 10 are cut short", note)
        self.assertIn("what is not shown is not seen", note)
        self.assertIn("notebook_read_cell_output { path, index: 10 }", note)

    def test_cut_sources_and_markdown_are_not_cut_outputs(self):
        whole = SUMMARY.replace("Pb-214     1.9506e-02      10.93\n[8 more lines]\n", "Pb-214     1.9506e-02      10.93\n")
        self.assertIsNone(after(self, {"toolName": "notebook_summary", "isError": False,
                                       "content": [{"type": "text", "text": whole}]}))

    def test_a_read_of_a_markdown_cell_is_told_where_the_code_cells_are(self):
        note = after(self, {"toolName": "notebook_read_cell_output", "isError": True,
                            "input": {"path": "chain.ipynb", "index": 5},
                            "content": [{"type": "text", "text": "Cell index 5 is not a code cell"}]},
                     files={"chain.ipynb": NOTEBOOK})
        self.assertEqual("\nThe code cells of chain.ipynb are at index 2, 4, 6 (0-based, markdown cells counted).", note)

    def test_nothing_is_added_when_the_notebook_cannot_be_read_or_the_read_worked(self):
        error = {"toolName": "notebook_read_cell_output", "isError": True, "input": {"path": "missing.ipynb", "index": 1},
                 "content": [{"type": "text", "text": "Cell index 1 is not a code cell"}]}
        self.assertIsNone(after(self, error))
        self.assertIsNone(after(self, {**error, "isError": False, "content": [{"type": "text", "text": "Po-214 ..."}]}))


if __name__ == "__main__":
    unittest.main()
