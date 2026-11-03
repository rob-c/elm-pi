"""The repository agrees with itself: every name one file uses is defined
where it points.

Skills are valid by pi's own rules and name only skills and reference files
that exist; every template renders to text with no placeholder left and every
JSON one parses; required extensions, packages, pins, the workflow middleware
list and the tool checksums line up; the files and links the documents and
install scripts name are there. One test per entry, generated at import, so a
failure names the file, link or package that broke.
"""

import json
import re
import shutil
import subprocess
import sys
import unittest
from difflib import get_close_matches
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
sys.path.insert(0, str(ROOT / "scripts"))

import elm_config  # noqa: E402
from verify_install import frontmatter  # noqa: E402

CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
SKILLS = sorted(p.parent.name for p in TEMPLATES.glob("skills/*/SKILL.md"))
TOKEN = re.compile(r"@[A-Z][A-Z_]*@")


def tracked(*patterns):
    """Tracked files only: a session the agent ran inside templates/ leaves a
    git-ignored .pi/ there that is not part of the repo."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", *patterns],
                             capture_output=True, check=True).stdout
        return sorted(ROOT / p for p in out.decode().split("\0") if p)
    except (OSError, subprocess.CalledProcessError):
        return sorted({p for pattern in patterns for p in ROOT.glob(pattern)
                       if p.is_file() and not {".pi", "__pycache__"} & set(p.parts)})


def render(path: Path) -> str:
    """A template as bootstrap.sh installs it: model ids from the config,
    @AGENT_DIR@ and @INSTALL_DIR@ (sed'ed into the permission config) as paths."""
    text = elm_config.rendered(path.read_text(), CONFIG["models"])
    return text.replace("@AGENT_DIR@", "/install/agent").replace("@INSTALL_DIR@", "/install")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def generate(cls, cases, check, expected_failures=()):
    for name, *args in cases:
        method_name = f"test_{name}"
        assert not hasattr(cls, method_name), method_name
        def method(self, _args=tuple(args)):
            check(self, *_args)
        method.__name__ = method_name
        if name in expected_failures:
            method = unittest.expectedFailure(method)
        setattr(cls, method_name, method)


# --- skills and the prompts that point at them ----------------------------------

class SkillTests(unittest.TestCase):
    """Each skill as pi validates it (core/skills.js, the Agent Skills spec)."""


def _skill_is_valid(self, name):
    path = TEMPLATES / "skills" / name / "SKILL.md"
    text = render(path)
    fields = frontmatter(text)
    self.assertIsNotNone(fields, "frontmatter does not parse")
    self.assertEqual(name, fields.get("name"))
    # validateName(): 64 characters, a-z 0-9 and single inner hyphens
    self.assertLessEqual(len(name), 64)
    self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
    description = fields.get("description", "")
    self.assertTrue(description.strip())
    self.assertLessEqual(len(description), 1024)
    # every frontmatter line is YAML pi can read: an unquoted ": " in any key,
    # not only the two verify_install.py looks at, makes pi drop the skill
    block = text.split("---\n", 2)[1]
    for line in block.splitlines():
        key, _, value = line.partition(": ")
        self.assertRegex(key, r"^[a-z][a-z-]*$", line)
        value = value.strip()
        if value.startswith('"'):
            json.loads(value)
        else:
            self.assertNotIn(": ", value, line)
    # the body is what pi loads on demand; a skill with none says nothing
    self.assertGreater(len(text.split("---\n", 2)[2].strip()), 200)


generate(SkillTests, [(f"skill_{slug(s)}_is_valid", s) for s in SKILLS], _skill_is_valid)


PROMPTS = sorted([TEMPLATES / "AGENTS.md", TEMPLATES / "APPEND_SYSTEM.md",
                  *TEMPLATES.glob("agents/*.md"), *TEMPLATES.glob("reference/*.md"),
                  *TEMPLATES.glob("skills/*/SKILL.md")])
SKILL_REF = re.compile(r"`([a-z0-9-]+)`(?:,? (?:and|or) `([a-z0-9-]+)`)? skills?\b")
REFERENCE_REF = re.compile(r"@AGENT_DIR@/reference/([A-Za-z0-9_.-]+\.md)")
HYPHENATED = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")


class PromptReferenceTests(unittest.TestCase):
    """What the model reads names only skills and reference files that exist."""


def _references_resolve(self, path):
    text = path.read_text()
    for match in SKILL_REF.finditer(text):
        for name in filter(None, match.groups()):
            self.assertIn(name, SKILLS, f"`{name}` skill")
    for name in REFERENCE_REF.findall(text):
        self.assertTrue((TEMPLATES / "reference" / name).is_file(), f"@AGENT_DIR@/reference/{name}")
    # a backticked name one or two letters off a skill's is a renamed or mistyped one
    for token in set(HYPHENATED.findall(text)) - set(SKILLS):
        self.assertEqual([], get_close_matches(token, SKILLS, n=1, cutoff=0.9), f"`{token}`")
    # rendered as bootstrap.sh does it, nothing of the form @NAME@ is left
    self.assertEqual([], TOKEN.findall(render(path)))


generate(PromptReferenceTests,
         [(f"references_in_{slug(str(p.relative_to(TEMPLATES)))}_resolve", p) for p in PROMPTS],
         _references_resolve)


class ReferenceFileTests(unittest.TestCase):
    """agent/reference/ is read only when AGENTS.md names the file."""


generate(ReferenceFileTests,
         [(f"reference_{slug(p.stem)}_is_named_in_agents_md", p.name) for p in sorted(TEMPLATES.glob("reference/*.md"))],
         lambda self, name: self.assertTrue(f"@AGENT_DIR@/reference/{name}" in (TEMPLATES / "AGENTS.md").read_text(),
                                            f"nothing points the model at reference/{name}"))


# --- templates: they render and parse ------------------------------------------

JSON_FILES = [p for p in tracked("templates/*.json", "templates/**/*.json", "config/*.json")]


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValueError(f"duplicate keys {duplicates}")   # json.loads would keep the last silently
    return dict(pairs)


class JsonTemplateTests(unittest.TestCase):
    pass


def _json_parses(self, path):
    text = render(path)
    self.assertEqual([], TOKEN.findall(text))
    value = json.loads(text, object_pairs_hook=_no_duplicates)
    self.assertIsInstance(value, dict)


generate(JsonTemplateTests,
         [(f"{slug(str(p.relative_to(ROOT)))}_renders_and_parses", p) for p in JSON_FILES], _json_parses)


# --- extensions, packages and pins ---------------------------------------------

EXTENSIONS = sorted(set(CONFIG["requiredExtensions"]) | {p.name for p in TEMPLATES.glob("extensions/*.ts")})


class ExtensionTests(unittest.TestCase):
    """bootstrap.sh installs exactly requiredExtensions from templates/extensions."""


def _extension(self, name):
    path = TEMPLATES / "extensions" / name
    self.assertIn(name, CONFIG["requiredExtensions"], "in templates/extensions but never installed")
    self.assertTrue(path.is_file(), "required but not in templates/extensions")
    text = render(path)
    self.assertRegex(text, r"(?m)^export default ", "pi loads an extension's default export")
    self.assertEqual([], TOKEN.findall(text))


generate(ExtensionTests, [(f"extension_{slug(n)}", n) for n in EXTENSIONS], _extension)


PACKAGES = json.loads((TEMPLATES / "packages.json").read_text())["dependencies"]
VERSIONS = json.loads((ROOT / "config/versions.json").read_text())
SETTINGS = json.loads((TEMPLATES / "settings.json").read_text())
SETTINGS_SOURCES = [s["source"] if isinstance(s, dict) else s for s in SETTINGS["packages"]]
# Installed with the others but loaded by the launcher with -e for a --remote
# session only, never from settings.json (LOCKDOWN.md, "Computer use").
REMOTE_ONLY = {"@injaneity/pi-computer-use"}


class PackageTests(unittest.TestCase):
    pass


def _package(self, name):
    # pin_versions.py: the manifest asks for latest, every install takes the pin
    self.assertEqual("latest", PACKAGES[name])
    self.assertRegex(VERSIONS["packages"].get(name, ""), r"^\d+\.\d+\.\d+$", "no exact tested version")
    if name in REMOTE_ONLY:
        self.assertNotIn(f"npm:{name}", SETTINGS_SOURCES, "would load in every session")
        self.assertIn(f"/node_modules/{name}/", (ROOT / "pi").read_text(), "the launcher no longer loads it")
    else:
        self.assertEqual(1, SETTINGS_SOURCES.count(f"npm:{name}"), "installed but pi never loads it")


generate(PackageTests, [(f"package_{slug(n)}", n) for n in sorted(set(PACKAGES) | set(VERSIONS["packages"]))],
         _package)


class PackageSetTests(unittest.TestCase):
    def test_every_package_pi_loads_is_installed(self):
        self.assertEqual([], [s for s in SETTINGS_SOURCES if s[4:] not in PACKAGES])
        self.assertTrue(all(s.startswith("npm:") for s in SETTINGS_SOURCES), SETTINGS_SOURCES)

    def test_core_pins_are_exact_versions_of_the_core_manifest(self):
        core = json.loads((ROOT / "package.json").read_text())["dependencies"]
        for name, version in VERSIONS["core"].items():
            self.assertEqual("latest", core[name], name)
            self.assertRegex(version, r"^\d+\.\d+\.\d+$", name)

    def test_every_subagent_model_is_on_an_allowed_provider(self):
        overrides = SETTINGS["subagents"]["agentOverrides"]
        models = {name: o["model"] for name, o in overrides.items() if "model" in o}
        self.assertGreater(len(models), 3)
        for name, model in models.items():
            self.assertIn(model.split("/", 1)[0], CONFIG["allowedProviders"], name)
        allow = {a.split("/")[0] for a in SETTINGS["subagents"]["modelScope"]["allow"]} - {"inherit"}
        self.assertEqual(set(CONFIG["allowedProviders"]), allow)


MIDDLEWARE = json.loads((TEMPLATES / "workflows/settings.json").read_text())["providerMiddlewareExtensions"]


class WorkflowMiddlewareTests(unittest.TestCase):
    """Each workflow middleware is a local extension or an installed package."""


def _middleware(self, entry):
    if entry.startswith("@") or entry in PACKAGES:
        self.assertIn(entry, PACKAGES)
    else:
        self.assertIn(f"{entry}.ts", CONFIG["requiredExtensions"])


generate(WorkflowMiddlewareTests, [(f"middleware_{slug(e)}", e) for e in MIDDLEWARE], _middleware)


# --- templates/tools.sha256 against what bootstrap.sh downloads ------------------

BOOTSTRAP = (ROOT / "bootstrap.sh").read_text()
TOOLSET = re.search(r'TOOLSET="\$\{ELM_PI_TOOLS:-([^}]+)\}"', BOOTSTRAP).group(1).split(",")
SHA_LINE = re.compile(r"^([0-9a-f]{64})  ([a-z-]+)/(\d+(?:\.\d+)+)/(\S+)$")
SHA_LINES = [line for line in (TEMPLATES / "tools.sha256").read_text().splitlines()
             if line.strip() and not line.startswith("#")]
PLATFORMS = ("Darwin x86_64", "Darwin arm64", "Linux x86_64", "Linux aarch64")
# bootstrap.sh: "resvg publishes no build for 64-bit ARM Linux before 0.49"
NO_RELEASE = re.compile(r"^resvg/0\.4[0-8](\.\d+)?/resvg-linux-aarch64\.")


def requested_assets():
    """Every tool/version/asset bootstrap.sh would fetch, on each platform: its
    own platform logic and install_tool lines, with install_tool stubbed."""
    start = BOOTSTRAP.index('  case "$(uname -s)" in', BOOTSTRAP.index('  TOOLSET="'))
    end = BOOTSTRAP.index("\n", BOOTSTRAP.index('  RUFF_VERSION="${RUFF_VERSION:-'))
    platform = BOOTSTRAP[start:end].replace("$(uname -s)", "$FAKE_OS").replace("$(uname -m)", "$FAKE_ARCH")
    calls = BOOTSTRAP[BOOTSTRAP.index("  GH=https://github.com"):BOOTSTRAP.index('  echo "    agent/bin is')]
    script = ('die() { echo "DIE $*" >&2; exit 9; }\n'
              "install_tool() { printf '%s/%s/%s\\n' \"$1\" \"$2\" \"$3\"; }\n"
              'for plat in "$@"; do (\n  set -- $plat; FAKE_OS=$1; FAKE_ARCH=$2\n'
              f"{platform}\n{calls}) || exit 1\ndone\n")
    out = subprocess.run(["bash", "-c", script, "assets", *PLATFORMS], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin"})
    if out.returncode != 0:
        raise AssertionError(f"bootstrap.sh's tool block did not run: {out.stderr}")
    return set(out.stdout.split())


class ToolChecksumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requested = requested_assets()

    def test_every_line_is_a_checksum_and_a_known_tool(self):
        keys = []
        for line in SHA_LINES:
            match = SHA_LINE.match(line)
            self.assertIsNotNone(match, line)
            self.assertIn(match.group(2), TOOLSET, line)
            keys.append("/".join(match.groups()[1:]))
        self.assertEqual(len(keys), len(set(keys)), "a key listed twice: bootstrap takes the first")

    def test_bootstrap_asks_for_every_tool_on_every_platform(self):
        tools = {key.split("/")[0] for key in self.requested}
        self.assertEqual(set(TOOLSET), tools)
        self.assertEqual(len(PLATFORMS) * len(TOOLSET), len(self.requested))


def _tool(self, tool):
    wanted = {k for k in self.requested if k.startswith(f"{tool}/") and not NO_RELEASE.match(k)}
    listed = {"/".join(SHA_LINE.match(l).groups()[1:]) for l in SHA_LINES
              if SHA_LINE.match(l) and SHA_LINE.match(l).group(2) == tool}
    self.assertGreaterEqual(len(wanted), 3)
    # a pin bump without its checksums installs unverified; a line nothing asks for is stale
    self.assertEqual(sorted(wanted), sorted(listed))


generate(ToolChecksumTests, [(f"checksums_match_the_pins_{slug(t)}", t) for t in TOOLSET], _tool)


# --- documents: links and named files exist -------------------------------------

DOCS = ["README.md", "INSTALL.md", "LOCKDOWN.md", "CONTRIBUTING.md", "docs/index.html"]
BLOB = "https://github.com/rob-c/elm-pi/blob/main/"


def headings(path: Path) -> set[str]:
    """GitHub's anchors for a Markdown file's headings (outside code fences)."""
    anchors, fenced = set(), False
    for line in path.read_text().splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,6} ", line):
            title = line.lstrip("#").strip().lower()
            anchors.add(re.sub(r"[^\w\- ]", "", title).replace(" ", "-"))
    return anchors


def links():
    found = []
    for doc in DOCS:
        text = (ROOT / doc).read_text()
        targets = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'href="([^"]+)"', text)
        for target in dict.fromkeys(targets):
            if target.startswith(BLOB):
                target = target[len(BLOB):]
            elif re.match(r"[a-z]+:", target):
                continue
            found.append((doc, target))
    return found


class DocumentLinkTests(unittest.TestCase):
    pass


def _link(self, doc, target):
    rel, _, anchor = target.partition("#")
    path = (ROOT / doc).parent / rel if rel else ROOT / doc
    if (ROOT / doc).suffix == ".html" and rel:
        path = ROOT / rel          # the site links to the repo through its blob URLs
    self.assertTrue(path.is_file(), f"{doc} -> {target}")
    if anchor:
        self.assertIn(anchor, headings(path), f"{doc} -> {target}")


generate(DocumentLinkTests, [(f"link_{slug(d)}_to_{slug(t)}", d, t) for d, t in links()], _link)


REPO_PATH = re.compile(r"(?<![\w./$~-])((?:templates|scripts|config|lib|proxy|shim|docs|tests|\.github)/[\w./-]*\w)")
# CONTRIBUTING.md names these as what git history holds, not as files.
HISTORICAL = {"scripts/repair-transitives.sh", "scripts/audit.sh"}


class DocumentPathTests(unittest.TestCase):
    """Repo paths a document names, in prose or in backticks, exist."""


def _paths(self, doc):
    text = (ROOT / doc).read_text()
    missing = sorted({p for p in REPO_PATH.findall(text) if not (ROOT / p).exists()} - HISTORICAL)
    self.assertEqual([], missing)


generate(DocumentPathTests, [(f"paths_named_in_{slug(d)}_exist", d) for d in DOCS], _paths)


class ReadmeLayoutTests(unittest.TestCase):
    def layout(self):
        text = (ROOT / "README.md").read_text()
        block = text.split("## Layout", 1)[1].split("```", 2)[1]
        return [line.split("  ", 1) for line in block.strip().splitlines()]

    def test_every_source_entry_exists(self):
        for names, description in self.layout():
            if description.strip().startswith("generated"):
                continue
            for name in names.split():
                self.assertTrue((ROOT / name).exists(), name)

    def test_agent_bin_lists_the_tools_bootstrap_installs(self):
        line = next(d for n, d in self.layout() if n.strip() == "agent/bin/")
        listed = line.split(":", 1)[1].split(",")[0].split()
        self.assertEqual(TOOLSET, listed)


# --- install scripts: the files and values they name ------------------------------

INSTALL_SCRIPTS = ["bootstrap.sh", "install.sh", "configure.sh", "pi", "scripts/check.sh",
                   ".github/workflows/ci.yml", "lib/sandbox.sh"]
NAMED = re.compile(r"(?<![\w./$-])((?:scripts|lib|proxy|shim|templates)/[A-Za-z0-9_.-]*[A-Za-z0-9_](?:/[A-Za-z0-9_.-]*[A-Za-z0-9_])*)")


class InstallScriptPathTests(unittest.TestCase):
    """Every scripts/, lib/, proxy/, shim/ and templates/ path an install
    script names is in the repo: a rename that misses one fails at install."""


def _named_paths(self, rel):
    text = (ROOT / rel).read_text()
    missing = sorted({p for p in NAMED.findall(text) if not (ROOT / p).exists()})
    self.assertEqual([], missing)


generate(InstallScriptPathTests, [(f"paths_named_in_{slug(r)}_exist", r) for r in INSTALL_SCRIPTS], _named_paths)


class ConfigValueTests(unittest.TestCase):
    """Each `elm_config.py value KEY` an install script asks for is answered
    from the real config/elm-pi.json (an unknown key exits non-zero)."""

    def test_every_key_asked_for_is_answered(self):
        import contextlib, io, tempfile
        from unittest import mock
        keys = set()
        for rel in INSTALL_SCRIPTS:
            keys |= set(re.findall(r"--root \"\$HERE\" value (\w+)", (ROOT / rel).read_text()))
        self.assertEqual({"nodeVersion", "pythonVersion", "pythonPackages", "qwen"}, keys)
        expected = {"nodeVersion": CONFIG["nodeVersion"], "pythonVersion": CONFIG["python"]["version"],
                    "pythonPackages": " ".join(CONFIG["python"]["packages"]), "qwen": CONFIG["models"]["qwen"]}
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config").mkdir()
            shutil.copy2(ROOT / "config/elm-pi.json", Path(directory) / "config/elm-pi.json")
            for key in sorted(keys):
                out = io.StringIO()
                with mock.patch.object(sys, "argv", ["elm_config.py", "--root", directory, "value", key]), \
                        contextlib.redirect_stdout(out):
                    self.assertEqual(0, elm_config.main(), key)
                self.assertEqual(expected[key] + "\n", out.getvalue(), key)


class ConfigTests(unittest.TestCase):
    """config/elm-pi.json and the scripts that depend on it."""

    def test_no_list_names_an_entry_twice(self):
        lists = {"builtinProviders": CONFIG["builtinProviders"], "providerCredentials": CONFIG["providerCredentials"],
                 "webTools": CONFIG["webTools"], "requiredExtensions": CONFIG["requiredExtensions"],
                 "python.packages": CONFIG["python"]["packages"], "proxyAllow": CONFIG["proxyAllow"]["hosts"],
                 **{f"excludedTools.{k}": v for k, v in CONFIG["excludedTools"].items() if k != "_comment"},
                 **{f"untrustedFolders.{k}": v for k, v in CONFIG["untrustedFolders"].items() if k != "_comment"}}
        for name, values in lists.items():
            self.assertEqual(sorted(set(values)), sorted(values), name)

    def test_tool_exclusion_lists_do_not_overlap(self):
        web, always, workflows = (set(CONFIG["webTools"]), set(CONFIG["excludedTools"]["always"]),
                                  set(CONFIG["excludedTools"]["workflows"]))
        self.assertEqual(set(), (web & always) | (web & workflows) | (always & workflows))

    def test_a_folder_is_exact_or_tree_not_both(self):
        folders = CONFIG["untrustedFolders"]
        self.assertEqual(set(), set(folders["exact"]) & set(folders["tree"]))

    def test_conda_search_asks_a_host_the_proxy_allows(self):
        hosts = re.findall(r"https://([a-z0-9.-]+)/", (ROOT / "scripts/conda-search").read_text())
        self.assertEqual(["prefix.dev"], hosts)
        self.assertIn("prefix.dev", CONFIG["proxyAllow"]["hosts"])

    def test_the_agents_python_can_build_the_pypi_index(self):
        # pypi_index.py build reads Parquet with pyarrow, on agent/python
        self.assertIn("import pyarrow.parquet", (ROOT / "scripts/pypi_index.py").read_text())
        self.assertIn("pyarrow", CONFIG["python"]["packages"])


# --- the scripts themselves parse, and check.sh checks them all --------------------

SCRIPT_FILES = tracked("scripts/*")


def kind(path: Path) -> str:
    first = path.read_text().split("\n", 1)[0]
    if path.suffix == ".py" or "python" in first:
        return "python"
    if path.suffix == ".sh" or "bash" in first:
        return "bash"
    return "other"


class ScriptSyntaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shells = [p for p in SCRIPT_FILES if kind(p) == "bash"]
        # one bash for all of them, reporting each status
        script = 'for f in "$@"; do bash -n "$f" 2>/dev/null; echo "$?"; done'
        out = subprocess.run(["bash", "-c", script, "syntax", *map(str, shells)], capture_output=True, text=True)
        cls.bash_status = dict(zip(shells, out.stdout.split()))

    # check.sh finds the scripts to syntax-check by extension or shebang: a
    # hand-kept list missed scripts/brew, conda-search, pypi-search,
    # workflow-check and pypi_index.py. Its discovery loop, run here, must find
    # every tracked script, and both lists must reach the checks.
    def test_check_sh_covers_every_script(self):
        check = (ROOT / "scripts/check.sh").read_text()
        loop = re.search(r"^SHELL_SCRIPTS=.*?^done$", check, re.S | re.M).group(0)
        out = subprocess.run(["bash", "-c", loop + '\necho "$SHELL_SCRIPTS"; echo "$PYTHON_SCRIPTS"'],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
        found = {"bash": out[0].split(), "python": out[1].split()}
        uncovered = [p.name for p in SCRIPT_FILES
                     if kind(p) in found and f"scripts/{p.name}" not in found[kind(p)]]
        self.assertEqual([], uncovered)
        self.assertRegex(check, r"\nbash -n .*\$SHELL_SCRIPTS\n")
        self.assertRegex(check, r"ast\.parse.*\n.*\$PYTHON_SCRIPTS\n")


# The Python ones are imported, and so compiled, by tests/test_scripts.py.
generate(ScriptSyntaxTests, [(f"shell_script_{slug(p.name)}_parses", p) for p in SCRIPT_FILES if kind(p) == "bash"],
         lambda self, path: self.assertEqual("0", self.bash_status[path], f"bash -n {path.name}"))


if __name__ == "__main__":
    unittest.main()
