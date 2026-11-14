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
  if (step.kind === "turn") { for (const h of handlers.turn_start ?? []) await h({ type: "turn_start" }, ctx); continue; }
  if (step.kind === "start") { for (const h of handlers.agent_start ?? []) await h({ type: "agent_start" }, ctx); continue; }
  if (step.kind === "input") { for (const h of handlers.input ?? []) await h({ type: "input", text: "make a site", source: "interactive" }, ctx); continue; }
  if (step.kind === "pause") { await new Promise((r) => setTimeout(r, 40)); continue; }
  if (step.kind === "files") {   // what sub-agents write, by tools this session never sees
    const { writeFileSync, mkdirSync } = await import("node:fs"); const { dirname } = await import("node:path");
    for (const [name, text] of Object.entries(step.write)) { mkdirSync(dirname(`${cwd}/${name}`), { recursive: true }); writeFileSync(`${cwd}/${name}`, text); }
    continue;
  }
  if (step.kind === "settle") {
    const event = { type: "agent_before_settle", context: { contextMessages: [{ role: "assistant", content: [{ type: "text", text: step.reply }] }] } };
    let r; for (const h of handlers.agent_before_settle ?? []) r = (await h(event, ctx)) ?? r;
    out.push({ isError: null, text: r ? r.entries[0].content : "", images: [], modified: r !== undefined, continue: r?.continue ?? null });
    continue;
  }
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
            "const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Optional: f, Boolean: f, Array: f };")
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

    def run_steps(self, steps, env=None):
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{Path(self.binary).parent}", **(env or {})}
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

    def test_an_html_page_is_drawn_by_a_browser_when_asked_and_never_attached_unasked(self):
        # test5: asked to compare the subpages' renderings, `view` refused HTML and nothing was looked at.
        # The fake browser records its arguments and writes the screenshot it is asked for.
        self.fake_tool("google-chrome", f'echo "$@" > "{self.tmp}/chrome.args"\n'
                                        f'for a; do case "$a" in --screenshot=*) /bin/cp "{self.tmp}/red.png" "${{a#--screenshot=}}" ;; esac; done\n')
        (self.tmp / "red.png").write_bytes(png(20, 20))
        (self.cwd / "index.html").write_text("<html><body>frogs</body></html>")
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "index.html"}}])
        self.assertEqual(1, len(viewed["images"]))
        self.assertIn("converted with google-chrome", viewed["text"])
        args = (self.tmp / "chrome.args").read_text()
        self.assertIn("--headless=new", args)
        self.assertIn("--user-data-dir=", args)        # never the user's own profile
        self.assertIn("file://", args)
        # with no egress proxy in the environment, nothing but this machine resolves
        self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND", args)
        auto, = self.run_steps([{"tool": "bash", "id": "b1", "input": {"command": "python3 build_site.py"},
                                 "write": {"page.html": self.b64(b"<html></html>")}}])
        self.assertEqual(0, len(auto["images"]))
        self.assertNotIn("page.html", auto["text"])

    def fake_browser(self, then=""):
        """A google-chrome that writes the screenshot it is asked for, then runs `then`."""
        (self.tmp / "red.png").write_bytes(png(20, 20))
        self.fake_tool("google-chrome", f'for a; do case "$a" in --screenshot=*) /bin/cp "{self.tmp}/red.png" '
                                        f'"${{a#--screenshot=}}" ;; esac; done\n{then}\n')

    def site(self):
        (self.cwd / "styles.css").write_text("body { background: url(img/paper.png); }")
        (self.cwd / "index.html").write_text("<html></html>")
        (self.cwd / "gallery.html").write_text(
            '<html><head><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="missing.css"></head><body>'
            '<a href="index.html">Home</a> <a href="about.html">About</a> <a href="https://example.org/x.html">x</a> '
            '<a href="#top">top</a> <img src="https://picsum.photos/seed/alpaca1/400/300" alt="White alpaca portrait">'
            '<img src="https://picsum.photos/seed/alpaca2/400/300"> <img src="logo.png"> '
            '<img src="data:image/png;base64,AAAA"></body></html>')

    def test_a_page_says_what_it_could_not_show(self):
        # test7: six picsum.photos images were refused by the egress proxy, drew as broken, and the
        # model called the page "Perfect!"; in a browser they would be arbitrary stock photos.
        agent = self.tmp / "agent"
        agent.mkdir()
        log = agent / "egress.log"
        log.write_text("2026-11-12T17:00:00Z REJECTED picsum.photos:443 not on the allowlist\n")   # an earlier render's
        self.fake_browser(then=f'echo "2026-11-12T17:58:26Z REJECTED picsum.photos:443 not on the allowlist" >> "{log}"')
        self.site()
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "gallery.html"}}],
                                 env={"HTTPS_PROXY": "http://127.0.0.1:9", "PI_CODING_AGENT_DIR": str(agent)})
        text = viewed["text"]
        self.assertEqual(1, len(viewed["images"]))
        missing = next(line for line in text.splitlines() if line.startswith("Missing: "))
        self.assertEqual({"missing.css", "logo.png"}, set(missing[9:missing.index(" - ")].split(", ")))
        self.assertIn("the page asks for these files, which are not there: broken in any browser.", missing)
        # test8: every page said "Missing: images/deer-hero.jpg", the stylesheet's, for the one page with a hero
        self.assertIn("styles.css asks for img/paper.png, which is not there: wherever the stylesheet uses it, "
                      "a browser shows nothing in its place.", text)
        self.assertIn("Links to pages that do not exist: about.html.", text)
        self.assertIn("Not drawn here: 2 from picsum.photos - the egress proxy refuses that host, so they show as broken above", text)
        self.assertIn("picsum.photos serves arbitrary placeholder pictures, not what a caption or alt text describes", text)
        self.assertNotIn("example.org", text)          # a link to another site is not drawn

    def test_through_the_proxy_chrome_calls_nobody_on_its_own(self):
        """test8: every render asked the egress proxy for accounts.google.com, clients2.google.com and five
        more; under --remote they went through. A PAC script sends those to a closed port, the page's to the proxy."""
        import base64
        self.fake_tool("google-chrome", f'echo "$@" > "{self.tmp}/chrome.args"\n'
                                        f'for a; do case "$a" in --screenshot=*) /bin/cp "{self.tmp}/red.png" "${{a#--screenshot=}}" ;; esac; done\n')
        (self.tmp / "red.png").write_bytes(png(20, 20))
        (self.cwd / "map.html").write_text('<html><body><iframe src="https://www.google.com/maps/embed?pb=x"></iframe></body></html>')
        self.run_steps([{"kind": "view", "params": {"path": "map.html"}}], env={"HTTPS_PROXY": "http://127.0.0.1:50920"})
        args = (self.tmp / "chrome.args").read_text()
        self.assertNotIn("--proxy-server", args)
        pac = base64.b64decode(args.split("--proxy-pac-url=data:application/x-ns-proxy-autoconfig;base64,")[1].split()[0]).decode()
        self.assertIn('"accounts.google.com"', pac)
        self.assertIn('"update.googleapis.com"', pac)
        self.assertNotIn('"www.google.com"', pac)          # the page's own map still goes through the proxy
        self.assertIn('return "PROXY 127.0.0.1:9"', pac)
        self.assertIn('return "PROXY 127.0.0.1:50920"', pac)

    def test_without_a_proxy_a_page_reaches_no_other_host(self):
        self.fake_browser()
        self.site()
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "gallery.html"}}], env={"HTTPS_PROXY": ""})
        self.assertIn("Not drawn here: 2 from picsum.photos - this render reaches no other host", viewed["text"])

    def test_several_files_come_back_together_to_compare(self):
        (self.cwd / "a.png").write_bytes(png(10, 10))
        (self.cwd / "b.png").write_bytes(png(12, 12))
        viewed, = self.run_steps([{"kind": "view", "params": {"paths": ["a.png", "b.png", "nope.png"]}}])
        self.assertEqual(["image/png", "image/png"], viewed["images"])
        self.assertIn("nope.png: no such file.", viewed["text"])
        self.assertIn("Shown together to compare. Before you call them consistent, list every difference", viewed["text"])
        self.assertIsNone(viewed["isError"])
        single, = self.run_steps([{"kind": "view", "params": {"path": "a.png"}}])
        self.assertNotIn("Shown together", single["text"])

    def test_a_download_that_is_not_an_image_is_reported_and_never_attached(self):
        """test9: seven curls saved "error code: 522" as .jpg; attached as JPEGs, the gateway refused
        that request and every later one with 400 "cannot identify image file"."""
        error = b"error code: 522"
        result, = self.run_steps([{
            "tool": "bash", "id": "b1", "output": "Images downloaded successfully",
            "input": {"command": "curl -sL https://example.org/a -o images/g1.jpg"},
            "write": {"g1.jpg": self.b64(error), "g2.jpg": self.b64(error), "g3.jpg": self.b64(error),
                      "page.png": self.b64(b"<!DOCTYPE html><html><head><title>403 Forbidden</title></head></html>"),
                      "cut.png": self.b64(png(30, 30)[:-12]), "real.jpg": self.b64(png(10, 10))},
        }])
        self.assertEqual(["image/png"], result["images"])       # real.jpg, a PNG by its bytes, typed as one
        text = result["text"]
        self.assertIn('Not images: g1.jpg, g2.jpg, g3.jpg - each holds 15 bytes of text: "error code: 522".', text)
        self.assertIn('Not an image: page.png - it holds a web page titled "403 Forbidden"', text)
        self.assertIn("Not an image: cut.png - it is cut short: it stops before the end of the picture", text)
        self.assertIn("`curl -fL`", text)
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "g1.jpg"}}])
        self.assertTrue(viewed["isError"])
        self.assertIn('g1.jpg: could not be shown: not an image: it holds 15 bytes of text: "error code: 522"', viewed["text"])

    def test_a_saved_error_page_says_what_the_server_said(self):
        """test12: five "Wikimedia Error" pages saved as .jpg; the body named the cause, the note did not."""
        page = (b'<!DOCTYPE html><html lang="en"><meta charset="utf-8"><title>Wikimedia Error</title><style>p{x:1}</style>'
                b'<div class="content"><h1>Error</h1><p>Use thumbnail sizes listed on https://w.wiki/GHai</p></div>'
                b'<div class="footer"><code>Error: 400, Use thumbnail sizes listed on https://w.wiki/GHai at Fri, '
                b'13 Nov 2026 09:18:47 GMT</code><p>Sensitive client information IP address: 192.0.2.1</p></div></html>')
        result, = self.run_steps([{"tool": "bash", "id": "b1", "input": {"command": "curl -L -o earthworm.jpg https://x"},
                                   "write": {"earthworm.jpg": self.b64(page)}}])
        self.assertIn('Not an image: earthworm.jpg - it holds a web page titled "Wikimedia Error" ('
                      f'{len(page)} bytes), saying "HTTP 400: Use thumbnail sizes listed on https://w.wiki/GHai".',
                      result["text"])
        self.assertNotIn("192.0.2.1", result["text"])

    def test_an_svg_drawing_named_jpg_is_called_what_it_is(self):
        """test13: placeholder SVGs written into .jpg files; the note called them text from a failed download."""
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect fill="#8B7355"/></svg>'
        result, = self.run_steps([{"tool": "bash", "id": "b1", "input": {"command": "cat > a.jpg"},
                                   "write": {"a.jpg": self.b64(svg)}}])
        self.assertIn(f"Not an image: a.jpg - it holds an SVG drawing ({len(svg)} bytes) under another picture "
                      "format's name: a browser shows it as broken - name it .svg.", result["text"])
        self.assertNotIn("A download that saved the server's error reply", result["text"])

    # auto08 (2026-11-13): a "JPEG" made by hand - a JFIF header and nothing a decoder can use - was attached,
    # and the gateway answered "400 Failed to load image" and ended the session.
    HAND_MADE_JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b1c12121314191617191817161c1f1e1d1c1c1f1f1e1e1cffc0000b080001000101011100ffc4001400010000000000000000000000000000000008ffc4001401010000000000000000000000000000000001ffd9")

    def test_a_picture_that_does_not_decode_is_never_attached(self):
        result, = self.run_steps([{"tool": "bash", "id": "b1", "input": {"command": "python3 make_frogs.py"},
                                   "write": {"frog1.jpg": self.b64(self.HAND_MADE_JPEG)}}])
        self.assertEqual([], result["images"])
        self.assertIn("Not an image: frog1.jpg - it does not decode as a picture", result["text"])

    def test_an_image_in_the_conversation_that_does_not_decode_is_left_out_of_requests(self):
        import base64
        good, bad = base64.b64encode(png(4, 4)).decode(), base64.b64encode(self.HAND_MADE_JPEG).decode()
        script = (RUNNER.split("const out = [];")[0] +
                  "const messages = JSON.parse(process.argv[4]);"
                  "const r = (await handlers.context[0]({ type: 'context', messages }))?.messages ?? null;"
                  "console.log(JSON.stringify(r));")
        read = [{"role": "toolResult", "toolName": "read", "content": [{"type": "image", "data": bad, "mimeType": "image/jpeg"},
                                                                      {"type": "image", "data": good, "mimeType": "image/png"}]}]
        run = subprocess.run([self.binary, "--no-warnings", "--input-type=module", "-e", script,
                              str(self.source), str(self.cwd), "[]", json.dumps(read)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        fixed = json.loads(run.stdout)
        self.assertEqual([{"type": "text", "text": "[left out here: an attachment that was not a valid image]"},
                          {"type": "image", "data": good, "mimeType": "image/png"}], fixed[0]["content"])

    def test_an_image_already_in_the_conversation_that_is_not_one_is_left_out_of_requests(self):
        """A session that already holds one recovers: the context handler drops it from every request."""
        import base64
        good, bad = base64.b64encode(png(4, 4)).decode(), base64.b64encode(b"error code: 522").decode()
        script = (RUNNER.split("const out = [];")[0] +
                  "const messages = JSON.parse(process.argv[4]); const r = [];"
                  "for (const h of handlers.context) r.push((await h({ type: 'context', messages: messages[0] }))?.messages ?? null,"
                  " (await h({ type: 'context', messages: messages[1] }))?.messages ?? null);"
                  "console.log(JSON.stringify(r));")
        poisoned = [{"role": "user", "content": [{"type": "text", "text": "hi"}]},
                    {"role": "toolResult", "toolName": "bash", "content": [
                        {"type": "text", "text": "Images downloaded"}, {"type": "image", "data": bad, "mimeType": "image/jpeg"},
                        {"type": "image", "data": good, "mimeType": "image/png"}]}]
        clean = [{"role": "toolResult", "toolName": "read", "content": [{"type": "image", "data": good, "mimeType": "image/png"}]}]
        run = subprocess.run([self.binary, "--no-warnings", "--input-type=module", "-e", script,
                              str(self.source), str(self.cwd), "[]", json.dumps([poisoned, clean])],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        fixed, untouched = json.loads(run.stdout)
        self.assertEqual(poisoned[0], fixed[0])
        self.assertEqual([{"type": "text", "text": "Images downloaded"},
                          {"type": "text", "text": "[left out here: an attachment that was not a valid image]"},
                          {"type": "image", "data": good, "mimeType": "image/png"}], fixed[1]["content"])
        self.assertIsNone(untouched)                             # nothing to change: the messages are left as they are

    def page(self, name, header, footer, css="css/style.css"):
        (self.cwd / "site" / name).write_text(
            f'<html><head><link rel="stylesheet" href="{css}"></head><body><header class="site-header"><h1>Deer</h1>'
            f'<nav><a href="index.html" class="active">Home</a> <a href="species.html">Species</a></nav></header>'
            f'{header}<main>body of {name}</main>{footer}</body></html>')

    def test_the_parts_every_page_repeats_are_compared_across_the_site(self):
        """test8 and test9: shown pages with four footers and a (c) 2024 among 2026s, the model said
        "complete visual consistency"; a view of a page now says what differs."""
        self.fake_browser()
        (self.cwd / "site/css").mkdir(parents=True)
        (self.cwd / "site/css/style.css").write_text("body {}")
        (self.cwd / "site/js").mkdir()
        (self.cwd / "site/js/main.js").write_text("")
        standard = '<footer class="site-footer"><p>&copy; 2026 Scottish Deer</p></footer>'
        self.page("index.html", "", standard, css="css/styles.css")
        self.page("species.html", '<img src="images/stag.jpg">', standard)
        self.page("habitat.html", "", standard)
        self.page("history.html", "", '<footer><p>&copy; 2024 Scottish Deer heritage</p></footer>')
        (self.cwd / "site/images").mkdir()
        (self.cwd / "site/images/stag.jpg").write_bytes(png(4, 4))
        (self.cwd / "site/images/old.svg").write_text("<svg/>")
        self.page("template.html", "", standard)        # the parent's scaffold, which nothing links to
        first, same_turn, again = self.run_steps([{"kind": "view", "params": {"path": "site/species.html"}},
                                                  {"kind": "view", "params": {"path": "site/habitat.html"}},
                                                  {"kind": "turn"},
                                                  {"kind": "view", "params": {"paths": ["site/index.html", "site/history.html"]}}])
        text = first["text"]
        self.assertIn("Compared across the 5 pages in site/, in what every page repeats:", text)
        self.assertIn("- footer: 2 versions - habitat.html, index.html, species.html, template.html | history.html.", text)
        self.assertIn('history.html, unlike habitat.html: has "<footer>", "&copy; 2024 Scottish Deer heritage"; '
                      'lacks "<footer class="site-footer">", "&copy; 2026 Scottish Deer".', text)
        self.assertIn("- copyright year: 2026 on habitat.html, index.html, species.html, template.html; 2024 on history.html.", text)
        self.assertIn("- stylesheets: css/style.css on habitat.html, history.html, species.html, template.html; "
                      "css/styles.css on index.html.", text)
        # test10: placeholder drawings beside the real photos, and the parent's scaffold page left in the site
        self.assertIn("- js/main.js, images/old.svg: in the site, but no page uses them.", text)
        # the fixture's navigation links only index and species
        self.assertIn("- habitat.html, history.html, template.html: no page links to them.", text)
        self.assertIn("clear out what nothing uses", text)
        self.assertIn("before you call them consistent", text)
        # test10: five views in one turn; four said "given before" of the comparison the fifth carried
        self.assertIn("The comparison of the pages in site/ is in another `view` result of this turn.", same_turn["text"])
        self.assertIn("The comparison of the pages in site/ given before still holds", again["text"])
        self.assertNotIn("- footer:", again["text"])

    def test_a_page_drawing_a_saved_error_page_as_a_picture_says_so(self):
        """test10: images/earthworm.jpg was Wikimedia's error page, saved by curl - there, so not "missing"."""
        self.fake_browser()
        (self.cwd / "images").mkdir()
        (self.cwd / "images/earthworm.jpg").write_bytes(b"<!DOCTYPE html><html><head><title>Wikimedia Error</title></head></html>")
        (self.cwd / "images/ok.png").write_bytes(png(4, 4))
        (self.cwd / "page.html").write_text('<html><body><img src="images/earthworm.jpg"><img src="images/ok.png"></body></html>')
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "page.html"}}])
        self.assertIn('Not an image: images/earthworm.jpg - it holds a web page titled "Wikimedia Error" (71 bytes): '
                      "broken in any browser.", viewed["text"])
        self.assertNotIn("ok.png", viewed["text"])

    def test_pages_the_children_wrote_before_the_last_run_began_are_still_checked(self):
        """batch 3, hares-auto (2026-11-14): sub-agents wrote four pages whose stylesheet asked for a hero
        picture that was not there; the run their last notice started viewed only pictures and said "100%
        self-consistent ... Verified". The check looked for pages changed since that run began, and they
        had all been written before it."""
        css = "body { background: url(images/hero-hare.jpg); }"
        page = '<html><head><link rel="stylesheet" href="styles.css"></head><body><nav><a href="index.html">Home</a></nav>%s<footer>x</footer></body></html>'
        steps = [{"kind": "input"}, {"kind": "start"},                       # the user asks; the run launches children
                 {"kind": "pause"},
                 {"kind": "files", "write": {"website/styles.css": css, "website/index.html": page % "a",
                                             "website/biology.html": page % "b"}},
                 {"kind": "pause"},
                 {"kind": "start"},                                          # the run the children's notice starts
                 {"kind": "settle", "reply": "I've created a 100% self-consistent website. Complete and Verified."}]
        sent, = self.run_steps(steps)
        self.assertTrue(sent["continue"])
        self.assertIn("images/hero-hare.jpg", sent["text"])
        self.assertIn("Do not call the pages consistent or fine until a view says so.", sent["text"])

    def test_a_sub_agent_is_held_to_its_own_page_not_to_its_siblings(self):
        """batch 6, dormice-revise: two children said their page matched, were shown the differences between
        their siblings' unfinished pages, and read those pages for half an hour. 45 of 210 children were sent
        back this way over six batches."""
        self.fake_browser()
        (self.cwd / "site").mkdir()
        self.page("index.html", "", "<footer><p>&copy; 2026 Dormice</p></footer>")
        self.page("habitat.html", "", "<footer><p>&copy; 2024 Hazel dormouse project</p></footer>")
        (self.cwd / "site/css").mkdir()
        (self.cwd / "site/css/style.css").write_text("body { margin: 0; }")     # nothing on the page itself is broken;
        # its link to species.html, which a sibling has yet to write, is not the child's to answer for either
        reply = "habitat.html is complete, with navigation and footer consistent with the other pages."
        steps = [{"kind": "start"}, {"kind": "view", "params": {"path": "site/habitat.html"}}, {"kind": "settle", "reply": reply}]
        _, as_parent = self.run_steps(steps)
        self.assertTrue(as_parent["continue"])                                  # the top session is still sent back
        _, as_child = self.run_steps(steps, env={"PI_SUBAGENT_CHILD": "1"})
        self.assertFalse(as_child["modified"])                                  # a child is not
        # ... but its own page asking for a picture that is not there is still its to fix
        (self.cwd / "site/habitat.html").write_text('<html><body><nav><a href="index.html">Home</a></nav><img src="images/nest.jpg"><footer>x</footer></body></html>')
        _, broken = self.run_steps([{"kind": "start"}, {"kind": "view", "params": {"path": "site/habitat.html"}},
                                    {"kind": "settle", "reply": "habitat.html renders correctly."}], env={"PI_SUBAGENT_CHILD": "1"})
        self.assertTrue(broken["continue"])
        self.assertIn("images/nest.jpg", broken["text"])
        # and pages it never viewed are not gone looking for
        unviewed = [{"kind": "input"}, {"kind": "start"}, {"kind": "pause"},
                    {"kind": "files", "write": {"site/biology.html": "<html><body><footer>other</footer></body></html>"}},
                    {"kind": "pause"}, {"kind": "start"}, {"kind": "settle", "reply": "All pages are consistent."}]
        sent, = self.run_steps(unviewed, env={"PI_SUBAGENT_CHILD": "1"})
        self.assertFalse(sent["modified"])

    def test_pictures_left_in_the_scratch_folder_are_not_part_of_the_site(self):
        """batch 6, wrens-3: eight pictures in .pi/tmp/wren-images/, every page pointing there, "validated all
        image paths point to existing files" - true on this machine, and nowhere the site is copied to."""
        self.fake_browser()
        (self.cwd / ".pi/tmp/wren-images").mkdir(parents=True)
        (self.cwd / ".pi/tmp/wren-images/house-wren.jpg").write_bytes(png(4, 4))
        (self.cwd / "images").mkdir()
        (self.cwd / "images/ok.png").write_bytes(png(4, 4))
        (self.cwd / "index.html").write_text('<html><body><img src=".pi/tmp/wren-images/house-wren.jpg"><img src="images/ok.png"></body></html>')
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "index.html"}}])
        self.assertIn("Kept in scratch: .pi/tmp/wren-images/house-wren.jpg", viewed["text"])
        self.assertIn("Move the files into the site", viewed["text"])
        self.assertNotIn("ok.png", viewed["text"])
        # and nobody viewing the page does not excuse it: the end-of-run check finds it
        steps = [{"kind": "input"}, {"kind": "start"}, {"kind": "pause"},
                 {"kind": "files", "write": {"species.html": '<html><body><img src=".pi/tmp/wren-images/house-wren.jpg"></body></html>'}},
                 {"kind": "pause"}, {"kind": "start"},
                 {"kind": "settle", "reply": "Validated: all image paths point to existing files and every page renders correctly."}]
        sent, = self.run_steps(steps)
        self.assertTrue(sent["continue"])
        self.assertIn("Kept in scratch", sent["text"])

    def test_a_gallery_of_placeholder_pictures_is_not_a_finished_site(self):
        """batch 4, salmon-8: 18 pictures from picsum.photos in the gallery, and "rendering correctly"."""
        imgs = "".join(f'<img src="https://picsum.photos/seed/salmon{i}/400/300" alt="Atlantic salmon leaping">' for i in range(3))
        page = "<html><body><nav><a href='index.html'>Home</a></nav>%s<footer>x</footer></body></html>"
        steps = [{"kind": "input"}, {"kind": "start"}, {"kind": "pause"},
                 {"kind": "files", "write": {"index.html": page % "home", "gallery.html": page % imgs}},
                 {"kind": "pause"}, {"kind": "start"},
                 {"kind": "settle", "reply": "Perfect! The website is rendering correctly with consistent navigation and styling."}]
        sent, = self.run_steps(steps)
        self.assertTrue(sent["continue"])
        self.assertIn("picsum.photos serves arbitrary placeholder pictures", sent["text"])

    def test_calling_the_pages_consistent_over_the_comparison_is_sent_back_once(self):
        """test8, test10, test11, test13: "Perfect! ... consistent" right after a comparison listing differences."""
        self.fake_browser()
        (self.cwd / "site").mkdir()
        self.page("index.html", "", "<footer><p>&copy; 2026 Deer</p></footer>")
        self.page("species.html", "", "<footer><p>&copy; 2024 Deer heritage</p></footer>")
        steps = [{"kind": "start"}, {"kind": "view", "params": {"path": "site/index.html"}},
                 {"kind": "settle", "reply": "Perfect! All pages are rendering with complete visual consistency."},
                 {"kind": "settle", "reply": "Perfect! All pages are consistent."},                     # once per run
                 {"kind": "start"},
                 {"kind": "settle", "reply": "The pages are consistent."}]                              # a new run: no views yet
        _, claimed, again, fresh = self.run_steps(steps)
        self.assertTrue(claimed["continue"])
        self.assertIn("Your reply calls the pages consistent, but the last comparison of the pages in site/ listed:", claimed["text"])
        self.assertIn("- footer: 2 versions", claimed["text"])
        self.assertFalse(again["modified"])
        self.assertFalse(fresh["modified"])
        honest, = self.run_steps([{"kind": "start"}, {"kind": "view", "params": {"path": "site/index.html"}},
                                  {"kind": "settle", "reply": "The footers are not consistent yet: species.html says 2024."}])[1:]
        self.assertFalse(honest["modified"])

    def test_pages_written_and_never_viewed_are_compared_before_consistent_is_believed(self):
        """auto06: five pages written with three different footers, no view, and "consistent styling"."""
        (self.cwd / "site").mkdir()
        page = ('<html><body><header class="site-header"><nav><a href="index.html">Home</a> '
                '<a href="pups.html">Pups</a></nav></header><main>x</main><footer>{}</footer></body></html>')
        writes = {"site/index.html": self.b64(page.format("&copy; 2026 Wolves").encode()),
                  "site/pups.html": self.b64(page.format("&copy; 2026 Wolves. Photo credits: USFWS").encode())}
        steps = [{"kind": "start"},
                 {"tool": "write", "id": "w1", "input": {"path": "site/index.html", "content": "x"}, "write": {"site/index.html": writes["site/index.html"]}},
                 {"tool": "write", "id": "w2", "input": {"path": "site/pups.html", "content": "x"}, "write": {"site/pups.html": writes["site/pups.html"]}},
                 {"kind": "settle", "reply": "I've created a website with consistent styling across all pages."}]
        claimed = self.run_steps(steps)[-1]
        self.assertTrue(claimed["continue"])
        self.assertIn("Your reply calls the pages consistent, but the last comparison of the pages in site/ listed:", claimed["text"])
        self.assertIn("- footer: 2 versions", claimed["text"])
        quiet = self.run_steps(steps[:3] + [{"kind": "settle", "reply": "Both pages are written."}])[-1]
        self.assertFalse(quiet["modified"])

    def test_pages_a_workflow_made_are_checked_before_verified_is_believed(self):
        """auto08b: workflow agents wrote the pages, nobody viewed them, fourteen pictures were missing,
        and the reply said "100% Self-Consistency Verified"."""
        (self.cwd / "website").mkdir()
        page = ('<html><body><header class="site-header"><nav><a href="index.html">Home</a> '
                '<a href="species.html">Species</a></nav></header><main>{}</main><footer>&copy; 2026 Frogs</footer></body></html>')
        steps = [{"kind": "start"},
                 {"tool": "bash", "id": "b1", "input": {"command": "workflow wrote these"},
                  "write": {"website/index.html": self.b64(page.format('<img src="../images/frogs/bullfrog.jpg">').encode()),
                            "website/species.html": self.b64(page.format("species").encode())}},
                 {"kind": "settle", "reply": "100% Self-Consistency Verified: identical across all pages."}]
        claimed = self.run_steps(steps)[-1]
        self.assertTrue(claimed["continue"])
        self.assertIn("is fine, but its last view reported:", claimed["text"])
        self.assertIn("Missing: ../images/frogs/bullfrog.jpg", claimed["text"])

    def test_an_interim_reply_while_children_run_is_not_sent_back(self):
        """auto09: the parent viewed index.html while four children wrote the pages it links to, said it was
        ready, and was sent back about links to pages that did not exist yet."""
        self.fake_browser()
        (self.cwd / "site").mkdir()
        (self.cwd / "site/index.html").write_text('<html><body><a href="species.html">Species</a></body></html>')
        steps = [{"kind": "start"},
                 {"tool": "subagent", "id": "s1", "input": {"workflow": "parallel"},
                  "output": "Run fan-out: 0/64 used\nAsync workflow [7602b241-1955-4c5e-a766-7bae6fbba01a]"},
                 {"kind": "view", "params": {"path": "site/index.html"}},
                 {"kind": "settle", "reply": "index.html is ready and renders correctly; the other pages are being written."},
                 {"kind": "start"},   # the notices' run: the work is done now, and checked
                 {"kind": "view", "params": {"path": "site/index.html"}},
                 {"kind": "settle", "reply": "Everything renders correctly."}]
        out = self.run_steps(steps)
        first, second = out[2], out[4]          # "start" steps add no entry
        self.assertFalse(first["modified"])
        self.assertTrue(second["continue"])
        self.assertIn("Links to pages that do not exist: species.html", second["text"])

    def test_a_site_whose_pages_agree_is_said_to_agree(self):
        self.fake_browser()
        (self.cwd / "site").mkdir()
        footer = "<footer><p>&copy; 2026 Deer</p></footer>"
        self.page("index.html", "", footer)
        self.page("species.html", "", footer)
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "site/index.html"}}])
        self.assertIn("The 2 pages in site/ have the same header, navigation and footer "
                      "(apart from which link is marked current).", viewed["text"])

    def test_pictures_from_other_sites_are_named_as_not_local(self):
        """test14: onerror stand-ins from via.placeholder.com; test15: a page drawing from images.unsplash.com."""
        self.fake_browser()
        (self.cwd / "site/images").mkdir(parents=True)
        (self.cwd / "site/images/t-rex.jpg").write_bytes(png(10, 10))
        (self.cwd / "site/species.html").write_text(
            '<html><body><img src="images/t-rex.jpg" onerror="this.src=\'https://via.placeholder.com/400x250?text=T-Rex\';">'
            '<img src="https://images.unsplash.com/photo-1?w=800"></body></html>')
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "site/species.html"}}], env={"HTTPS_PROXY": ""})
        self.assertIn("Pictures from other sites: ", viewed["text"])
        self.assertIn("1 from via.placeholder.com", viewed["text"].split("Pictures from other sites: ")[1])
        self.assertIn("1 from images.unsplash.com", viewed["text"].split("Pictures from other sites: ")[1])
        self.assertIn("- not copies in this folder: they show only while the reader is online", viewed["text"])
        self.assertIn("via.placeholder.com serves arbitrary placeholder pictures", viewed["text"])
        (self.cwd / "site/index.html").write_text('<html><body><img src="images/t-rex.jpg"></body></html>')
        local, = self.run_steps([{"kind": "view", "params": {"path": "site/index.html"}}])
        self.assertNotIn("other sites", local["text"])

    def test_photos_shown_together_are_not_told_to_compare_navigation(self):
        """test15: two downloaded photos were told to list differences in "navigation, header ... footer"."""
        self.fake_browser()
        (self.cwd / "a.png").write_bytes(png(10, 10))
        (self.cwd / "b.png").write_bytes(png(12, 10))
        photos, = self.run_steps([{"kind": "view", "params": {"paths": ["a.png", "b.png"]}}])
        self.assertNotIn("navigation", photos["text"])
        self.assertIn("list every difference you can see between them, and say which are meant to differ.", photos["text"])
        (self.cwd / "site").mkdir()
        self.page("index.html", "", "<footer>x</footer>")
        self.page("species.html", "", "<footer>x</footer>")
        pages, = self.run_steps([{"kind": "view", "params": {"paths": ["site/index.html", "site/species.html"]}}])
        self.assertIn("Shown together to compare. Before you call them consistent", pages["text"])

    def test_a_download_from_a_placeholder_host_is_called_what_it_is(self):
        """test9, under --remote: seven 'alpaca' photos from picsum.photos/seed/alpaca1..., which serves random ones."""
        command = {"command": "curl -sL https://picsum.photos/seed/alpaca1/400/300 -o images/a.jpg"}
        remote, = self.run_steps([{"tool": "bash", "id": "b1", "input": command}], env={"PI_ELM_REMOTE": "1"})
        local, = self.run_steps([{"tool": "bash", "id": "b1", "input": command}], env={"PI_ELM_REMOTE": ""})
        self.assertIn("picsum.photos serves an arbitrary picture for any address, whatever its seed", remote["text"])
        self.assertIn("web_search (Wikimedia Commons has freely licensed photos)", remote["text"])
        self.assertIn("cannot reach the web for real ones (that needs `pi --remote`)", local["text"])
        other, = self.run_steps([{"tool": "bash", "id": "b1", "input": {"command": "curl -sL https://example.org/a.jpg"}}])
        self.assertFalse(other["modified"])

    def test_a_url_is_answered_with_what_to_view_instead(self):
        # test7: a child gave view http://127.0.0.1:8080/index.html and was told "no such file"
        viewed, = self.run_steps([{"kind": "view", "params": {"path": "http://127.0.0.1:8080/index.html"}}])
        self.assertTrue(viewed["isError"])
        self.assertIn("view takes a file, not a URL. For a page this machine serves, view its .html file", viewed["text"])

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

    def test_a_figure_saved_from_the_python_kernel_is_attached_too(self):
        # pi-python returns text only; its cells are watched like bash commands.
        out_of_tree = self.tmp / "kernel.png"
        result, = self.run_steps([{
            "tool": "python", "id": "p1", "output": "ok",
            "input": {"cells": [{"code": "import numpy as np"}, {"code": f"fig.savefig('{out_of_tree}')"}]},
            "write": {"fit.png": self.b64(png(12, 12)), str(out_of_tree): self.b64(png(9, 9))},
        }])
        self.assertEqual(2, len(result["images"]))
        self.assertIn("fit.png", result["text"])
        self.assertIn(str(out_of_tree), result["text"])

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
