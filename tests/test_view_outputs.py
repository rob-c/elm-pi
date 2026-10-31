"""Figures and PDFs are shown to the model: the ones a command writes, and any it asks to view.

view-outputs.ts is run under node against real files: a two-page PDF and a PNG
made here, rendered by the same mupdf package pi loads. typebox is a stub - pi
supplies the real one to extensions - and mupdf is the installed copy, so the
tests skip on a checkout that has not been bootstrapped.
"""

import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "templates/extensions/view-outputs.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def png(width, height):
    raw = b"".join(b"\0" + bytes((200, 30, 30)) * width for _ in range(height))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def pdf(pages):
    """A minimal PDF with one line of text per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>",
               "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{4 + 2 * i} 0 R" for i in range(pages)), pages),
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i in range(pages):
        stream = f"BT /F1 24 Tf 30 150 Td (Spectrum page {i + 1}) Tj ET".encode()
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents {5 + 2 * i} 0 R "
                       "/Resources << /Font << /F1 3 0 R >> >> >>")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + (body if isinstance(body, bytes) else body.encode()) + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


# Registers the extension against a stub pi, then replays the events a session
# would send. Prints, per step, the text parts and the image count/sizes.
RUNNER = r"""
const [source, cwd, stepsJson] = process.argv.slice(1);
const mod = await import(source);
const handlers = {}; let tool;
mod.default({ on: (e, h) => { (handlers[e] ??= []).push(h); }, registerTool: (t) => { tool = t; } });
const model = (vision) => ({ input: vision ? ["text", "image"] : ["text"] });
const out = [];
for (const step of JSON.parse(stepsJson)) {
  const ctx = { cwd, model: model(step.vision !== false), hasUI: false };
  let result;
  if (step.kind === "view") {
    result = await tool.execute("v", step.params, undefined, undefined, ctx);
  } else {
    const id = step.id;
    for (const h of handlers.tool_call ?? []) await h({ type: "tool_call", toolCallId: id, toolName: step.tool, input: step.input }, ctx);
    if (step.write) for (const [name, b64] of Object.entries(step.write)) {
      const { writeFileSync } = await import("node:fs");
      writeFileSync(name.startsWith("/") ? name : `${cwd}/${name}`, Buffer.from(b64, "base64"));
    }
    const event = { type: "tool_result", toolCallId: id, toolName: step.tool, input: step.input,
                    content: [{ type: "text", text: step.output ?? "" }], isError: !!step.isError, details: undefined };
    for (const h of handlers.tool_result ?? []) result = (await h(event, ctx)) ?? result;
  }
  const content = result?.content ?? [];
  out.push({
    isError: result?.isError ?? null,
    text: content.filter((c) => c.type === "text").map((c) => c.text).join("\n"),
    images: content.filter((c) => c.type === "image").map((c) => c.mimeType),
    modified: result !== undefined,
  });
}
console.log(JSON.stringify(out));
"""


class ViewOutputsTests(unittest.TestCase):
    def setUp(self):
        self.binary = node()
        mupdf = ROOT / "node_modules/mupdf"
        if not self.binary or not mupdf.exists():
            self.skipTest("needs node and the installed mupdf package (run bootstrap.sh)")
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        # The extension, beside a node_modules with the real mupdf and a typebox stub.
        ext = self.tmp / "ext"
        (ext / "node_modules/typebox").mkdir(parents=True)
        (ext / "node_modules/typebox/package.json").write_text('{"name":"typebox","type":"module","main":"index.js"}')
        (ext / "node_modules/typebox/index.js").write_text(
            "const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Optional: f, Boolean: f };")
        (ext / "node_modules/mupdf").symlink_to(mupdf)
        shutil.copy(SOURCE, ext / "view-outputs.ts")
        self.source = ext / "view-outputs.ts"
        self.cwd = self.tmp / "project"
        (self.cwd / "figures").mkdir(parents=True)
        (self.cwd / ".venv").mkdir()
        # PATH is this folder and node's, so which converters exist is up to each test,
        # not to the machine (a Mac has qlmanage and sips).
        self.bin = self.tmp / "bin"
        self.bin.mkdir()

    def fake_tool(self, name, script):
        tool = self.bin / name
        tool.write_text("#!/bin/sh\n" + script)
        tool.chmod(0o755)

    def run_steps(self, steps):
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{Path(self.binary).parent}"}
        run = subprocess.run([self.binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                              str(self.source), str(self.cwd), json.dumps(steps)],
                             capture_output=True, text=True, timeout=120, env=env)
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        return json.loads(run.stdout)

    @staticmethod
    def b64(data):
        import base64
        return base64.b64encode(data).decode()

    def test_figures_a_command_writes_are_attached_with_an_instruction_to_examine_them(self):
        (self.cwd / "old.png").write_bytes(png(10, 10))
        old = (self.cwd / "old.png").stat().st_mtime - 3600
        os.utime(self.cwd / "old.png", (old, old))
        out_of_tree = self.tmp / "elsewhere.png"
        result, = self.run_steps([{
            "tool": "bash", "id": "b1", "output": "saved",
            "input": {"command": f"python3 plot.py --out {out_of_tree}"},
            "write": {"figures/fit.png": self.b64(png(40, 30)), "report.pdf": self.b64(pdf(2)),
                      ".venv/hidden.png": self.b64(png(5, 5)), str(out_of_tree): self.b64(png(8, 8)),
                      "figures/fit.svg": self.b64(b"<svg/>")},
        }])
        self.assertEqual(4, len(result["images"]))  # fit.png, both PDF pages, elsewhere.png
        self.assertIn("saved", result["text"])       # the command's own output is kept
        self.assertIn("Examine every attached image", result["text"])
        self.assertIn("figures/fit.png", result["text"])
        self.assertIn("Spectrum page 2", result["text"])  # the PDF's text layer comes with it
        self.assertIn("fit.svg: no converter for .svg on this machine", result["text"])
        self.assertNotIn("old.png", result["text"])
        self.assertNotIn("hidden.png", result["text"])

    def test_formats_mupdf_cannot_read_go_through_a_system_converter(self):
        # rsvg-convert -f png -o OUT IN; gs ... -sOutputFile=OUT IN
        self.fake_tool("rsvg-convert", f'/bin/cp "{self.tmp}/red.png" "$4"\n')
        self.fake_tool("gs", f'for a; do case "$a" in -sOutputFile=*) /bin/cp "{self.tmp}/two.pdf" "${{a#-sOutputFile=}}" ;; esac; done\n')
        (self.tmp / "red.png").write_bytes(png(20, 20))
        (self.tmp / "two.pdf").write_bytes(pdf(2))
        auto, = self.run_steps([{"tool": "bash", "id": "b1", "input": {"command": "python3 plot.py"},
                                 "write": {"fit.svg": self.b64(b"<svg/>")}}])
        self.assertEqual(1, len(auto["images"]))
        self.assertIn("fit.svg (converted with rsvg-convert)", auto["text"])
        (self.cwd / "spectrum.eps").write_bytes(b"%!PS-Adobe-3.0 EPSF-3.0")
        (self.cwd / "photo.heic").write_bytes(b"not really")
        viewed, heic = self.run_steps([{"kind": "view", "params": {"path": "spectrum.eps"}},
                                       {"kind": "view", "params": {"path": "photo.heic"}}])
        self.assertEqual(2, len(viewed["images"]))
        self.assertIn("converted with gs", viewed["text"])
        self.assertIn("Spectrum page 2", viewed["text"])
        self.assertTrue(heic["isError"])
        self.assertIn("any of: sips, magick", heic["text"])

    def test_an_unchanged_figure_is_not_attached_twice(self):
        steps = [{"tool": "bash", "id": "b1", "input": {"command": "make"}, "write": {"a.png": self.b64(png(9, 9))}},
                 {"tool": "bash", "id": "b2", "input": {"command": "ls"}}]
        first, second = self.run_steps(steps)
        self.assertEqual(1, len(first["images"]))
        self.assertFalse(second["modified"])

    def test_a_text_only_model_is_told_to_hand_figures_to_qwen(self):
        result, = self.run_steps([{"tool": "bash", "id": "b1", "vision": False, "input": {"command": "x"},
                                   "write": {"a.png": self.b64(png(9, 9))}}])
        self.assertEqual([], result["images"])
        self.assertIn("qwen", result["text"])

    def test_per_command_limit_names_what_was_left_out(self):
        write = {f"p{i}.png": self.b64(png(6, 6)) for i in range(10)}
        result, = self.run_steps([{"tool": "bash", "id": "b1", "input": {"command": "x"}, "write": write}])
        self.assertEqual(8, len(result["images"]))
        self.assertIn("Not attached here", result["text"])
        self.assertIn("view tool", result["text"])

    def test_view_renders_selected_pages_and_large_images_are_scaled(self):
        (self.cwd / "paper.pdf").write_bytes(pdf(15))
        (self.cwd / "big.png").write_bytes(png(3200, 100))
        first, chosen, big, svg = self.run_steps([
            {"kind": "view", "params": {"path": "paper.pdf"}},
            {"kind": "view", "params": {"path": "paper.pdf", "pages": "14-15"}},
            {"kind": "view", "params": {"path": "big.png"}},
            {"kind": "view", "params": {"path": "x.svg"}},
        ])
        self.assertEqual(12, len(first["images"]))
        self.assertIn('pages "13-15" for the rest', first["text"])
        self.assertEqual(2, len(chosen["images"]))
        self.assertIn("Spectrum page 14", chosen["text"])
        self.assertNotIn("Spectrum page 1\n", chosen["text"])
        self.assertEqual(["image/png"], big["images"])  # re-rendered through mupdf, not passed through
        self.assertTrue(svg["isError"])

    def test_a_pdf_given_to_read_is_rendered_whatever_read_made_of_it(self):
        # Compressed: read rejects it as binary. Uncompressed: read returns the PDF source.
        (self.cwd / "notes.pdf").write_bytes(pdf(1))
        rejected, as_source, text = self.run_steps([
            {"tool": "read", "id": "r1", "isError": True, "output": "binary file rejected", "input": {"path": "notes.pdf"}},
            {"tool": "read", "id": "r2", "output": "aaaaa|%PDF-1.4", "input": {"path": "notes.pdf"}},
            {"tool": "read", "id": "r3", "output": "x = 1", "input": {"path": "fit.py"}},
        ])
        for result in (rejected, as_source):
            self.assertFalse(result["isError"])
            self.assertEqual(1, len(result["images"]))
            self.assertIn("Spectrum page 1", result["text"])
            self.assertNotIn("%PDF", result["text"])
        self.assertFalse(text["modified"])


class WiringTests(unittest.TestCase):
    def test_installed_and_pinned(self):
        self.assertIn("view-outputs.ts", CONFIG["requiredExtensions"])
        manifest = json.loads((ROOT / "package.json").read_text())
        versions = json.loads((ROOT / "config/versions.json").read_text())
        self.assertIn("mupdf", manifest["dependencies"])
        self.assertIn("mupdf", versions["core"])

    def test_llama_cannot_call_view(self):
        meta = (ROOT / "templates/agents/llama.md").read_text().split("---")[1]
        self.assertIn(" view,", next(l for l in meta.splitlines() if l.startswith("excludeTools:")))

    def test_system_prompt_states_free_compute_and_the_real_context_window(self):
        prompt = (ROOT / "templates/APPEND_SYSTEM.md").read_text()
        models = json.loads((ROOT / "templates/models.json").read_text())
        window = next(m["contextWindow"] for p in models["providers"].values() for m in p["models"])
        compact = json.loads(next((ROOT / "templates/config/pi-auto-compact").glob("*.json")).read_text())
        self.assertIn("# This compute is free", prompt)
        self.assertIn(f"{window:,} tokens", prompt)
        self.assertIn(f"compacted at {compact['autoCompactThreshold']}%", prompt)
        self.assertIn("`view`", prompt)


if __name__ == "__main__":
    unittest.main()
