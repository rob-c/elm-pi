"""templates/extensions/network.ts (/network), and the proxy route it uses to tighten a session.

A running session can be tightened and not opened up: the proxy takes a narrower list from anyone
and a wider one from nobody, and the OS fence cannot be taken off a process already inside it. The
cases here run /network against a real proxy/egress.py on loopback, and check what the proxy then
allows, what the session's environment says, and what was saved for new sessions.
"""

import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

GATEWAY = "elm.example"
TRUSTED = [GATEWAY, "pypi.example", "search.example"]
BASE = {"ELM_BASE_URL": "https://%s/api/v1" % GATEWAY, "ELM_PROXY_ALLOW": "pypi.example,search.example",
        "ELM_WEB_TOOLS": "web_search,fetch_content"}

# Scripted answers for the two menus, and a record of what each one offered.
SCRIPT = """
const menus = [];
const picks = %s;
ui.select = async (title, options) => { menus.push([title, options]); const p = picks.shift();
  return typeof p === "number" ? options[p] : p; };
const active = [];
globalThis.__active = ["bash", "read", "web_search", "fetch_content"];
pi.setActiveTools = (names) => { active.push(names); };
const state = () => ({ menus, notes: registered.notes, status: registered.statuses.network ?? null, active,
  env: Object.fromEntries(["PI_ELM_NETWORK", "PI_ELM_NETWORK_DEFAULT", "PI_ELM_WEB", "PI_ELM_REMOTE",
    "ELM_PI_PROXY_ALLOW"].map((name) => [name, process.env[name] ?? null])) });
"""


def load_egress():
    spec = importlib.util.spec_from_file_location("elm_pi_egress_for_network", ROOT / "proxy/egress.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def health(port):
    with socket.create_connection(("127.0.0.1", port), 3) as connection:
        connection.sendall(b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n")
        reply = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            reply += chunk
    return json.loads(reply.partition(b"\r\n\r\n")[2])


def post(port, path):
    with socket.create_connection(("127.0.0.1", port), 3) as connection:
        connection.sendall(("POST %s HTTP/1.0\r\nContent-Length: 0\r\n\r\n" % path).encode())
        reply = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            reply += chunk
    head, _, body = reply.partition(b"\r\n\r\n")
    return int(head.split()[1]), json.loads(body)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.agent = Path(self.tmp.name) / "agent"
        self.agent.mkdir()

    def proxy(self, allow):
        port_file = Path(self.tmp.name) / ("proxy-%d.port" % len(list(Path(self.tmp.name).glob("*.port"))))
        process = subprocess.Popen(
            [sys.executable, "-E", "-S", str(ROOT / "proxy/egress.py"), "--allow", ",".join(allow),
             "--port-file", str(port_file), "--log", str(Path(self.tmp.name) / "egress.log")],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def stop():
            process.terminate()
            process.wait(timeout=5)
        self.addCleanup(stop)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not port_file.exists():
            time.sleep(0.02)
        self.assertTrue(port_file.exists(), "the test's proxy did not start")
        return int(port_file.read_text().strip())

    def network(self, args, picks, port=None, **env):
        settings = dict(BASE, PI_CODING_AGENT_DIR=str(self.agent))
        if port:
            settings["HTTPS_PROXY"] = "http://127.0.0.1:%d" % port
        settings.update(env)
        return run_extension(self, "network", SCRIPT % json.dumps(picks) + """
            await registered.commands["network"].handler(%s, ctx);
            out(state());
        """ % json.dumps(args), env=settings)

    def saved(self):
        target = self.agent / "network-mode"
        return target.read_text() if target.exists() else None


class MenuTests(Case):
    def test_the_first_menu_marks_this_sessions_mode_and_new_sessions(self):
        got = self.network("", [None], PI_ELM_NETWORK="offline", PI_ELM_NETWORK_DEFAULT="trusted-remote")
        title, options = got["menus"][0]
        self.assertEqual("Network: offline now, new sessions start in trusted-remote", title)
        self.assertEqual(["offline - the ELM gateway only (now)",
                          "trusted-remote - the gateway, packages and research hosts (new sessions)",
                          "yolo - every destination, no OS fence"], options)
        self.assertEqual(1, len(got["menus"]))                     # Escape: no second menu
        self.assertEqual([], got["notes"])
        self.assertIsNone(self.saved())

    def test_an_unfenced_session_is_named_as_one(self):
        for env in ({"ELM_PI_UNFENCED": "fallback", "ELM_PI_NO_JAIL": "1"}, {"ELM_PI_NO_JAIL": "1"}):
            got = self.network("", [None], **env)
            self.assertEqual("Network: trusted-remote (no OS fence) now, new sessions start in trusted-remote",
                             got["menus"][0][0])

    def test_a_tighter_mode_offers_the_session_and_a_looser_one_only_new_sessions(self):
        tighter = self.network("offline", [None], PI_ELM_NETWORK="trusted-remote")
        self.assertEqual(["Change for this session", "Change for this session and new ones"], tighter["menus"][0][1])
        for wanted, current in (("trusted-remote", "offline"), ("yolo", "trusted-remote"), ("yolo", "offline")):
            looser = self.network(wanted, [None], PI_ELM_NETWORK=current)
            self.assertEqual(["Make it the default for new sessions"], looser["menus"][0][1], (wanted, current))
            self.assertIn("A running session cannot be opened up", looser["menus"][0][0])

    def test_default_is_another_name_for_trusted_remote(self):
        got = self.network("default", [None], PI_ELM_NETWORK="offline")
        self.assertTrue(got["menus"][0][0].startswith("trusted-remote: "), got["menus"][0][0])
        self.assertIn("pi --trusted-remote -c", got["menus"][0][0])

    def test_an_unknown_word_changes_nothing(self):
        got = self.network("everything", [0])
        self.assertEqual([['Unknown network mode "everything". Choose offline, trusted-remote (or "default") or yolo.',
                           "error"]], got["notes"])
        self.assertEqual([], got["menus"])

    def test_the_mode_it_is_in_already_is_said_and_nothing_asked(self):
        got = self.network("trusted-remote", [0])
        self.assertEqual([], got["menus"])
        self.assertTrue(got["notes"][0][0].startswith("Already trusted-remote, and new sessions start in it"))


class TightenTests(Case):
    def test_offline_for_this_session_narrows_the_proxy_and_switches_the_web_tools_off(self):
        port = self.proxy(TRUSTED)
        got = self.network("", [0, "Change for this session"], port=port, PI_ELM_NETWORK="trusted-remote",
                           PI_ELM_WEB="1", PI_ELM_REMOTE="1", ELM_PI_PROXY_ALLOW="extra.example")
        self.assertEqual([GATEWAY], health(port)["allow"])           # what the proxy now allows
        self.assertEqual({"PI_ELM_NETWORK": "offline", "PI_ELM_NETWORK_DEFAULT": None, "PI_ELM_WEB": None,
                          "PI_ELM_REMOTE": None, "ELM_PI_PROXY_ALLOW": None}, got["env"])
        self.assertEqual([["bash", "read"]], got["active"])
        self.assertEqual("net: offline", got["status"])
        self.assertIsNone(self.saved())                              # this session only
        text, level = got["notes"][-1]
        self.assertEqual("info", level)
        self.assertTrue(text.startswith("Network: offline - the ELM gateway and nothing else"), text)
        self.assertTrue(text.endswith("New sessions start in trusted-remote."), text)

    def test_for_this_session_and_new_ones_saves_it_too(self):
        port = self.proxy(TRUSTED)
        got = self.network("offline", ["Change for this session and new ones"], port=port)
        self.assertEqual([GATEWAY], health(port)["allow"])
        self.assertEqual("offline\n", self.saved())
        self.assertEqual(0o600, stat.S_IMODE((self.agent / "network-mode").stat().st_mode))
        self.assertEqual("offline", got["env"]["PI_ELM_NETWORK_DEFAULT"])
        self.assertTrue(got["notes"][-1][0].endswith("offline is now the default for new sessions."))
        self.assertEqual([], [p.name for p in self.agent.iterdir() if p.name != "network-mode"])   # no .tmp left

    def test_leaving_yolo_narrows_the_proxy_and_says_the_fence_is_still_off(self):
        port = self.proxy(["*"])
        got = self.network("trusted-remote", ["Change for this session"], port=port, PI_ELM_NETWORK="yolo",
                           ELM_PI_PROXY_ALLOW="extra.example,*")
        self.assertEqual(TRUSTED + ["extra.example"], health(port)["allow"])
        self.assertEqual("extra.example", got["env"]["ELM_PI_PROXY_ALLOW"])      # yolo's "*" is gone
        self.assertIn("The OS fence cannot be added to a running session", got["menus"][0][0])
        self.assertEqual([], got["active"])                                       # web tools stay: not offline
        self.assertEqual("net: trusted-remote", got["status"])

    def test_the_list_a_sub_agent_will_ask_for_is_the_one_the_proxy_now_has(self):
        sys.path.insert(0, str(ROOT / "python"))
        from elmpi import network, proxy
        port = self.proxy(TRUSTED + ["extra.example"])
        self.network("offline", ["Change for this session"], port=port, ELM_PI_PROXY_ALLOW="extra.example")
        child = dict(BASE, PI_ELM_NETWORK="offline")                  # what a run started afterwards inherits
        mode = network.resolve("", child)
        wanted = ",".join(mode.hosts(child, proxy.elm_host(type("E", (), {"get": lambda self, n, d="": child.get(n, d)})())))
        self.assertTrue(proxy.compatible(port, wanted, ""))

    def test_escape_at_the_second_menu_changes_nothing(self):
        port = self.proxy(TRUSTED)
        got = self.network("offline", [None], port=port)
        self.assertEqual(TRUSTED, health(port)["allow"])
        self.assertEqual("trusted-remote", got["env"]["PI_ELM_NETWORK"] or "trusted-remote")
        self.assertEqual(([], [], None), (got["notes"], got["active"], self.saved()))

    def test_without_a_proxy_of_ours_nothing_is_claimed(self):
        for env in ({}, {"HTTPS_PROXY": "http://proxy.example:3128"}):
            got = self.network("offline", ["Change for this session and new ones"], **env)
            self.assertEqual("error", got["notes"][-1][1])
            self.assertIn("Not changed: this session has no proxy of this install's to narrow", got["notes"][-1][0])
            self.assertIn("pi --offline -c", got["notes"][-1][0])
            self.assertIsNone(got["env"]["PI_ELM_NETWORK"])
            self.assertIsNone(self.saved())

    def test_a_proxy_that_refuses_leaves_the_session_as_it_was(self):
        port = self.proxy(["other.example"])                          # the gateway is not on its list
        got = self.network("offline", ["Change for this session"], port=port, PI_ELM_WEB="1")
        self.assertEqual(["other.example"], health(port)["allow"])
        self.assertEqual("error", got["notes"][-1][1])
        self.assertIn("Not changed: the proxy did not take the offline list - elm.example is not on this proxy's list",
                      got["notes"][-1][0])
        self.assertEqual(("1", []), (got["env"]["PI_ELM_WEB"], got["active"]))

    def test_a_port_nothing_answers_on_is_an_error_not_a_change(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        got = self.network("offline", ["Change for this session"], port=port)
        self.assertEqual("error", got["notes"][-1][1])
        self.assertIsNone(got["env"]["PI_ELM_NETWORK"])


class LoosenTests(Case):
    def test_a_looser_mode_is_saved_for_new_sessions_and_this_one_is_left_alone(self):
        port = self.proxy([GATEWAY])
        got = self.network("trusted-remote", [0], port=port, PI_ELM_NETWORK="offline")
        self.assertEqual([GATEWAY], health(port)["allow"])            # not widened
        self.assertEqual("trusted-remote\n", self.saved())
        self.assertEqual("offline", got["env"]["PI_ELM_NETWORK"])
        self.assertEqual([], got["active"])
        self.assertEqual(["Network: trusted-remote is now the default for new sessions. This session stays offline; "
                          "to use trusted-remote now: pi --trusted-remote -c", "info"], got["notes"][-1])

    def test_yolo_can_be_made_the_default_and_is_said_as_a_warning(self):
        got = self.network("yolo", [0])
        self.assertEqual("yolo\n", self.saved())
        text, level = got["notes"][-1]
        self.assertEqual("warning", level)
        self.assertIn("yolo is now the default for new sessions", text)
        self.assertIn("pi --remote -c", text)

    def test_the_mode_it_is_in_can_be_made_the_default(self):
        got = self.network("offline", [0], PI_ELM_NETWORK="offline", PI_ELM_NETWORK_DEFAULT="trusted-remote")
        self.assertEqual(["Make it the default for new sessions"], got["menus"][0][1])
        self.assertEqual("offline\n", self.saved())
        self.assertEqual(["Network: offline is now the default for new sessions.", "info"], got["notes"][-1])

    def test_a_default_that_cannot_be_written_is_an_error(self):
        got = self.network("yolo", [0], PI_CODING_AGENT_DIR=str(self.agent / "missing"))
        self.assertEqual("error", got["notes"][-1][1])
        self.assertTrue(got["notes"][-1][0].startswith("Not saved as the default: "), got["notes"][-1][0])


class SessionTests(Case):
    def start(self, has_ui=True, **env):
        return run_extension(self, "network", SCRIPT % "[]" + """
            ctx.hasUI = %s;
            for (const handler of registered.handlers.session_start) await handler({}, ctx);
            out(state());
        """ % ("true" if has_ui else "false"), env=dict(BASE, **env))

    def test_the_footer_says_the_mode_and_whether_it_is_fenced(self):
        self.assertEqual("net: trusted-remote", self.start()["status"])
        self.assertEqual("net: offline", self.start(PI_ELM_NETWORK="offline")["status"])
        self.assertEqual("net: yolo", self.start(PI_ELM_NETWORK="yolo")["status"])
        self.assertEqual("net: trusted-remote (no OS fence)", self.start(ELM_PI_NO_JAIL="1")["status"])
        self.assertEqual("net: offline (no OS fence)", self.start(PI_ELM_NETWORK="offline", ELM_PI_NO_PROXY="1")["status"])

    def test_a_session_started_without_its_fence_is_told_once_inside_pi(self):
        got = self.start(ELM_PI_UNFENCED="fallback", ELM_PI_NO_JAIL="1")
        self.assertEqual(1, len(got["notes"]))
        self.assertEqual("warning", got["notes"][0][1])
        self.assertTrue(got["notes"][0][0].startswith("⚠ This session is NOT fenced by the OS"), got["notes"][0][0])
        self.assertEqual("net: trusted-remote (no OS fence)", got["status"])

    def test_someone_who_chose_to_run_unfenced_is_not_warned(self):
        for env in ({"ELM_PI_NO_JAIL": "1"}, {"PI_ELM_NETWORK": "yolo"}, {}):
            self.assertEqual([], self.start(**env)["notes"], env)

    def test_a_sub_agent_has_no_screen_to_be_told_on(self):
        got = self.start(has_ui=False, ELM_PI_UNFENCED="fallback")
        self.assertEqual(([], None), (got["notes"], got["status"]))

    def test_a_proxy_that_came_back_with_its_first_list_is_narrowed_again(self):
        # The watchdog's replacement holds the list the session started with. A stand-in proxy
        # here answers health with that list and records what it is then asked.
        got = run_extension(self, "network", SCRIPT % '["Change for this session"]' + """
            const http = await import("node:http");
            const asked = [];
            let allow = %s;
            const server = http.createServer((request, response) => {
              asked.push(request.method + " " + request.url);
              if (request.method === "POST") allow = decodeURIComponent(request.url.split("allow=")[1]).split(",");
              response.end(JSON.stringify({ proxy: "elm-pi-egress", allow, upstream: false }));
            });
            await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
            process.env.HTTPS_PROXY = "http://127.0.0.1:" + server.address().port;
            const run = async () => { for (const handler of registered.handlers.before_agent_start) await handler({}, ctx); };
            await run();                                   // nothing narrowed yet: nothing asked
            const before = asked.length;
            await registered.commands["network"].handler("offline", ctx);
            await run();                                   // still narrow: asked, not told again
            const settled = asked.slice();
            allow = %s;                                    // the replacement proxy
            await run();
            server.close();
            out({ before, settled, after: asked.slice(settled.length), allow });
        """ % (json.dumps(TRUSTED), json.dumps(TRUSTED)), env=dict(BASE, PI_CODING_AGENT_DIR=str(self.agent)))
        self.assertEqual(0, got["before"])
        self.assertEqual(["POST /__elm_pi_egress__/narrow?allow=elm.example", "GET /__elm_pi_egress__/health"],
                         got["settled"])
        self.assertEqual(["GET /__elm_pi_egress__/health", "POST /__elm_pi_egress__/narrow?allow=elm.example"],
                         got["after"])
        self.assertEqual([GATEWAY], got["allow"])


class ProxyNarrowTests(Case):
    """proxy/egress.py's side: a list is only ever narrowed."""

    def test_a_subset_is_kept_and_the_rest_is_refused_from_then_on(self):
        proxy = load_egress().Proxy(TRUSTED, str(Path(self.tmp.name) / "log"))
        self.assertEqual("", proxy.narrow([GATEWAY]))
        self.assertEqual([GATEWAY], proxy.allow)
        self.assertTrue(proxy.allowed(GATEWAY))
        self.assertFalse(proxy.allowed("pypi.example"))
        self.assertIn("NARROWED elm.example", (Path(self.tmp.name) / "log").read_text())

    def test_nothing_can_be_added(self):
        proxy = load_egress().Proxy([GATEWAY], str(Path(self.tmp.name) / "log"))
        for hosts in ([GATEWAY, "pypi.example"], ["*"], ["evil.example"], [], ["", " "], ["bad host"]):
            self.assertNotEqual("", proxy.narrow(hosts), hosts)
            self.assertEqual([GATEWAY], proxy.allow)
        # a subdomain of an allowed host is inside the list, and naming it narrows to it
        self.assertEqual("", proxy.narrow(["api." + GATEWAY]))
        self.assertFalse(proxy.allowed(GATEWAY))

    def test_an_open_proxy_can_be_given_a_list_and_is_open_no_longer(self):
        proxy = load_egress().Proxy(["*"], str(Path(self.tmp.name) / "log"))
        self.assertTrue(proxy.allowed("anything.example"))
        self.assertEqual("", proxy.narrow(["A.Example.", "b.example", "a.example"]))
        self.assertEqual(["a.example", "b.example"], proxy.allow)
        self.assertFalse(proxy.open_mode)
        self.assertFalse(proxy.allowed("anything.example"))
        self.assertNotEqual("", proxy.narrow(["*"]))

    def test_over_the_wire_it_answers_with_the_list_it_now_has(self):
        port = self.proxy(TRUSTED)
        self.assertEqual((403, TRUSTED), (lambda r: (r[0], r[1]["allow"]))(
            post(port, "/__elm_pi_egress__/narrow?allow=elm.example,evil.example")))
        self.assertIn("evil.example is not on this proxy's list", post(port, "/__elm_pi_egress__/narrow?allow=evil.example")[1]["error"])
        status, document = post(port, "/__elm_pi_egress__/narrow?allow=pypi.example,elm.example")
        self.assertEqual((200, ["pypi.example", GATEWAY], "elm-pi-egress"),
                         (status, document["allow"], document["proxy"]))
        self.assertEqual(["pypi.example", GATEWAY], health(port)["allow"])
        self.assertEqual(403, post(port, "/__elm_pi_egress__/narrow?allow=search.example")[0])   # gone for good
        self.assertEqual(403, post(port, "/__elm_pi_egress__/narrow")[0])                        # no hosts named

    def test_a_get_of_the_route_narrows_nothing(self):
        port = self.proxy(TRUSTED)
        with socket.create_connection(("127.0.0.1", port), 3) as connection:
            connection.sendall(b"GET /__elm_pi_egress__/narrow?allow=elm.example HTTP/1.0\r\n\r\n")
            connection.recv(65536)
        self.assertEqual(TRUSTED, health(port)["allow"])


if __name__ == "__main__":
    unittest.main()
