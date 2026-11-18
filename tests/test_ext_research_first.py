"""templates/extensions/research-first.ts: a service is researched before it is built, and an error before a second guess.

The sessions: the SLURM-in-Docker treadmill of 2026-11-17. Without a recipe, sessions built from memory and debugged
for 15 to 34 minutes; one gave up on a cgroup error and one built Ubuntu when asked for Rocky Linux, each a search
away from the answer, and none had searched.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

REQUEST = ("Set up a small test SLURM cluster on this machine using Docker: one head node, a container named v1-head that runs "
           "the controller, and one compute node, a container named v1-c1.")
HELPERS = """
const say = async (text, source = "rpc") => { for (const h of registered.handlers.input) await h({ type: "input", text, source }, ctx); };
const call = async (tool, input = {}) => (await registered.handlers.tool_call[0]({ toolName: tool, toolCallId: "c", input }, ctx)) ?? null;
const result = async (text, isError = true, tool = "bash") =>
  (await registered.handlers.tool_result[0]({ toolName: tool, toolCallId: "c", input: {}, content: [{ type: "text", text }], isError }, ctx)) ?? null;
"""


class ResearchFirstTests(unittest.TestCase):
    def session(self, body, env=None):
        return run_extension(self, "research-first", HELPERS + body, env=env)

    def test_the_first_build_is_refused_until_something_has_been_looked_up(self):
        got = self.session("""
            await say(%r);
            const looked = await call("bash", { command: "docker info" });
            const first = await call("write", { path: "/proj/Dockerfile.slurm", content: "FROM ubuntu:22.04" });
            const again = await call("bash", { command: "docker build -t slurm ." });
            out([looked, first, again]);
        """ % REQUEST)
        self.assertIsNone(got[0])                                        # looking around is not building
        self.assertTrue(got[1]["block"])
        reason = got[1]["reason"]
        self.assertTrue(reason.startswith("Not yet: nothing has been looked up in this run"), reason)
        self.assertIn("`web_search`, then `get_search_content`", reason)
        self.assertIn("how it is run in a container, without systemd", reason)
        self.assertIn("INSTALL-LOG.md", reason)
        self.assertIsNone(got[2])                                        # said once; a session that goes on is not held

    def test_after_a_search_the_plan_and_its_sources_are_asked_for_once(self):
        # res1 r1-r3 (2026-11-17): each searched once, for tutorials, wrote no notes; one of three got a job to run.
        body = """
            await say(%r); await call("web_search", { query: "slurm quick start administrator guide" });
            const first = await call("bash", { command: "docker build -t s ." });
            const second = await call("bash", { command: "docker build -t s ." });
            out([first, second]);
        """ % REQUEST
        first, second = self.session(body)
        self.assertTrue(first["block"])
        self.assertTrue(first["reason"].startswith("Not yet: INSTALL-LOG.md does not hold the plan and its sources."), first["reason"])
        self.assertIn("with the URL each point came from", first["reason"])
        self.assertIn("open the software's own guide with `fetch_content` first", first["reason"])
        self.assertIsNone(second)                                        # asked once

    def test_notes_with_a_plan_and_a_source_let_the_build_through(self):
        plan = "# Plan\n\nslurm-wlm 21.08 from Ubuntu 22.04's own packages. slurmctld on the head node, slurmd on the compute node, munge on both " \
               "with one key, slurm.conf identical everywhere. Start munge, then slurmctld, then slurmd; sinfo shows the node idle.\n" \
               "Source: https://slurm.schedmd.com/quickstart_admin.html\n"
        build = "await say(%r); await call('web_search', { query: 'x' }); out(await call('bash', { command: 'docker build -t s .' }));" % REQUEST
        self.assertIsNone(run_extension(self, "research-first", HELPERS + build, files={"INSTALL-LOG.md": plan}))
        for thin in ("", "todo", "x" * 400, "see https://example.org"):          # empty, a stub, no source, a link and nothing else
            with self.subTest(notes=thin[:20]):
                self.assertTrue(run_extension(self, "research-first", HELPERS + build, files={"INSTALL-LOG.md": thin})["block"])

    def test_it_names_no_software_and_gives_no_answer(self):
        from_ts = (Path(__file__).resolve().parents[1] / "templates/extensions/research-first.ts").read_text()
        told = from_ts[from_ts.index("export const RESEARCH_FIRST"):from_ts.index("/** Whether this call starts the build")].lower()
        for word in ("slurm", "munge", "cgroup", "proctrack", "rocky", "ubuntu"):
            self.assertNotIn(word, told)

    def test_after_a_search_the_build_goes_ahead(self):
        for tool in ("web_search", "get_search_content", "fetch_content"):
            with self.subTest(tool=tool):
                got = self.session("await say(%r); await call(%r, { query: 'slurm quick start administrator guide' });"
                                   "out((await call('write', { path: 'slurm.conf' })).reason.slice(0, 28));" % (REQUEST, tool))
                self.assertEqual("Not yet: INSTALL-LOG.md does", got)             # the search counted: what is asked for next is the plan

    def test_what_counts_as_starting_the_build(self):
        builds = [("bash", {"command": "docker build -f Dockerfile.slurm -t slurm:local ."}), ("bash", {"command": "docker compose up -d"}),
                  ("bash", {"command": "docker run -d --name head --network n img"}), ("bash", {"command": "apt-get install -y slurm-wlm"}),
                  ("bash", {"command": "docker exec head dnf -y install slurm"}), ("write", {"path": "docker-compose.yml"}),
                  ("write", {"path": "etc/slurm.conf"}), ("replace", {"path": "Dockerfile"})]
        not_builds = [("bash", {"command": "docker images"}), ("bash", {"command": "docker run --rm --network=none ubuntu:22.04 cat /etc/os-release"}),
                      ("bash", {"command": "docker network create --internal n"}), ("bash", {"command": "docker pull ubuntu:22.04"}),
                      ("write", {"path": "INSTALL-LOG.md"}), ("read", {"path": "Dockerfile"}), ("bash", {"command": "apt-cache policy slurm-wlm"})]
        for tool, args in builds + not_builds:
            with self.subTest(tool=tool, args=args):
                got = self.session("await say(%r); out(await call(%r, %s));" % (REQUEST, tool, __import__("json").dumps(args)))
                self.assertEqual((tool, args) in builds, got is not None)

    def test_only_a_request_to_set_up_a_service(self):
        for request, on in (("Deploy a three-node Kubernetes cluster in containers for testing.", True),
                            ("install and configure a PostgreSQL database server with replication", True),
                            ("Bring up Redis and RabbitMQ so the two services can talk", True),
                            ("Fix the failing test in test_stats.py", False),
                            ("Write a Dockerfile for my Python script", False),
                            ("Set up the test fixtures for the parser", False),
                            ("pip install numpy and run the script", False)):
            with self.subTest(request=request):
                got = self.session("await say(%r); out(await call('bash', { command: 'docker build -t x .' }));" % request)
                self.assertEqual(on, got is not None)

    def test_the_guard_and_the_skill_route_fire_on_the_same_requests(self):
        root = Path(__file__).resolve().parents[1]
        guard = (root / "templates/extensions/research-first.ts").read_text()
        router = (root / "templates/extensions/skill-router.ts").read_text()
        mine = guard[guard.index("export const SETS_UP =") :].split("\n")[1].strip().rstrip(";")
        line = next(l for l in router.splitlines() if l.strip().startswith('["package-admin", /'))
        theirs = line.strip()[len('["package-admin", '):].rstrip(",").rstrip("]")
        self.assertEqual(theirs, mine)

    def test_the_file_it_asks_for_is_one_the_report_guard_lets_through(self):
        # res2 r4-r6: this guard asked for a file called INSTALL-NOTES and report-guard refused it, "Nobody asked for" it.
        import re
        root = Path(__file__).resolve().parents[1]
        report = (root / "templates/extensions/report-guard.ts").read_text()
        pattern = re.search(r"export const REPORT_NAME =\s*/(.*)/i;", report).group(1)
        name = re.search(r'export const NOTES = "([^"]+)";', (root / "templates/extensions/research-first.ts").read_text()).group(1)
        self.assertIsNone(re.match(pattern, name, re.I), name)
        self.assertIsNotNone(re.match(pattern, "INSTALL-" + "NOTES.md", re.I))            # the name that was refused

    def test_other_suites_are_set_up_the_same_way(self):
        for request in ("Set up an HTCondor pool in Docker with a central manager and one execute node.",
                        "Install Sun Grid Engine in containers: a qmaster and an execution host.",
                        "Deploy an XRootD redirector with one data server behind it.",
                        "Stand up a NorduGrid ARC compute element in front of a batch system.",
                        # suites1-ht (2026-11-17): "Set one up" matched nothing, and the session built an HTCondor pool
                        # from memory with no search at all.
                        "I want a small HTCondor pool to test submit files against. Set one up in Docker: a central manager and one execute node.",
                        "We need a Redis server for the integration tests - bring one up in a container.",
                        "Set up a two-node OpenSearch cluster in Docker for testing."):
            with self.subTest(request=request):
                self.assertIsNotNone(self.session("await say(%r); out(await call('bash', { command: 'docker build -t x .' }));" % request))

    def test_a_second_failure_in_a_row_is_told_to_search_the_message(self):
        got = self.session("""
            await say(%r); await call("web_search", { query: "x" });
            const seen = [];
            seen.push(await result("slurmd: error: Unable to initialize cgroup plugin"));
            seen.push(await result("slurmd: error: Unable to initialize cgroup plugin"));
            seen.push(await result("slurmd: fatal: something else"));          // the streak starts again after a note
            await call("web_search", { query: "slurmd Unable to initialize cgroup plugin" });
            seen.push(await result("still failing"));                          // a search was made: this is the first again
            seen.push(await result("ok", false)); seen.push(await result("fails"));
            out(seen.map((r) => r && r.content.map((p) => p.text)));
        """ % REQUEST)
        self.assertIsNone(got[0])
        self.assertEqual("slurmd: error: Unable to initialize cgroup plugin", got[1][0])     # the output itself is untouched
        self.assertTrue(got[1][1].startswith("[That is the second failure in a row with no search between them."), got[1][1])
        self.assertIn("search for how it is run in a container before concluding that", got[1][1])
        self.assertEqual([None, None, None, None], [got[2], got[3], got[4], got[5]])

    def test_a_failure_read_from_a_log_counts_though_the_command_succeeded(self):
        # suites2-xrd (2026-11-18): `docker logs xrd-redir 2>&1 | tail -30` exits 0 whatever the log says, so an hour of
        # failing daemons never drew the note. What the output says counts too.
        got = self.session("""
            await say(%r); await call("web_search", { query: "x" });
            const seen = [];
            seen.push(await result("------ ofs initialization failed.\\n------ xrootd protocol initialization failed.", false));
            seen.push(await result("Unable to create socket; address family not supported", false));
            seen.push(await result("PARTITION AVAIL NODES STATE\\ndebug* up 1 idle node1", false));     // working output resets the streak
            seen.push(await result("cmsd: fatal: no manager specified", false));
            out(seen.map((r) => (r ? 1 : 0)));
        """ % REQUEST)
        self.assertEqual([0, 1, 0, 0], got)

    SGE = ("Set up a Grid Engine (SGE) cluster in Docker: the qmaster in a container named sge-master, where jobs are submitted, and one "
           "execution host in a container named sge-exec1. Show that a job submitted on sge-master runs on sge-exec1.")

    def settle(self, request, up, twice=False):
        body = ("const m = await import(process.argv[1]);" if False else "") + """
            const mod = await import(new URL(process.argv[1], "file://").href);
            mod.setRunningProbe(() => %s);
            await say(%r);
            const settle = async () => (await registered.handlers.agent_before_settle[0]({}, ctx)) ?? null;
            const first = await settle(); const second = await settle();
            out(%s);
        """ % (__import__("json").dumps(up) if up is not None else "undefined", request, "[first, second]" if twice else "first")
        return self.session(body)

    def test_a_container_the_request_names_and_that_is_not_running_is_said_before_the_report(self):
        # suites1-sge and suites4-sge (2026-11-17/18): one container where two were asked for, and a reply that began
        # "Perfect! Everything is working" and "Excellent! Everything is working".
        got = self.settle(self.SGE, ["sge-master", "someone-elses"])
        self.assertTrue(got["continue"])
        content = got["entries"][0]["content"]
        self.assertTrue(content.startswith("Before you report: the request asks for the containers `sge-master`, `sge-exec1`, and `sge-exec1` is not running"), content)
        self.assertIn("the first line of your reply says what is missing and why", content)

    def test_all_running_or_nothing_named_or_no_engine_says_nothing_and_it_is_said_once(self):
        self.assertIsNone(self.settle(self.SGE, ["sge-exec1", "sge-master"]))
        self.assertIsNone(self.settle("Set up a PostgreSQL database server in a container for the tests.", []))
        self.assertIsNone(self.settle(self.SGE, None))                               # the engine did not answer: nothing is known
        first, second = self.settle(self.SGE, [], twice=True)
        self.assertIn("`sge-master` and `sge-exec1` are not running", first["entries"][0]["content"])
        self.assertIsNone(second)

    def test_the_names_a_request_gives_its_containers(self):
        root = Path(__file__).resolve().parents[1]
        cases = {
            self.SGE: ["sge-master", "sge-exec1"],
            "two containers, os-node1 and os-node2, that form a single cluster": ["os-node1", "os-node2"],
            "a head node (container v2-head) and two compute nodes (containers v2-c1 and v2-c2)": ["v2-head", "v2-c1", "v2-c2"],
            "a redirector in a container named xrd-redir that stores nothing itself": ["xrd-redir"],
            "Run the database in a container for the integration tests and tear it down after": [],
            "Put it in a container. The head-node config goes in slurm.conf": [],
        }
        body = """
            const mod = await import(new URL(process.argv[1], "file://").href);
            out(%s.map((text) => mod.namedContainers(text)));
        """ % __import__("json").dumps(list(cases))
        self.assertEqual([sorted(v) for v in cases.values()], [sorted(v) for v in self.session(body)])     # which, not in what order

    def test_the_caps_and_a_sub_agent(self):
        got = self.session("""
            const seen = [];
            for (let n = 0; n < 3; n++) { await say(%r); seen.push((await call("bash", { command: "docker build ." })) ? 1 : 0); }
            let notes = 0;
            for (let n = 0; n < 30; n++) { if (await result("error")) notes += 1; }
            out([seen, notes]);
        """ % REQUEST)
        self.assertEqual([[1, 1, 1], 8], got)
        child = self.session("await say(%r); out([await call('bash', { command: 'docker build .' }), await result('e'), await result('e')]);" % REQUEST,
                             env={"PI_SUBAGENT_CHILD": "1"})
        self.assertEqual([None, None, None], child)


if __name__ == "__main__":
    unittest.main()
