"""The failures seen in the test10-test13 sessions (2026-11-13), each replayed through the code that now
handles it, so none of them comes back unnoticed.

Every case reproduces what the session actually did - the task text a parent wrote, the file a download
left behind, the reply the model ended with - cut down and with this machine's paths taken out, and runs
it through the extension that shipped to stop it. Where the fix is a sentence in a prompt (the model has
to read it; nothing can enforce it), the sentence is pinned instead.

    test10  five children building one page each of a worm site under `pi --remote`
    test11  a `workflow` run of eight agents, before workflow agents loaded the guards
    test12  a `--remote` site whose model read Wikimedia's own refusals as the egress proxy
    test13  `/ultracode` in a manual session: a workflow that could only read, then placeholders
    test14  dinosaurs, five children under `pi --remote`: a "../" stylesheet, Wikimedia 429s, stand-ins
    test15  dinosaurs, `/ultracode`: a retyped workflow script, page prompts that named CSS they never got
    auto01  otters, a driven session (scratchpad iter/drive.mjs over `pi --mode rpc`): four page tasks told
            to copy index.html while a sibling wrote it, and bg_wait called four times after its refusal
    auto02  owls in manual mode: 31 dialogs in 16 minutes, and a qwen child told to "use web_search"
    auto04  bees without --remote: downloads delegated, refused 19 times, labelled boxes called "downloaded";
            and a request that stalled 921 s mid-upload
    auto08  frogs on Mistral: hand-made 129-byte "JPEGs" attached, and the gateway's 400 ended the session;
            the rerun's workflow pages, with fourteen missing pictures, called "100% Self-Consistency Verified"
    auto09  sharks: a search with raw spaces in its URL, and an interim reply sent back while children wrote
    auto10  butterflies in manual mode: five guessed Commons names refused in a row (the refusal now searches)
    auto11  tortoises: every page child fetching its own pictures at once, and eight refused waits in 45 s
    auto12  Mauna Loa CO2: a straight line through 50 years, its misfit called "intrinsic scatter" to make chi2/ndf 1
    auto13  a Python unit-converter package: its README.md refused as an unrequested report
    auto14  "the paper that announced GW150914": the companion detector paper summarised instead
    auto15  red squirrels in manual mode: launches refused over pictures already in the site folder
    auto16  pine martens in manual mode: a launch over pi-subagents' 16 KB limit, each task pasting the same text
    auto17  grey seals, /ultracode: a Commons URL with raw spaces, which curl refuses
    auto19  "a 3-page LaTeX document": six pages delivered, the extra called natural expansion
    auto20  a Bateman notebook: a cut output preview, and a peak time in the reply that was in no output
    auto21  the same notebook: `pip3 install --break-system-packages` into Homebrew's Python (92 packages)
    auto22  the same notebook on an install with its own Python: one command, no environment built, 0.36M tokens
    auto23  fix a seeded project's failing tests: right fixes in 43 s, after installing pytest first
    auto24  a half-life from counts: scipy's minimiser said "converged" 15 units of -2 ln L above the minimum
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "templates/extensions"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
QWEN = CONFIG["models"]["qwen"]
LAUNCHER = (ROOT / "pi").read_text()
RUN = "be162096-3f6e-4000-9cd0-ae4ffd3f4050"
FORK = ("You are a delegated subagent running from a fork of the parent session. Treat the inherited conversation "
        "as reference-only context.\n\nTask:\n")


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def run_node(test, script, *args, env=None, cwd=None):
    binary = node()
    if not binary:
        test.skipTest("needs node")
    run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, *map(str, args)],
                         capture_output=True, text=True, timeout=120, cwd=cwd or ROOT,
                         env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd or ROOT), **(env or {})})
    if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
        test.skipTest("this node cannot load TypeScript")
    test.assertEqual(0, run.returncode, run.stderr[-2000:])
    return json.loads(run.stdout.strip().splitlines()[-1])


def view_outputs(test, tmp):
    """view-outputs.ts beside a typebox stub (pi supplies the real one); its page checks need nothing else."""
    ext = Path(tmp) / "ext"
    (ext / "node_modules/typebox").mkdir(parents=True)
    (ext / "node_modules/typebox/package.json").write_text('{"name":"typebox","type":"module","main":"index.js"}')
    (ext / "node_modules/typebox/index.js").write_text(
        "const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Optional: f, Boolean: f, Array: f };")
    shutil.copy(EXT / "view-outputs.ts", ext / "view-outputs.ts")
    return ext / "view-outputs.ts"


CALL = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
        "const [fn, args] = [process.argv[2], JSON.parse(process.argv[3])];"
        "const r = await m[fn](...args); console.log(JSON.stringify(r ?? null));")


def call(test, source, fn, *args, env=None, cwd=None):
    return run_node(test, CALL, source, fn, json.dumps(list(args)), env=env, cwd=cwd)


def what_it_holds(test, source, body):
    """What view-outputs says a file of these bytes holds."""
    script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
              "console.log(JSON.stringify(m.whatItHolds(Uint8Array.from(Buffer.from(process.argv[2], 'base64')))));")
    return run_node(test, script, source, base64.b64encode(body).decode())


def msg(role, text, **extra):
    return {"type": "message", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "message": {"role": role, "content": [{"type": "text", "text": text}], **extra}}


def parent_branch(tasks):
    """A parent's parallel launch of these tasks, and its result, as pi records them."""
    launch = {"type": "toolCall", "id": "c1", "name": "subagent",
              "arguments": {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": t} for t in tasks]}}}
    return [msg("user", "use 5 agents make me a website about worms"),
            {"type": "message", "timestamp": "2026-11-13T00:17:18.000Z", "message": {"role": "assistant", "content": [launch]}},
            msg("toolResult", f"Async workflow [{RUN}]", toolCallId="c1", toolName="subagent", isError=False)]


# A site written as several sessions left them: (file -> html). {nav} is the same navigation on every page.
NAV = ('<nav class="navbar"><a href="index.html" class="active">Home</a> <a href="species.html">Species</a> '
       '<a href="habitat.html">Habitat</a></nav>')


def page(title_banner="", footer="<footer><p>&copy; 2026 World of Worms</p></footer>", body="", nav=NAV):
    return (f'<!DOCTYPE html><html><head><link rel="stylesheet" href="css/style.css"></head><body>{nav}'
            f"{title_banner}<main>{body}</main>{footer}</body></html>")


def write_site(root, files):
    for name, content in files.items():
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)


class Test10(unittest.TestCase):
    """test10: worms, five children, `pi --remote`."""

    def tasks(self, site):
        """The second launch's tasks, as test10's parent wrote them (shortened)."""
        return [f"Create the homepage at {site}/index.html. Copy the navigation bar and footer EXACTLY from template.html.",
                f"Create the anatomy page at {site}/anatomy.html. Copy navigation and footer EXACTLY from template.html.",
                f"Create the species page at {site}/species.html. Copy navigation and footer EXACTLY from template.html.",
                f"Create the gallery page at {site}/gallery.html. Each gallery-item has an img tag "
                f"(placeholder paths like images/worm1.jpg through images/worm6.jpg)."]

    def test_the_first_launch_with_the_stylesheet_as_one_childs_task_was_refused(self):
        with tempfile.TemporaryDirectory() as site:
            launch = {"workflow": "parallel", "args": {"tasks": [
                {"agent": "qwen", "task": f"Create a shared CSS stylesheet for a worm website at {site}/css/style.css."},
                *[{"agent": "qwen", "task": f"Create {p}.html at {site}/{p}.html. Use consistent navigation. "
                                            "The page should reference css/style.css."} for p in ("index", "anatomy", "species")],
            ]}}
            script = ("import { pathToFileURL } from 'node:url'; import { existsSync } from 'node:fs';"
                      "const m = await import(pathToFileURL(process.argv[1]).href);"
                      "console.log(JSON.stringify(m.sharedGaps(JSON.parse(process.argv[2]), process.argv[3], existsSync) ?? null));")
            reason = run_node(self, script, EXT / "owner-guard.ts", json.dumps(launch), site)
        self.assertIn("css/style.css: named by task-2, task-3 and task-4, and not there yet", reason)

    def test_children_building_pages_may_not_draw_the_users_images_themselves(self):
        """Three page children wrote worm1-6.svg into images/, which only the gallery's task named."""
        with tempfile.TemporaryDirectory() as site:
            tasks = self.tasks(site)
            branch = parent_branch(tasks) + [msg("user", FORK + tasks[2])]          # the species child
            gallery = parent_branch(tasks) + [msg("user", FORK + tasks[3])]
            script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                      "const [species, gallery, site] = [JSON.parse(process.argv[2]), JSON.parse(process.argv[3]), process.argv[4]];"
                      "const may = (b, p) => m.mayCreate(m.childScope(b, site), `${site}/${p}`, site);"
                      "console.log(JSON.stringify([may(species, 'images/worm1.svg'), may(species, 'species.html'),"
                      " may(gallery, 'images/worm1.jpg')]));")
            out = run_node(self, script, EXT / "owner-guard.ts", json.dumps(branch), json.dumps(gallery), site)
        self.assertEqual([False, True, True], out)

    def test_children_are_told_they_have_no_web_tools(self):
        """Forked children see the parent's web tools declared; each call answered "not found"."""
        qwen = " ".join((ROOT / "templates/agents/qwen.md").read_text().split())
        self.assertIn("**No web of your own.** You have no `web_search`, `fetch_content` or other web tool", qwen)
        research = " ".join((EXT / "remote-research.ts").read_text().split())
        self.assertIn("A `qwen` sub-agent has no web tools", research)

    def test_the_site_check_names_its_leftovers_and_saved_error_pages(self):
        error = b'<!DOCTYPE html><html><head><title>Wikimedia Error</title></head><body>Error</body></html>'
        with tempfile.TemporaryDirectory() as tmp:
            source = view_outputs(self, tmp)
            site = Path(tmp) / "site"
            write_site(site, {"index.html": page(body='<img src="images/earthworm.jpg">'), "species.html": page(),
                              "habitat.html": page(), "template.html": page(), "css/style.css": "body {}",
                              "images/earthworm.jpg": error, "images/worm1.svg": "<svg/>"})
            compared = call(self, source, "compareSite", str(site), "in site/")
            resources = call(self, source, "pageResources", str(site / "index.html"))
        self.assertIn("- images/worm1.svg: in the site, but no page uses it.", compared)
        self.assertIn("- template.html: no page links to it.", compared)
        self.assertEqual("images/earthworm.jpg", resources["broken"][0]["file"])
        self.assertIn('web page titled "Wikimedia Error"', resources["broken"][0]["holds"])

    def test_the_closing_consistent_over_listed_differences_is_sent_back(self):
        """test10 ended "Excellent! The website is complete and visually consistent." over the comparison."""
        with tempfile.TemporaryDirectory() as tmp:
            note = call(self, view_outputs(self, tmp), "claimNote",
                        "Excellent! The website is complete and visually consistent.",
                        {"differences": {"place": "here", "lines": ["- template.html: no page links to it."]}})
        self.assertIn("Your reply calls the pages consistent, but the last comparison of the pages here listed:", note)


class Test11(unittest.TestCase):
    """test11: a workflow of eight agents, before workflow agents loaded the guards."""

    REQUEST = ("use 5 agents make me a website about worms and make sure everything is 100% self-consistent and check "
               "the visual renderings between each subpage for consistency download images from the internet")
    # from test11's script: the verification agent's task, its last lines
    VERIFY = ("Verify the entire website for consistency and completeness.\n...\n"
              "Create a report file at ${siteDir}/VERIFICATION_REPORT.md with:\n- What was checked\n- Issues found\n\n"
              "Report: summary of verification results and any issues fixed.")

    def guard(self, tool, input_, asked, cwd):
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "const branch = [{ type: 'message', message: { role: 'user', content: [{ type: 'text', text: process.argv[4] }] } }];"
                  "const r = await h.tool_call({ type: 'tool_call', toolCallId: 't', toolName: process.argv[2], input: JSON.parse(process.argv[3]) },"
                  " { cwd: process.argv[5], sessionManager: { getBranch: () => branch } });"
                  "console.log(JSON.stringify(r?.block ? r.reason : null));")
        return run_node(self, script, EXT / "report-guard.ts", tool, json.dumps(input_), asked, cwd)

    def test_a_workflow_that_tells_an_agent_to_write_an_unrequested_report_is_not_started(self):
        script = f"export const meta = {{ name: 'worms' }};\nconst verifyTask = `{self.VERIFY}`;\nawait agent(verifyTask);"
        with tempfile.TemporaryDirectory() as cwd:
            refused = self.guard("workflow", {"script": script}, self.REQUEST, cwd)
            asked = self.guard("workflow", {"script": script}, self.REQUEST + " and write a verification report", cwd)
        self.assertIn("Not started: it tells an agent to write VERIFICATION_REPORT.md, which the user did not ask for", refused)
        self.assertIsNone(asked)

    def test_report_colon_in_a_task_asks_for_a_reply_not_a_file(self):
        """An agent told only "Report: summary of verification results" may not create VERIFICATION_REPORT.md."""
        with tempfile.TemporaryDirectory() as cwd:
            refused = self.guard("write", {"path": "VERIFICATION_REPORT.md", "content": "x"},
                                 "Verify the website.\n\nReport: summary of verification results and any issues fixed.", cwd)
        self.assertIn("Nobody asked for VERIFICATION_REPORT.md", refused)

    def test_a_pages_own_title_banner_is_not_compared_as_the_site_header(self):
        """test11 was told "header: 5 versions" of each page's own <header class="page-header"><h1>...."""
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            write_site(site, {f"{p}.html": page(f'<header class="page-header"><h1>{p.title()}</h1></header>')
                              for p in ("index", "species", "habitat")} | {"css/style.css": "body {}"})
            compared = call(self, view_outputs(self, tmp), "compareSite", str(site), "in site/")
        self.assertNotIn("header", compared.split("(apart from")[0].replace("navigation and footer", ""))
        self.assertIn("have the same navigation and footer", compared)

    def test_the_closing_self_consistent_over_five_footers_is_sent_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = call(self, view_outputs(self, tmp), "claimNote",
                        "## Website Complete!\n\nI've created a comprehensive, self-consistent website about worms",
                        {"differences": {"place": "in worms-website/", "lines": ["- footer: 5 versions - a.html | b.html"]}})
        self.assertIn("- footer: 5 versions", note)

    def test_workflow_agents_load_the_report_guard_and_the_date(self):
        """The report was dated "13 November 2024": workflow agents had neither guard then."""
        listed = json.loads((ROOT / "templates/workflows/settings.json").read_text())["providerMiddlewareExtensions"]
        for name in ("report-guard", "date-note", "claim-guard", "owner-guard"):
            self.assertIn(name, listed)

    def test_the_workflow_tool_is_offered_without_a_flag(self):
        """The first session had no workflow tool: it was started without --workflows."""
        self.assertIn('WORKFLOWS="${PI_ELM_WORKFLOWS:-1}"', LAUNCHER)


class Test12(unittest.TestCase):
    """test12: a `--remote` session that read Wikimedia's refusals as the egress proxy."""

    def test_every_text_that_said_a_403_is_this_install_asks_about_remote_first(self):
        egress = (ROOT / "templates/reference/egress.md").read_text()
        self.assertTrue(egress.startswith("# A 403: this install, or the site?\n\n**First: was this session started"))
        self.assertIn("refuses nothing: a 403 or error page is the site's answer",
                      " ".join((ROOT / "templates/AGENTS.md").read_text().split()))
        self.assertIn("The egress proxy refuses nothing in this session", " ".join((EXT / "remote-research.ts").read_text().split()))

    def test_a_saved_wikimedia_error_page_says_what_wikimedia_said(self):
        body = (b'<!DOCTYPE html><html lang="en"><title>Wikimedia Error</title><div><h1>Error</h1><p>Use thumbnail sizes '
                b'listed on https://w.wiki/GHai</p></div><code>Error: 400, Use thumbnail sizes listed on https://w.wiki/GHai '
                b'at Fri, 13 Nov 2026 09:18:47 GMT</code><p>Sensitive client information IP address: 192.0.2.1</p></html>')
        with tempfile.TemporaryDirectory() as tmp:
            holds = what_it_holds(self, view_outputs(self, tmp), body)
        self.assertIn('saying "HTTP 400: Use thumbnail sizes listed on https://w.wiki/GHai"', holds)
        self.assertNotIn("192.0.2.1", holds)

    def test_pythons_403_from_wikimedia_is_shown_as_its_text(self):
        body = b"Please set a user-agent and respect our robot policy https://w.wiki/4wJS."
        with tempfile.TemporaryDirectory() as tmp:
            holds = what_it_holds(self, view_outputs(self, tmp), body)
        self.assertIn('"Please set a user-agent and respect our robot policy', holds)

    def test_a_coordinator_meant_to_run_after_the_others_is_not_started_beside_them(self):
        with tempfile.TemporaryDirectory() as site:
            launch = {"workflow": "parallel", "args": {"tasks": [
                *[{"agent": "qwen", "task": f"Create {p}.html. Save to: {site}/{p}.html"} for p in ("index", "anatomy")],
                {"agent": "qwen", "task": "COORDINATOR TASK: After the other 4 agents complete their pages: 1. Read all "
                                          "created HTML files 2. Create a unified stylesheet (style.css)"},
            ]}}
            script = ("import { pathToFileURL } from 'node:url'; import { existsSync } from 'node:fs';"
                      "const m = await import(pathToFileURL(process.argv[1]).href);"
                      "console.log(JSON.stringify(m.sharedGaps(JSON.parse(process.argv[2]), process.argv[3], existsSync) ?? null));")
            reason = run_node(self, script, EXT / "owner-guard.ts", json.dumps(launch), site)
        self.assertIn("- task-3 is to start after the others finish", reason)
        self.assertIn("cannot wait for each other", reason)


class Test13(unittest.TestCase):
    """test13: `/ultracode` in a manual session."""

    # test13's script, cut down: what its agents were told to do
    SCRIPT = ("export const meta = { name: 'elephant-website' };\n"
              "const setupTask = `Create the website directory structure and download elephant images for local use.`;\n"
              "const css = await agent(`Write the shared stylesheet to website/styles.css`);")

    def test_a_writing_workflow_in_manual_is_not_started(self):
        """Nine agents, thirteen minutes and 629k tokens, each reporting BLOCKED."""
        refused = call(self, EXT / "permission-mode.ts", "workflowRefusal", "manual", {"script": self.SCRIPT},
                       {"PI_ELM_APPROVED_AGENTS": "auto"})
        self.assertIn("Not started: this session is in manual mode, and there a workflow agent can only read", refused)
        self.assertIsNone(call(self, EXT / "permission-mode.ts", "workflowRefusal", "auto", {"script": self.SCRIPT}))

    def test_an_allowed_launch_does_not_ask_again_for_each_child(self):
        self.assertIn('PI_ELM_MANUAL_ALLOW="${PI_ELM_MANUAL_ALLOW:+$PI_ELM_MANUAL_ALLOW,}subagent_launch"', LAUNCHER)

    def test_commons_file_names_come_from_its_search_not_a_guess(self):
        """A guessed Special:FilePath name came back 404, and the run fell back to placeholders."""
        research = " ".join((EXT / "remote-research.ts").read_text().split())
        self.assertIn("--data-urlencode 'srsearch=African elephant'", research)
        self.assertIn("never guess one", research)
        self.assertIn("404 from `Special:FilePath`", (ROOT / "templates/reference/egress.md").read_text())

    def test_an_svg_drawing_saved_as_jpg_is_named_as_one(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect/></svg>'
        with tempfile.TemporaryDirectory() as tmp:
            holds = what_it_holds(self, view_outputs(self, tmp), svg)
        self.assertIn("holds an SVG drawing", holds)
        self.assertIn("name it .svg", holds)

    def test_rendering_correctly_over_broken_pictures_is_sent_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = call(self, view_outputs(self, tmp), "claimNote",
                        "The website is rendering correctly! The placeholder SVG images are showing as expected.",
                        {"broken": {"page": "website/index.html",
                                    "lines": ["Not an image: images/african-elephant.jpg - it holds an SVG drawing"]}})
        self.assertIn("Your reply says website/index.html is fine, but its last view reported:", note)

    def test_an_agent_whose_writes_were_all_refused_may_not_say_it_created_one(self):
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; }, getActiveTools: () => ['read', 'write'] });"
                  "await h.agent_start({});"
                  "for (let i = 0; i < 3; i++) await h.tool_result({ toolName: 'write', isError: true, content: [] });"
                  "const event = { context: { contextMessages: [{ role: 'user', content: 'Write the shared stylesheet.' },"
                  " { role: 'assistant', content: [{ type: 'text', text: 'The stylesheet file has been created.' }] }] } };"
                  "const r = await h.agent_before_settle(event, { model: { id: process.env.ELM_QWEN_MODEL_ID } });"
                  "console.log(JSON.stringify(r ? r.continue : null));")
        self.assertTrue(run_node(self, script, EXT / "claim-guard.ts", env={"ELM_QWEN_MODEL_ID": QWEN}))


def note_for(test, tmp, page_file):
    """view's note under a page, from the page as it is on disk (a render with no other host reachable)."""
    script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
              "console.log(JSON.stringify(m.resourceNote(m.pageResources(process.argv[2]), false, undefined) ?? null));")
    return run_node(test, script, view_outputs(test, tmp), page_file)


class Test14(unittest.TestCase):
    """test14: dinosaurs, five children, `pi --remote`."""

    def test_a_stylesheet_named_one_folder_up_is_named_where_it_is(self):
        """The tasks said "Link to ../css/style.css" from pages beside the css/style.css the parent had written."""
        with tempfile.TemporaryDirectory() as site:
            (Path(site) / "css").mkdir()
            (Path(site) / "css/style.css").write_text("body {}")
            launch = {"workflow": "parallel", "args": {"tasks": [
                {"agent": "qwen", "task": f"Create the {p.upper()} PAGE ({p}.html).\n1. Use the navigation template in "
                                          "NAVIGATION_TEMPLATE.txt\n2. Link to ../css/style.css for styling"}
                for p in ("species", "timeline", "habitat")]}}
            script = ("import { pathToFileURL } from 'node:url'; import { existsSync } from 'node:fs';"
                      "const m = await import(pathToFileURL(process.argv[1]).href);"
                      "console.log(JSON.stringify(m.sharedGaps(JSON.parse(process.argv[2]), process.argv[3], existsSync) ?? null));")
            reason = run_node(self, script, EXT / "owner-guard.ts", json.dumps(launch), site)
        self.assertIn("- ../css/style.css: named by task-1, task-2 and task-3, and not there yet - css/style.css is: "
                      "\"../\" climbs out of the folder the tasks run in. Name it css/style.css.", reason)
        self.assertIn("Correct the name in every task and launch again.", reason)
        self.assertNotIn("Write those first", reason)

    def test_stand_ins_from_another_site_are_named_as_not_local(self):
        """Four missing pictures got onerror="this.src='https://via.placeholder.com/...'"."""
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            write_site(site, {"species.html": page(body=(
                '<img src="images/velociraptor.jpg" alt="Velociraptor fossil" '
                'onerror="this.src=\'https://via.placeholder.com/400x250?text=Velociraptor+Image\';">'))})
            note = note_for(self, tmp, site / "species.html")
        self.assertIn("Missing: images/velociraptor.jpg", note)
        self.assertIn("Pictures from other sites: 1 from via.placeholder.com - not copies in this folder", note)
        self.assertIn("via.placeholder.com serves arbitrary placeholder pictures", note)

    def test_wikimedias_429_is_explained_and_pictures_are_fetched_in_one_place(self):
        """Five children, then the parent, downloaded at once - mostly guessed names - and got 429 for minutes."""
        egress = " ".join((ROOT / "templates/reference/egress.md").read_text().split())
        self.assertIn("**429 Too Many Requests** from `upload.wikimedia.org`: too many requests at once.", egress)
        self.assertIn("Fetch every picture in one place, yourself or one agent, before the agents that write pages start", egress)
        research = " ".join((EXT / "remote-research.ts").read_text().replace('",\n\t"', " ").split())
        self.assertIn("Fetch them all in one place - yourself or one agent - before the agents that write pages start", research)

    def test_the_readme_it_wrote_at_the_end_was_refused(self):
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "const branch = [{ type: 'message', message: { role: 'user', content: [{ type: 'text', text: process.argv[2] }] } }];"
                  "const r = await h.tool_call({ toolName: 'write', input: { path: 'README.md', content: '# DinoWorld' } },"
                  " { cwd: process.argv[3], sessionManager: { getBranch: () => branch } });"
                  "console.log(JSON.stringify(r?.block ? r.reason : null));")
        with tempfile.TemporaryDirectory() as cwd:
            reason = run_node(self, script, EXT / "report-guard.ts", Test15.REQUEST, cwd)
        self.assertIn("Nobody asked for README.md", reason)


class Test15(unittest.TestCase):
    """test15: dinosaurs, `/ultracode`, one `workflow` run."""

    REQUEST = ("use 5 agents make me a website about dinosaurs and make sure everything is 100% self-consistent and check "
               "the visual renderings between each subpage for consistency download images from the internet to "
               "populate the website for local use")
    # the run's script, cut down: page tasks that say "copy sharedStyles verbatim", and never hold it
    SCRIPT = (
        'export const meta = { name: "dinosaur_website", description: "Create a self-consistent 5-page dinosaur website" };\n'
        "const sharedStyles = `/* Global styles - must be identical across all pages */\n"
        "header { background: linear-gradient(135deg, #2c5530, #4a7c59); }`;\n"
        "const buildPage = (pageName) => `Create the ${pageName} page for a dinosaur website.\n\n"
        "Write to: .pi/tmp/dino-site/${pageName}.html\n\nRequirements:\n"
        "- Use the EXACT same CSS as all other pages (copy sharedStyles verbatim into <style> tag)`;\n"
        'const htmlResults = await parallel(["index", "facts"].map((p) => () => agent(buildPage(p))));\n'
        "return { report: `## Dinosaur Website Created\\n${htmlResults.join('\\n\\n')}` };\n")

    def handler(self, cwd, input_):
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "const input = JSON.parse(process.argv[2]);"
                  "const r = await h.tool_call({ toolName: 'workflow', input }, { cwd: process.argv[3] });"
                  "console.log(JSON.stringify({ block: r?.block ? r.reason : null, script: input.script }));")
        return run_node(self, script, EXT / "workflow-script.ts", json.dumps(input_), cwd,
                        env={"PI_CODING_AGENT_DIR": str(ROOT / "agent")})

    def test_the_checked_file_is_run_instead_of_a_retyped_copy(self):
        """The file passed workflow-check; the copy typed into the call escaped `\\`` and `\\${` and did not parse."""
        fixed = self.SCRIPT.replace("(copy sharedStyles verbatim into <style> tag)", "in a <style> tag:\n${sharedStyles}")
        with tempfile.TemporaryDirectory() as cwd:
            (Path(cwd) / ".pi/tmp").mkdir(parents=True)
            (Path(cwd) / ".pi/tmp/dino-website.mjs").write_text(fixed)
            ran = self.handler(cwd, {"script": ".pi/tmp/dino-website.mjs"})
        self.assertIsNone(ran["block"])
        self.assertEqual(fixed, ran["script"])

    def test_page_prompts_that_name_css_they_never_get_are_not_started(self):
        """Five agents read "copy sharedStyles verbatim", drew five colour schemes, and 384k tokens went to waste."""
        if not (ROOT / "agent/npm/node_modules/acorn").exists():
            self.skipTest("acorn comes with pi-dynamic-workflows (run bootstrap.sh)")
        with tempfile.TemporaryDirectory() as cwd:
            refused = self.handler(cwd, {"script": self.SCRIPT})
        self.assertIn("Not started: `sharedStyles` is never used, so no agent gets its text", refused["block"])

    def test_what_the_user_asked_for_is_not_built_in_pi_tmp(self):
        """The site was built in .pi/tmp/dino-site, rebuilt in .pi/tmp/dino-site-consistent, then copied out."""
        agents = " ".join((ROOT / "templates/AGENTS.md").read_text().split())
        self.assertIn("Keep scratch, never what the user asked for, under `.pi/tmp/`", agents)
        skill = " ".join((ROOT / "templates/skills/elm-dynamic-workflows/SKILL.md").read_text().split())
        self.assertIn("the files the user asked for go where they will look - the launch directory - not `.pi/tmp/`", skill)

    def test_a_page_on_unsplash_is_named_as_not_local(self):
        """carnivores.html drew its pictures from images.unsplash.com in a site asked for "for local use"."""
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            write_site(site, {"carnivores.html": page(body='<img src="https://images.unsplash.com/photo-1?w=800">'
                                                           '<img src="https://images.unsplash.com/photo-2?w=800">')})
            note = note_for(self, tmp, site / "carnivores.html")
        self.assertIn("Pictures from other sites: 2 from images.unsplash.com - not copies in this folder: they show only "
                      "while the reader is online", note)

    # The two photos told to compare "navigation, header ... footer" are in
    # tests/test_view_outputs.py: test_photos_shown_together_are_not_told_to_compare_navigation.


def gaps(test, tasks, site):
    launch = {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": t} for t in tasks]}}
    script = ("import { pathToFileURL } from 'node:url'; import { existsSync } from 'node:fs';"
              "const m = await import(pathToFileURL(process.argv[1]).href);"
              "console.log(JSON.stringify(m.sharedGaps(JSON.parse(process.argv[2]), process.argv[3], existsSync) ?? null));")
    return run_node(test, script, EXT / "owner-guard.ts", json.dumps(launch), site)


class Auto01(unittest.TestCase):
    """auto01: otters, five children, `pi --remote --auto`, driven over RPC."""

    def tasks(self, site):
        return [
            "Create the main index.html page for an otter website. The page should include: a header with site title "
            "\"Otters of the World\", navigation menu linking to all 5 pages (index.html, species.html, habitat.html, "
            f"conservation.html, gallery.html), and a footer consistent across all pages. Write to: {site}/index.html",
            "Create the species.html page. Include: navigation menu (same as index), footer consistent with index.html. "
            f"Use the same CSS classes and styling as index.html for consistency. Write to: {site}/species.html",
            "Create the habitat.html page. Include: navigation menu (same as other pages). Match the exact CSS classes, "
            f"navigation structure, and footer from index.html. Write to: {site}/habitat.html",
            "Create the gallery.html page. Match the exact CSS classes, navigation structure, and footer from "
            f"index.html. Write to: {site}/gallery.html",
        ]

    def test_pages_told_to_copy_a_page_a_sibling_is_writing_are_not_launched(self):
        with tempfile.TemporaryDirectory() as site:
            reason = gaps(self, self.tasks(site), site)
        self.assertIn("- task-2, task-3 and task-4 are told to take their styling, navigation or footer from index.html, "
                      "which a sibling is writing at the same time", reason)
        self.assertIn("Write those first - the stylesheet, and one finished page or a template", reason)

    def test_once_the_page_is_there_the_same_tasks_launch(self):
        with tempfile.TemporaryDirectory() as site:
            (Path(site) / "index.html").write_text("<html></html>")
            tasks = self.tasks(site)[1:]
            self.assertIsNone(gaps(self, tasks, site))

    def test_shared_parts_said_after_the_noun_count_as_shared(self):
        """"footer consistent with other pages" is the same ask as "a consistent footer"."""
        with tempfile.TemporaryDirectory() as site:
            reason = gaps(self, [f"Create {p}.html with a footer consistent with other pages. Write to: {site}/{p}.html"
                                 for p in ("index", "habitat", "gallery")], site)
        self.assertIn("are told to share \"footer consistent with\"", reason)

    def test_a_menu_that_links_the_other_pages_is_not_copying_them(self):
        """test7's tasks listed every page in the menu ("links to about.html, care.html ...") and launched."""
        with tempfile.TemporaryDirectory() as site:
            (Path(site) / "style.css").write_text("body {}")
            reason = gaps(self, [
                f"Write {site}/{p}.html. Link {site}/style.css. Navigation: links to index.html, about.html, care.html "
                "(the same nav on every page, classes from style.css)." for p in ("index", "about", "care")], site)
        self.assertIsNone(reason)

    def test_a_guessed_commons_name_is_refused_until_a_search_lists_it(self):
        """The child fetching pictures guessed eleven names - each a 404 - before it searched Commons."""
        guess = ('curl -fL -A "OtterWebsite/1.0" -o images/giant-otter.jpg '
                 '"https://commons.wikimedia.org/wiki/Special:FilePath/Giant_Otter_%28Pteronura_brasiliensis%29.jpg?width=960"')
        found = ('curl -fL -o images/giant-otter-1.jpg "https://commons.wikimedia.org/wiki/Special:FilePath/'
                 '018%20Giant%20otter%20eating%20a%20fish%20in%20Encontro%20das%20%C3%81guas.jpg?width=960"')
        upload = 'curl -fL -o x.jpg "https://upload.wikimedia.org/wikipedia/commons/2/23/Some_Guessed_Otter.JPG"'
        search = ('{"query":{"search":[{"ns":6,"title":"File:018 Giant otter eating a fish in Encontro das '
                  '\\u00c1guas.jpg"}]}}')
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "m.setCommonsSearch(async () => []);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "await h.session_start({}, { sessionManager: { getBranch: () => [] } });"
                  "const [guess, found, upload, search] = process.argv.slice(2);"
                  "const call = async (c) => { const r = await h.tool_call({ toolName: 'bash', input: { command: c } });"
                  " return r?.block ? r.reason : null; };"
                  "const out = [await call(guess), await call(found), await call(upload)];"
                  "await h.tool_result({ content: [{ type: 'text', text: search }] });"
                  "out.push(await call(found), await call('curl -s https://commons.wikimedia.org/w/api.php?list=search'));"
                  "console.log(JSON.stringify(out));")
        out = run_node(self, script, EXT / "remote-research.ts", guess, found, upload, search, env={"PI_ELM_REMOTE": "1"})
        self.assertIn('Not run: "giant otter (pteronura brasiliensis).jpg" is in no search result of this session', out[0])
        self.assertIn("--data-urlencode 'srsearch=<words, spaces and all>'", out[0])   # auto09: raw spaces broke its own search
        self.assertIsNotNone(out[1])                       # not searched yet
        self.assertIn('"some guessed otter.jpg"', out[2])  # an upload.wikimedia.org path is a name too
        self.assertEqual([None, None], out[3:])            # listed by the search (as \u00c1 in raw JSON): allowed

    def test_a_refused_guess_comes_back_with_the_names_commons_has(self):
        """auto10: refused five times in a row, guessing a new name each time; the refusal now runs the search."""
        guess = ('curl -fL -o monarch.jpg "https://commons.wikimedia.org/wiki/Special:FilePath/'
                 'Danaus_plexippus_March_2013.jpg?width=800"')
        listed = ('curl -fL -o monarch.jpg "https://commons.wikimedia.org/wiki/Special:FilePath/'
                  'Danaus%20plexippus%20(7).jpg?width=800"')
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const asked = []; m.setCommonsSearch(async (w) => { asked.push(w); return ['File:Danaus plexippus (7).jpg',"
                  " 'File:Monarch Butterfly Danaus plexippus on Milkweed Hybrid 2800px.jpg']; });"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "await h.session_start({}, { sessionManager: { getBranch: () => [] } });"
                  "const call = async (c) => { const r = await h.tool_call({ toolName: 'bash', input: { command: c } });"
                  " return r?.block ? r.reason : null; };"
                  "console.log(JSON.stringify([await call(process.argv[2]), await call(process.argv[3]), asked]));")
        refused, then, asked = run_node(self, script, EXT / "remote-research.ts", guess, listed, env={"PI_ELM_REMOTE": "1"})
        self.assertEqual(["danaus plexippus"], asked)       # the name as compared: lower case, which the search ignores
        self.assertIn('Commons\' search, run for you - use one of these exact names (in the URL, spaces as %20): '
                      'for "danaus plexippus": "Danaus plexippus (7).jpg"', refused)
        self.assertIsNone(then)            # a name the refusal listed is a name the session has been shown

    def test_an_interactive_session_is_not_offered_bg_wait(self):
        """bg_wait was refused, then called three more times and followed by a status check, in one turn."""
        launcher = (ROOT / "pi").read_text()
        self.assertIn('[ "$BG_WAIT_USED" = "1" ] || [ "$WITH_ALL" = "1" ] || [ -n "${PI_SUBAGENT_CHILD:-}" ] || '
                      'XT_LIST="${XT_LIST:+$XT_LIST,}bg_wait"', launcher)
        # the rest is in tests/test_launcher_cases.py and tests/test_run_guards.py (WaitGuardTests)


class Auto02(unittest.TestCase):
    """auto02: owls, `pi --remote` in manual mode, driven over RPC."""

    RESEARCH = ("Research owls and gather factual information. Find 5-7 owl species with accurate facts. Use web_search "
                "to verify facts from reliable sources (ornithology sites, wildlife organizations).")
    PHOTOS = ("Download real owl photos from Wikimedia Commons. Search for 5-7 different owl species using the Wikimedia "
              "API. For each species, download one high-quality photo using curl with proper User-Agent header.")

    def refusal(self, launch, web="1"):
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "console.log(JSON.stringify(m.webWithoutTools(JSON.parse(process.argv[2]), process.argv[3] === '1') ?? null));")
        return run_node(self, script, EXT / "owner-guard.ts", json.dumps(launch), web)

    def test_a_child_told_to_search_the_web_is_not_launched(self):
        """It had no web_search: "Tool web_search not found", then 32 turns and 1.8M tokens from memory."""
        parallel = {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": self.RESEARCH},
                                                                {"agent": "qwen", "task": self.PHOTOS}]}}
        reason = self.refusal(parallel)
        self.assertIn("Not launched: task-1 (qwen) is told to search the web, and that child has no web tools - only the "
                      "`researcher` agent has them.", reason)
        self.assertNotIn("task-2", reason)                     # curl from Commons is a child's work: it has bash
        self.assertIn("This session has no web access at all", self.refusal({"agent": "qwen", "task": self.RESEARCH}, "0"))
        self.assertIsNone(self.refusal({"agent": "researcher", "task": self.RESEARCH}))
        self.assertIsNone(self.refusal({"agent": "qwen", "task": self.PHOTOS}))

    def test_a_manual_session_is_told_which_tools_never_ask(self):
        """Seven of its 31 dialogs were ls, grep and cat through bash."""
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; }, registerCommand: () => {} });"
                  "const out = []; for (const mode of ['manual', 'auto']) { process.env.PI_ELM_PERMISSION_MODE = mode;"
                  " const event = { systemPromptOptions: { sections: { permission_mode: 'stale' } } };"
                  " h.before_agent_start(event); out.push(event.systemPromptOptions.sections.permission_mode ?? null); }"
                  "console.log(JSON.stringify(out));")
        manual, auto = run_node(self, script, EXT / "permission-mode.ts")
        self.assertIn("`read`, `grep`, `find`, `ls` and `view` never ask", manual)
        self.assertIsNone(auto)

    def test_reading_a_running_childs_log_is_refused_at_once(self):
        """Five of its dialogs were `tail`/`cat` of a child's output-0.log under async-subagent-runs."""
        guard = (EXT / "wait-guard.ts").read_text()
        self.assertIn('if (event.toolName === "bash" && typeof input.command === "string" && RUN_FILES.test(input.command)) return refuse();', guard)
        # the behaviour is in tests/test_run_guards.py (WaitGuardTests)


class Auto04(unittest.TestCase):
    """auto04: bees, `pi --auto` without --remote, driven over RPC."""

    REQUEST = ("use 5 agents make me a website about bees and make sure everything is 100% self-consistent and check "
               "the visual renderings between each subpage for consistency download images from the internet to "
               "populate the website for local use")

    def note(self, prompt, env):
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "if (!h.before_agent_start) { console.log(JSON.stringify('no handler')); process.exit(0); }"
                  "const r = await h.before_agent_start({ prompt: process.argv[2], systemPromptOptions: { sections: {} } },"
                  " { sessionManager: { getBranch: () => [] } });"
                  "console.log(JSON.stringify(r?.message?.content ?? null));")
        return run_node(self, script, EXT / "remote-research.ts", prompt, env=env)

    def test_a_request_for_downloads_without_web_is_told_so_at_once(self):
        note = self.note(self.REQUEST, {})
        self.assertIn("This session cannot reach the web: it was started without `pi --remote`", note)
        self.assertIn("call it a stand-in in your final reply", note)
        self.assertIsNone(self.note("make me a website about bees", {}))
        self.assertNotEqual(note, self.note(self.REQUEST, {"PI_ELM_WEB": "1", "PI_ELM_REMOTE": "1"}))

    def test_a_child_told_to_download_from_the_web_is_not_launched_without_it(self):
        task = ("Download bee images for the website using curl or wget. Save to ~/sandbox/auto04/images/ from free "
                "sources (Wikimedia Commons, Unsplash, or similar)")
        launch = {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": task},
                                                              {"agent": "qwen", "task": "Create anatomy.html"}]}}
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "console.log(JSON.stringify([m.webWithoutTools(JSON.parse(process.argv[2]), false) ?? null,"
                  " m.webWithoutTools(JSON.parse(process.argv[2]), true) ?? null]));")
        without, with_web = run_node(self, script, EXT / "owner-guard.ts", json.dumps(launch))
        self.assertIn("Not launched: task-1 is told to download from the web, and this session cannot reach it", without)
        self.assertIsNone(with_web)

    def test_an_upload_the_gateway_stops_acknowledging_is_dropped_in_two_minutes(self):
        proxy = (ROOT / "proxy/egress.py").read_text()
        self.assertIn("UNACKED_TIMEOUT_S = 120", proxy)
        self.assertIn("TCP_RXT_CONNDROPTIME = 0x80", proxy)
        # the socket option itself: tests/test_egress_proxy.py, SocketTuningTests


class Auto08(unittest.TestCase):
    """auto08: frogs, `pi --mistral --remote --auto`: ended by a 400 for an attached picture that did not decode."""

    def test_pictures_are_decoded_before_they_are_attached_or_sent(self):
        source = (EXT / "view-outputs.ts").read_text()
        self.assertIn("export async function undecodable(", source)
        self.assertIn("const why = await undecodable(bytes, type);", source)          # before attaching
        self.assertIn("!(await undecodable(bytes, imageType(bytes)))", source)       # before every request
        # the behaviour, with the session's own 129-byte file: tests/test_view_outputs.py,
        # test_a_picture_that_does_not_decode_is_never_attached and the context test after it

    def test_a_bulk_download_into_the_project_is_named(self):
        """The rerun's workflow agents left a 410 MB dataset of 7,796 images, and two cloned repositories."""
        with tempfile.TemporaryDirectory() as tmp:
            script = ("import { pathToFileURL } from 'node:url'; import { mkdirSync, writeFileSync } from 'node:fs';"
                      "const m = await import(pathToFileURL(process.argv[1]).href); const root = process.argv[2];"
                      "const since = Date.now() - 1000; mkdirSync(root + '/frog_images', { recursive: true });"
                      "for (let i = 0; i < 30; i++) writeFileSync(`${root}/frog_images/frog-${i}.png`, Buffer.alloc(200));"
                      "const view = (await import(pathToFileURL(process.argv[1]).href)).default;"
                      "console.log(JSON.stringify([m.bulkNote('curl -L -o frogs.tar.gz https://x/y && tar xzf frogs.tar.gz', root, since, 5000, 20) ?? null,"
                      " m.bulkNote('python3 build.py', root, since, 5000, 20) ?? null,"
                      " m.bulkNote('git clone https://x/y', root, since) ?? null]));")
            bulk, other, small = run_node(self, script, view_outputs(self, tmp), Path(tmp) / "proj")
        self.assertIn("[view-outputs] This command added 30 files, 0 MB, to the project folder: frog_images (0 MB).", bulk)
        self.assertIn("a few pictures, not a dataset", bulk)
        self.assertIsNone(other)          # not a download
        self.assertIsNone(small)          # under 100 MB and 2,000 files


class Auto11(unittest.TestCase):
    """auto11: tortoises, five children, `pi --remote --auto`."""

    def test_several_children_fetching_pictures_at_once_are_not_launched(self):
        tasks = [{"agent": "qwen", "task": f"Create {p}.html. Download 3 {p} photos from Wikimedia Commons with curl "
                                          "into images/." } for p in ("species", "habitat", "diet")]
        one = [{"agent": "qwen", "task": "Download every picture the site needs from Wikimedia Commons into images/."},
               {"agent": "qwen", "task": "Create species.html using images/tortoise-1.jpg."}]
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const [a, b] = [JSON.parse(process.argv[2]), JSON.parse(process.argv[3])];"
                  "console.log(JSON.stringify([m.webWithoutTools({ workflow: 'parallel', args: { tasks: a } }, true) ?? null,"
                  " m.webWithoutTools({ workflow: 'parallel', args: { tasks: b } }, true) ?? null]));")
        several, single = run_node(self, script, EXT / "owner-guard.ts", json.dumps(tasks), json.dumps(one))
        self.assertIn("Not launched: task-1, task-2, task-3 are each told to download from the web.", several)
        self.assertIn("Fetch every picture in one place first", several)
        self.assertIsNone(single)               # one agent fetching for the rest is the way

    def test_a_third_refused_wait_ends_the_turn(self):
        guard = (EXT / "wait-guard.ts").read_text()
        self.assertIn("export const ENOUGH = 3;", guard)
        # the behaviour: tests/test_run_guards.py, test_a_third_refused_wait_in_a_turn_ends_the_turn


class Auto12(unittest.TestCase):
    """auto12: fit NOAA's Mauna Loa CO2 record (data-fitting and uncertainty-propagation were routed)."""

    def test_the_fitting_skill_says_to_fix_the_model_not_the_errors(self):
        skill = " ".join((ROOT / "templates/skills/data-fitting/SKILL.md").read_text().split())
        self.assertIn("**Fix the model, not the errors.**", skill)
        self.assertIn('Adding an "intrinsic scatter" in quadrature until χ²/ndf ≈ 1 makes any model fit', skill)
        self.assertIn("a yearly cycle's harmonics have T = 1, 1/2, 1/3 yr", skill)


class Auto13(unittest.TestCase):
    """auto13: "a small Python command-line tool ... with a proper package layout and tests"."""

    REQUEST = ("Write a small Python command-line tool, unitconv, that converts between common units of length, mass "
               "and temperature. Give it a proper package layout and tests, run the tests, and show me a few examples.")

    def write_readme(self, cwd):
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "const branch = [{ type: 'message', message: { role: 'user', content: [{ type: 'text', text: process.argv[2] }] } }];"
                  "const r = await h.tool_call({ toolName: 'write', input: { path: 'README.md', content: '# unitconv' } },"
                  " { cwd: process.argv[3], sessionManager: { getBranch: () => branch } });"
                  "console.log(JSON.stringify(r?.block ? r.reason : null));")
        return run_node(self, script, EXT / "report-guard.ts", self.REQUEST, cwd)

    def test_a_packages_readme_is_part_of_the_package(self):
        with tempfile.TemporaryDirectory() as package, tempfile.TemporaryDirectory() as site:
            (Path(package) / "pyproject.toml").write_text("[project]\nname = 'unitconv'\n")
            (Path(site) / "index.html").write_text("<html></html>")
            self.assertIsNone(self.write_readme(package))
            self.assertIn("Nobody asked for README.md", self.write_readme(site))   # a website's README is still a report


class Auto14(unittest.TestCase):
    """auto14: find, download and summarise the GW150914 discovery paper (`pi --remote`)."""

    def test_the_research_prompt_says_to_check_it_is_the_document_asked_for(self):
        research = " ".join((EXT / "remote-research.ts").read_text().replace('",\n\t"', " ").split())
        self.assertIn("Asked about a particular paper, report or page, check that what you found is that one", research)
        self.assertIn("a search for one paper finds its companions", research)


class Auto15(unittest.TestCase):
    """auto15: red squirrels, `pi --remote` in manual mode, driven over RPC."""

    def test_files_in_a_folder_the_tasks_name_are_there(self):
        """The parent downloaded the pictures into red-squirrel-website/images/, named the folder in each task
        ("... website at .../red-squirrel-website/") and the pictures as images/..., and was refused three times
        for files "not there yet" - then wrote all five pages itself."""
        with tempfile.TemporaryDirectory() as cwd:
            site = Path(cwd).resolve() / "red-squirrel-website"
            (site / "images").mkdir(parents=True)
            for name in ("red-squirrel-portrait.jpg", "scottish-woodland.jpg"):
                (site / "images" / name).write_bytes(b"\xff\xd8\xff")
            (site / "main.css").write_text("body {}")
            (site / "index.html").write_text("<html></html>")
            tasks = [f"Create {p}.html for the red squirrel website at {site}/\n\nEXISTING FILES TO MATCH:\n"
                     "- index.html (navigation structure, footer)\n- main.css (all styling)\n\nAVAILABLE IMAGES:\n"
                     "- images/red-squirrel-portrait.jpg\n- images/scottish-woodland.jpg" for p in ("about", "habitat")]
            self.assertIsNone(gaps(self, tasks, cwd))
            (site / "images/scottish-woodland.jpg").unlink()
            self.assertIn("images/scottish-woodland.jpg: named by task-1 and task-2, and not there yet", gaps(self, tasks, cwd))


class Auto16(unittest.TestCase):
    """auto16: pine martens, manual mode: five tasks each carrying the same page of instructions."""

    def test_the_delegation_skill_says_to_name_shared_text_not_paste_it(self):
        skill = " ".join((ROOT / "templates/skills/elm-delegation/SKILL.md").read_text().split())
        self.assertIn("Name it, do not paste it: a launch's tasks travel in one call of at most 16 KB", skill)


class Auto17(unittest.TestCase):
    """auto17: grey seals, `/ultracode` in auto mode with `--remote`."""

    def test_spaces_in_a_quoted_commons_file_url_are_encoded_before_it_runs(self):
        command = ('curl -fL -o seal.jpg "https://commons.wikimedia.org/wiki/Special:FilePath/Grey seal pup.jpg?width=960" '
                   '&& echo "two words here"')
        script = ("import { pathToFileURL } from 'node:url'; const m = await import(pathToFileURL(process.argv[1]).href);"
                  "m.setCommonsSearch(async () => []);"
                  "const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                  "await h.session_start({}, { sessionManager: { getBranch: () => [] } });"
                  "await h.tool_result({ content: [{ type: 'text', text: 'File:Grey seal pup.jpg' }] });"
                  "const event = { toolName: 'bash', input: { command: process.argv[2] } };"
                  "const r = await h.tool_call(event);"
                  "console.log(JSON.stringify([r?.block ?? null, event.input.command]));")
        blocked, ran = run_node(self, script, EXT / "remote-research.ts", command, env={"PI_ELM_REMOTE": "1"})
        self.assertIsNone(blocked)
        self.assertEqual('curl -fL -o seal.jpg "https://commons.wikimedia.org/wiki/Special:FilePath/Grey%20seal%20pup.jpg'
                         '?width=960" && echo "two words here"', ran)


class Auto19(unittest.TestCase):
    """auto19: a 3-page LaTeX document on the photoelectric effect with a Python figure, `pi --auto`."""

    def test_the_documents_skill_holds_a_page_count_as_a_requirement(self):
        skill = " ".join((ROOT / "templates/skills/physics-documents/SKILL.md").read_text().split())
        self.assertIn("A length asked for is a requirement.", skill)
        self.assertIn("compare the built count with it and cut", skill)


class Auto20(unittest.TestCase):
    """auto20: a Jupyter notebook for the Po-218 decay chain, `pi --auto`. Its summary cut the peak-activity
    table after two rows; tests/test_ext_notebook_outputs.py holds the note that names it. Here: the
    extension is installed, and the skill says the same."""

    def test_the_note_is_installed_and_the_skill_says_to_read_a_cut_output_whole(self):
        required = json.loads((ROOT / "config/elm-pi.json").read_text())["requiredExtensions"]
        self.assertIn("notebook-outputs.ts", required)
        skill = " ".join((ROOT / "templates/skills/scientific-python/SKILL.md").read_text().split())
        self.assertIn("read a cut one whole with `notebook_read_cell_output` before quoting it", skill)


class Auto21(unittest.TestCase):
    """auto21: Homebrew's Python refused `pip3 install` (PEP 668), and the model added
    --break-system-packages. tests/test_permission_rules.py holds every spelling's refusal; here, the one
    that ran."""

    def test_the_command_that_ran_is_refused(self):
        rules = json.loads((EXT / "pi-permission-system/config.json").read_text())["permission"]["bash"]
        self.assertEqual("deny", rules["*break-system-packages*"]["action"])
        self.assertIn("system's Python", rules["*break-system-packages*"]["reason"])


class Auto22(unittest.TestCase):
    """auto22: with the agent's Python built by default (asked for on 2026-11-14 after auto18-21 each
    worked around its absence), the notebook ran with `jupyter nbconvert` at the first try."""

    def test_the_agents_python_is_built_by_default_and_dev_setup_stays_offline(self):
        bootstrap = (ROOT / "bootstrap.sh").read_text()
        self.assertIn("WITH_PYTHON=1;", bootstrap)
        self.assertIn("--no-python) WITH_PYTHON=0; WITH_PYPI_INDEX=0 ;;", bootstrap)
        self.assertIn("./bootstrap.sh --no-python < /dev/null", (ROOT / "scripts/dev-setup.sh").read_text())
        packages = json.loads((ROOT / "config/elm-pi.json").read_text())["python"]["packages"]
        for needed in ("numpy", "scipy", "matplotlib", "nbconvert", "ipykernel", "pytest"):   # pytest: auto23
            self.assertIn(needed, packages)


class Auto24(unittest.TestCase):
    """auto24: Ba-137m counts, a Cash-statistic fit by scipy.optimize.minimize(L-BFGS-B) that stopped at
    its start and reported success: 145.1 +- 1.3 s, where the minimum is 151.5 +- 2.7 s."""

    def test_the_fitting_skill_says_a_minimisers_success_is_not_proof(self):
        skill = " ".join((ROOT / "templates/skills/data-fitting/SKILL.md").read_text().split())
        self.assertIn("Not `scipy.optimize.minimize` for a likelihood fit unless you check it.", skill)
        self.assertIn("restart it from its own result with another method (Nelder-Mead)", skill)
        # auto25 read the warning and used minimize all the same: the skill now carries the fit to copy.
        self.assertIn("m = Minuit(cash, N0=n[0]", skill)
        self.assertIn("assert m.valid, m.fmin", skill)
        self.assertIn("iminuit", json.loads((ROOT / "config/elm-pi.json").read_text())["python"]["packages"])


if __name__ == "__main__":
    unittest.main()
