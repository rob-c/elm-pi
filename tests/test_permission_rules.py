"""Every rule in the permission gate's policy, decided by the gate's own code.

templates/extensions/pi-permission-system/config.json is filled in the way
bootstrap.sh fills it (@INSTALL_DIR@, @AGENT_DIR@) into a temporary install,
then the installed @gotgenes/pi-permission-system package - loaded with jiti,
as pi loads it - decides each case:

- a bash command goes through tree-sitter's parse and resolveBashCommandCheck,
  the function the tool-call gate uses, so chains, substitutions, wrappers
  (env, sudo, bash -c) and last-match-wins precedence are the package's own;
  then through templates/extensions/command-guard.ts, which pi runs beside the
  gate and which denies a spelling of a denied command the gate's rules miss
  (`'ssh' host`, `sudo ssh host`). A call either one blocks is refused, so a
  case's decision is the gate's unless the guard denies what the gate did not;
- a command's path tokens go through the bash path gate (cat .env);
- a file tool's path is resolved on the path and external_directory surfaces,
  and the Pi infrastructure read list is checked with the package's matcher;
- the config itself loads with no issues.

Each case asserts the exact decision (allow / ask / deny) and the rule that
made it, and a deny carries the rule's reason to the model. HOME is a
temporary folder, so ~ in the rules never names the real home. One node
process answers every case in the file. Cases marked BUG are known gaps,
kept as expected failures. The tests skip on a checkout that has not been
bootstrapped.
"""

import functools
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/extensions/pi-permission-system/config.json"
GUARD = ROOT / "templates/extensions/command-guard.ts"
NPM = ROOT / "agent/npm/node_modules"
PACKAGE = NPM / "@gotgenes/pi-permission-system"
JITI = NPM / "jiti/lib/jiti.mjs"
RULES = json.loads(TEMPLATE.read_text())
BASH_RULES = RULES["permission"]["bash"]


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


# Loads the package's own modules and answers every case as one JSON object.
RUNNER = r"""
const [jitiPath, pkg, agentDir, cwd, casesPath, guardPath] = process.argv.slice(1);
const { readFileSync } = await import("node:fs");
const { createJiti } = await import(jitiPath);
const jiti = createJiti(import.meta.url, { fsCache: false });
const load = (p) => jiti.import(`${pkg}/src/${p}`);
const { PermissionManager } = await load("policy/permission-manager.ts");
const { PermissionResolver } = await load("policy/permission-resolver.ts");
const { BashProgram } = await load("access-intent/bash/program.ts");
const { resolveBashCommandCheck } = await load("handlers/gates/bash-command.ts");
const { describeBashPathGate } = await load("handlers/gates/bash-path.ts");
const { PathNormalizer } = await load("path/path-normalizer.ts");
const { posixPathFlavor } = await load("path/path-flavor.ts");
const { capabilitySurfaceForTool } = await load("access-intent/path-surfaces.ts");
const { isPiInfrastructureRead } = await load("path/pi-infrastructure-read.ts");
const { loadUnifiedConfig, detectPermissiveBashFallback } = await load("config/config-loader.ts");
const { getGlobalConfigPath } = await load("config/config-paths.ts");

const guard = await jiti.import(guardPath);

const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const config = JSON.parse(readFileSync(getGlobalConfigPath(agentDir), "utf8"));
const manager = new PermissionManager({ agentDir });
manager.configureForCwd(cwd);
const resolver = new PermissionResolver(manager, { getRuleset: () => [] });
const normalizer = new PathNormalizer(posixPathFlavor, cwd);
const pick = (r) => ({ state: r.state, pattern: r.matchedPattern ?? null, reason: r.reason ?? null });
const out = { bash: {}, bashPath: {}, path: {}, external: {}, infra: {}, tools: {}, guard: {} };

for (const command of cases.bash) {
  const program = await BashProgram.parse(command, normalizer);
  const gate = pick(resolveBashCommandCheck(command, program.commands(), undefined, resolver));
  const denial = gate.state === "deny" ? undefined : guard.deniedSpelling(command, config.permission.bash);
  out.bash[command] = denial ? { state: "deny", pattern: denial.pattern, reason: denial.reason ?? null } : gate;
}
for (const command of cases.bashPath) {
  const program = await BashProgram.parse(command, normalizer);
  const tcc = { toolName: "bash", toolCallId: "t", agentName: undefined, input: { command } };
  const gate = describeBashPathGate(tcc, program, resolver, normalizer);
  out.bashPath[command] = gate?.preCheck ? pick(gate.preCheck) : { state: "none", pattern: null, reason: null };
}
const onSurface = (family, tool, path) => pick(resolver.resolve({
  kind: "access-path",
  surface: capabilitySurfaceForTool(family, tool),
  path: normalizer.forToolPath(tool, path),
}));
for (const [tool, path] of cases.path) out.path[`${tool} ${path}`] = onSurface("path", tool, path);
for (const [tool, path] of cases.external) out.external[`${tool} ${path}`] = onSurface("external_directory", tool, path);

for (const [tool, path] of cases.infra) {
  const resolved = normalizer.forToolPath(tool, path).matchValues()[0];
  out.infra[`${tool} ${path}`] = isPiInfrastructureRead(
    tool, resolved, config.piInfrastructureReadPaths, cwd, posixPathFlavor);
}
for (const tool of cases.tools) {
  out.tools[tool] = { state: manager.getToolPermission(tool), fullyDenied: manager.isToolFullyDenied(tool) };
}
out.loadIssues = loadUnifiedConfig(getGlobalConfigPath(agentDir)).issues;
out.permissiveBash = detectPermissiveBashFallback(config.permission) ?? null;
out.policyIssues = manager.getPolicyIssues();

// The guard as pi loads it: its tool_call handler, reading the rules installed
// under PI_CODING_AGENT_DIR.
const handlers = {};
guard.default({ on: (name, handler) => { handlers[name] = handler; } });
const call = async (toolName, input) => (await handlers.tool_call({ toolName, input }, { hasUI: false })) ?? null;
out.guard.denied = await call("bash", { command: "cd x && 'ssh' host" });
out.guard.allowed = await call("bash", { command: "ls -la" });
out.guard.otherTool = await call("read", { command: "'ssh' host" });
out.guard.noCommand = await call("bash", {});
process.env.PI_CODING_AGENT_DIR = cwd;
out.guard.noConfig = await call("bash", { command: "'ssh' host" });
out.guard.plainDeny = guard.deniedSpelling("\\x y", { "*": "allow", "x *": "deny" }) ?? null;
out.guard.envRemote = guard.remoteEngineInEnvironment("sudo docker ps", { DOCKER_HOST: "ssh://build" }) ?? null;
out.guard.envSocket = guard.remoteEngineInEnvironment("docker ps", { DOCKER_HOST: "unix:///var/run/docker.sock" }) ?? null;
out.guard.envDefault = guard.remoteEngineInEnvironment("docker ps", { DOCKER_CONTEXT: "default" }) ?? null;
out.guard.envNotAnEngine = guard.remoteEngineInEnvironment("ls", { CONTAINER_HOST: "ssh://h" }) ?? null;
console.log(JSON.stringify(out));
"""


def deny(pattern):
    return ("deny", pattern)


def ask(pattern):
    return ("ask", pattern)


def allow(pattern="*"):
    return ("allow", pattern)


# (command, (decision, the rule that decides it), note). A note starting
# "BUG:" marks a known gap: the case states the right answer and is expected
# to fail until the policy (or the package) catches it.
BASH = [
    # --- the catch-all: ordinary work runs without asking
    ("ls", allow(), ""),
    ("python3 analysis/fit.py --plot", allow(), ""),
    ("echo done > out.txt", allow(), ""),
    ("curl -sS https://pypi.org/simple/numpy/", allow(), "goes through the egress proxy"),
    ("pip install requests", allow(), "not pi"),

    # --- sudo asks
    ("sudo ls /var/root", ask("sudo *"), ""),
    ("sudo", ask("sudo *"), "a trailing ' *' also matches the bare word"),
    ("cd build && sudo make install", ask("sudo *"), "found inside a chain"),
    ("sudo ssh host", deny("ssh *"), "command-guard: sudo's own ask would win at the gate"),
    ("sudo apt-get install -y curl", deny("apt-get install*"), "command-guard: past sudo"),
    ("sudo -u root -- ssh host", deny("ssh *"), "command-guard: past sudo's options"),

    # --- git push and remote add ask; everything else in git runs
    ("git push", ask("git push *"), ""),
    ("git push --force-with-lease origin feature", ask("git push *"), ""),
    ("git status && git push", ask("git push *"), "the chain's second command"),
    ("git pushall", allow(), "another command, not git push"),
    ("git stash push -m wip", allow(), "stash push is local"),
    ("git commit -m 'push the fix'", allow(), "push inside a message"),
    ("git pull --rebase", allow(), ""),
    ("git remote add upstream https://github.com/x/y", ask("git remote add*"), ""),
    ("git remote -v", allow(), ""),
    ("git -C sub push", ask("git -* push *"), "a global option before the subcommand"),
    ("git --no-pager -C sub remote add x https://h/y", ask("git -* remote add*"), ""),

    # --- pi's own setup and update ask; gh asks
    ("pi setup --python", ask("pi setup*"), ""),
    ("pi update", ask("pi update*"), ""),
    ("pi --version", allow(), ""),
    ("gh pr create --fill", ask("gh *"), ""),
    ("gh", ask("gh *"), ""),
    ("ghc Main.hs", allow(), "the Haskell compiler is not gh"),

    # --- SSH and what rides on it are denied
    ("ssh -i key user@host 'ls'", deny("ssh *"), ""),
    ("ssh", deny("ssh *"), ""),
    ("ssh  -v  host", deny("ssh *"), "extra spaces"),
    ("  ssh host", deny("ssh *"), "leading spaces"),
    ("cd repo && ssh host uptime", deny("ssh *"), ""),
    ("ls; ssh host", deny("ssh *"), ""),
    ("tar c . | ssh host 'tar x'", deny("ssh *"), "the far end of a pipe"),
    ("(ssh host)", deny("ssh *"), "a subshell"),
    ("echo $(ssh host hostname)", deny("ssh *"), "a command substitution"),
    ("echo `ssh host hostname`", deny("ssh *"), "a backtick substitution"),
    ("ls\nssh host", deny("ssh *"), "the second line"),
    ("FOO=1 ssh host", deny("ssh *"), "an assignment prefix"),
    ("time ssh host", deny("ssh *"), "a wrapper that only times it"),
    ("timeout 10 ssh host", deny("ssh *"), "a wrapper that only limits it"),
    ("ssh-keygen -t ed25519 -f k", allow(), "local key work"),
    ("sshd-keygen", allow(), "a lookalike name"),
    ("man ssh", allow(), "ssh as an argument"),
    ("echo 'ssh host'", allow(), "quoted text"),
    ("git commit -m \"ssh host\"", allow(), ""),
    ("# ssh host", allow(), "a comment runs nothing"),
    ("cat <<EOF\nssh host\nEOF", allow(), "a heredoc body is data"),
    ("bash -c 'ssh host'", deny("ssh *"), "command-guard: the gate does not parse inside, the guard does"),
    ("bash -c 'ls'", ask("<opaque-bash-wrapper>"), "the gate's ask stands when the payload is allowed"),
    ("eval ls", ask("<opaque-bash-wrapper>"), ""),
    ("eval 'ssh host'", deny("ssh *"), "command-guard"),
    ("env ls", allow(), "env with an allowed command"),
    ("env ssh host", deny("ssh *"), "command-guard: the gate floors env to an ask"),
    ("env -i PATH=/usr/bin ssh host", deny("ssh *"), "command-guard: past env's options and assignments"),
    ("echo host | xargs ssh", deny("ssh *"), "command-guard: the gate floors xargs to an ask"),
    ("find . -name '*.py' | xargs grep ssh", allow(), "ssh as an argument of what xargs runs"),
    ("nohup ssh host &", deny("ssh *"), "command-guard"),
    ("/usr/bin/ssh host", deny("ssh *"), "command-guard: the command name's last path segment"),
    ("command ssh host", deny("ssh *"), "command-guard: the command builtin runs ssh"),
    ("command -v ssh", allow(), "only says where ssh is"),
    ("exec ssh host", deny("ssh *"), "command-guard: exec runs ssh"),
    ("'ssh' host", deny("ssh *"), "command-guard: a quoted command name is still ssh"),
    ("\\ssh host", deny("ssh *"), "command-guard: a backslashed command name is still ssh"),
    ("s\"s\"h host", deny("ssh *"), "command-guard: quotes inside a word"),
    ("$'ssh' host", deny("ssh *"), "command-guard: ANSI-C quoting"),
    ("ssh\thost", deny("ssh *"), "command-guard: a tab between words"),
    ("echo $('ssh' host)", deny("ssh *"), "command-guard: inside a substitution too"),
    ("$CMD host", allow(), "a computed command name is not known before it runs"),
    ("scp results.csv host:/tmp/", deny("scp *"), ""),
    ("scp a.txt b.txt", deny("scp *"), "scp is denied outright, local or not"),
    ("sftp host", deny("sftp *"), ""),
    ("rsync -av src/ host:dst/", deny("rsync *:*"), ""),
    ("rsync rsync://mirror/module/ .", deny("rsync *:*"), ""),
    ("rsync host::module/ .", deny("rsync *:*"), ""),
    ("rsync -av src/ dst/", allow(), "a local rsync is a copy"),
    ("sshfs host:/data mnt", deny("sshfs *"), ""),
    ("ssh-copy-id user@host", deny("ssh-copy-id *"), ""),
    ("autossh -M 0 host", deny("autossh *"), ""),
    ("mosh host", deny("mosh *"), ""),
    ("mosh-server new", allow(), "a lookalike name"),

    # --- raw connections and transfer clients are denied
    ("nc -z host 22", deny("nc *"), ""),
    ("nc", deny("nc *"), ""),
    ("ls | nc host 9000", deny("nc *"), ""),
    ("ncdu .", allow(), "a lookalike name"),
    ("ncat host 80", deny("ncat *"), ""),
    ("netcat -u host 53", deny("netcat *"), ""),
    ("socat TCP:host:80 -", deny("socat *"), ""),
    ("socat - UNIX-CONNECT:/tmp/s", deny("socat *"), "every socat, a local socket too"),
    ("telnet host 25", deny("telnet *"), ""),
    ("ftp host", deny("ftp *"), ""),
    ("lftp -u user host", deny("lftp *"), ""),
    ("rclone copy out remote:bucket", deny("rclone *"), ""),

    # --- tunnels are denied
    ("ngrok http 8000", deny("ngrok *"), ""),
    ("cloudflared tunnel --url localhost:8000", deny("cloudflared *"), ""),
    ("tailscale serve 8000", deny("tailscale serve*"), ""),
    ("tailscale funnel 443", deny("tailscale funnel*"), ""),
    ("tailscale file cp out.pdf phone:", deny("tailscale file*"), ""),
    ("tailscale status", allow(), ""),

    # --- containers run only with no network
    ("docker run --rm --network=none alpine true", allow("docker run *--network=none *"), ""),
    ("docker run --rm --net none alpine true", allow("docker run *--net none *"), ""),
    ("docker run --net=none alpine", allow("docker run *--net=none *"), ""),
    ("docker run --rm --network=none -v \"$PWD\":\"$PWD\" -w \"$PWD\" alpine ls", allow("docker run *--network=none *"),
     "the containers skill's mount"),
    ("docker run -it --rm alpine sh", deny("docker run *"), ""),
    ("docker run", deny("docker run *"), ""),
    ("docker run --network host alpine", deny("docker run *"), ""),
    ("docker run --network=none alpine && docker run alpine", deny("docker run *"), "the second run has a network"),
    ("docker run alpine sh -c 'echo --network=none'", deny("docker run *"),
     "--network=none must be a word of its own, but a word anywhere in the command"),
    ("docker run alpine sh -c 'echo --network=none x'", deny("docker run"),
     "command-guard: --network=none after the image is the container's argument, not docker's"),
    ("DOCKER_HOST=ssh://h docker run --network=none alpine", deny("DOCKER_HOST"),
     "command-guard: the container would run on another machine"),
    ("export DOCKER_HOST=tcp://build:2375; docker ps", deny("DOCKER_HOST"), "command-guard"),
    ("env CONTAINER_HOST=ssh://h podman run --network=none alpine", deny("CONTAINER_HOST"), "command-guard"),
    ("docker run -v \"$PWD\":/src --rm --network=none -w /src alpine make", allow("docker run *--network=none *"),
     "valued options before --network are read past"),
    ("docker run -it --network none alpine sh", allow("docker run *--network none *"), "combined short flags"),
    ("docker run --network=bridge --network=none alpine true", allow("docker run *--network=none *"),
     "the last network option wins, as in docker"),
    ("docker run --network=none --network=host alpine true", deny("docker run"), "command-guard: host wins"),
    ("docker run --some-future-opt x --network=none alpine", deny("docker run"),
     "command-guard: an unknown option ends the scan - the safe side"),
    ("docker run --network=none-bridge alpine", deny("docker run *"),
     "a network merely named none-... (docker network create is allowed) is not none"),
    ("docker run --net none-bridge alpine", deny("docker run *"), ""),
    ("docker  run alpine", deny("docker run *"), "command-guard: two spaces after docker"),
    ("docker  run --network=none alpine", allow(), "the plain spelling is allowed, so the guard adds nothing"),
    ("sudo docker run alpine", deny("docker run *"), "command-guard: past sudo"),
    ("docker container run --rm alpine", deny("docker container run *"), ""),
    ("docker container run --network none alpine", allow("docker container run *--network none *"), ""),
    ("docker container run --network=none alpine", allow("docker container run *--network=none *"), ""),
    ("docker create --network=none alpine", allow("docker create *--network=none *"), ""),
    ("docker create --net none alpine", allow("docker create *--net none *"), ""),
    ("docker create --net=none alpine", allow("docker create *--net=none *"), ""),
    ("docker create -p 80:80 nginx", deny("docker create *"), ""),
    ("docker container create alpine", deny("docker container create *"), ""),
    ("docker container create --network=none alpine", allow("docker container create *--network=none *"), ""),
    ("docker container create --network none alpine", allow("docker container create *--network none *"), ""),
    ("docker container create --net=none alpine", allow("docker container create *--net=none *"), ""),
    ("docker container create --net none alpine", allow("docker container create *--net none *"), ""),
    ("docker run --rm --network none -w /src alpine true", allow("docker run *--network none *"), ""),
    ("docker container run --rm --net=none alpine", allow("docker container run *--net=none *"), ""),
    ("docker container run --net none alpine", allow("docker container run *--net none *"), ""),
    ("docker create --network none alpine", allow("docker create *--network none *"), ""),
    ("docker exec -it web sh", allow(), ""),
    ("docker logout", allow(), "a lookalike of login"),
    ("docker login -u me ghcr.io", deny("docker login*"), ""),
    ("docker push", deny("docker push *"), ""),
    ("docker manifest push me/x", deny("docker manifest push *"), ""),
    ("docker image push", deny("docker image push *"), ""),
    ("docker manifest inspect me/x", allow(), ""),
    ("docker build .", ask("docker build *"), ""),
    ("docker build --push -t me/x .", deny("docker *--push*"), "the later deny beats the build's ask"),
    ("docker image build -t x .", ask("docker image build *"), ""),
    ("docker buildx build -t x .", ask("docker buildx *"), ""),
    ("docker builder prune", allow(), "builder is not build"),
    ("docker compose up -d", ask("docker compose *"), ""),
    ("docker compose push", ask("docker compose *"), "asks, like the rest of compose"),
    ("docker-compose -f ci.yml up", ask("docker-compose *"), ""),
    ("docker -H tcp://10.0.0.1:2375 ps", deny("docker -H *"), ""),
    ("docker --host=tcp://h ps", deny("docker --host*"), ""),
    ("docker -c remote ps", deny("docker -c *"), ""),
    ("docker --context=remote run --network=none alpine", deny("docker --context*"),
     "the run's allow does not reach a remote engine"),
    ("docker context create remote --docker host=ssh://h", deny("docker context create*"), ""),
    ("docker context use default", deny("docker context use*"), ""),
    ("docker context ls", allow(), ""),

    # --- podman, the same
    ("podman run --rm alpine", deny("podman run *"), ""),
    ("podman run --network=none alpine", allow("podman run *--network=none *"), ""),
    ("podman run --net none alpine", allow("podman run *--net none *"), ""),
    ("podman run --network=slirp4netns alpine", deny("podman run *"), ""),
    ("podman container run --network none alpine", allow("podman container run *--network none *"), ""),
    ("podman container run alpine", deny("podman container run *"), ""),
    ("podman create alpine", deny("podman create *"), ""),
    ("podman create --net=none alpine", allow("podman create *--net=none *"), ""),
    ("podman container create --network=none alpine", allow("podman container create *--network=none *"), ""),
    ("podman container create alpine", deny("podman container create *"), ""),
    ("podman run --network none alpine", allow("podman run *--network none *"), ""),
    ("podman run --net=none alpine", allow("podman run *--net=none *"), ""),
    ("podman container run --network=none alpine", allow("podman container run *--network=none *"), ""),
    ("podman container run --net=none alpine", allow("podman container run *--net=none *"), ""),
    ("podman container run --net none alpine", allow("podman container run *--net none *"), ""),
    ("podman create --network=none alpine", allow("podman create *--network=none *"), ""),
    ("podman create --network none alpine", allow("podman create *--network none *"), ""),
    ("podman create --net none alpine", allow("podman create *--net none *"), ""),
    ("podman container create --network none alpine", allow("podman container create *--network none *"), ""),
    ("podman container create --net=none alpine", allow("podman container create *--net=none *"), ""),
    ("podman container create --net none alpine", allow("podman container create *--net none *"), ""),
    ("podman build -t x .", ask("podman build *"), ""),
    ("podman image build .", ask("podman image build *"), ""),
    ("podman buildx build .", ask("podman buildx *"), ""),
    ("podman compose up", ask("podman compose *"), ""),
    ("podman-compose up", ask("podman-compose *"), ""),
    ("podman image push me/x", deny("podman image push *"), ""),
    ("podman push me/x:1", deny("podman push *"), ""),
    ("podman manifest push list docker://me/x", deny("podman manifest push *"), ""),
    ("podman build --push -t me/x .", deny("podman *--push*"), ""),
    ("podman login", deny("podman login*"), ""),
    ("podman -r ps", deny("podman -r *"), ""),
    ("podman --remote=true ps", deny("podman --remote*"), ""),
    ("podman -c box ps", deny("podman -c *"), ""),
    ("podman --connection=box ps", deny("podman --connection*"), ""),
    ("podman --url unix:///run/x.sock ps", deny("podman --url*"), ""),
    ("podman system connection list", deny("podman system connection*"), "even listing them"),

    # --- Homebrew: installs ask, casks/taps/formula files/full path are denied
    ("brew install wget", ask("brew install*"), ""),
    ("brew install ruby", ask("brew install*"), "ruby is not a .rb file"),
    ("HOMEBREW_NO_AUTO_UPDATE=1 brew install wget", ask("brew install*"), ""),
    ("cd x && brew install wget", ask("brew install*"), ""),
    ("brew reinstall wget", ask("brew reinstall*"), ""),
    ("brew upgrade", ask("brew upgrade*"), ""),
    ("brew fetch wget", ask("brew fetch*"), ""),
    ("brew update", ask("brew update*"), ""),
    ("brew bundle", ask("brew bundle*"), ""),
    ("brew uninstall wget", ask("brew uninstall*"), ""),
    ("brew remove wget", ask("brew remove*"), ""),
    ("brew link wget", ask("brew link *"), ""),
    ("brew unlink wget", ask("brew unlink *"), ""),
    ("brew services start postgresql@16", ask("brew services*"), ""),
    ("brew cleanup", ask("brew cleanup*"), ""),
    ("brew autoremove", ask("brew autoremove*"), ""),
    ("brew pin wget", ask("brew pin *"), ""),
    ("brew unpin wget", ask("brew unpin *"), ""),
    ("brew linkage wget", allow(), "read-only, and not brew link"),
    ("brew info wget", allow(), "read-only stays behind the proxy"),
    ("brew deps --tree wget", allow(), ""),
    ("brew untap user/repo", allow(), "untap is not tap"),
    ("brew", allow(), "only a path before brew is denied"),
    ("brew install --cask firefox", deny("brew install *--cask*"), "the later deny beats install's ask"),
    ("brew install firefox --cask", deny("brew install *--cask*"), ""),
    ("brew --cask install firefox", deny("brew --cask *"), ""),
    ("brew reinstall --cask firefox", deny("brew reinstall *--cask*"), ""),
    ("brew upgrade --cask", deny("brew upgrade *--cask*"), ""),
    ("brew info --cask firefox", allow(), "reading about a cask installs nothing"),
    ("brew tap homebrew/cask-fonts", deny("brew tap ?*"), ""),
    ("brew tap-info homebrew/core", allow(), "read-only, and not brew tap"),
    ("brew tap", allow(), "with no argument it only lists the taps"),
    ("brew install user/tap/formula", deny("brew install */*"), ""),
    ("brew reinstall user/tap/formula", deny("brew reinstall */*"), ""),
    ("brew fetch user/tap/formula", deny("brew fetch */*"), ""),
    ("brew install ./wget.rb", deny("brew install *.rb*"), "a later rule than */*"),
    ("brew install https://example.com/x.rb", deny("brew install *://*"), "the last of three that match"),
    ("brew bundle --file=Brewfile", deny("brew bundle *--file*"), ""),
    ("/opt/homebrew/bin/brew install wget", deny("*/brew *"), "past the wrapper"),
    ("/usr/local/bin/brew list", deny("*/brew *"), "even read-only"),
    ("/opt/homebrew/bin/brew", deny("*/brew *"), ""),
    ("brew install wget && ssh host", deny("ssh *"), "the most restrictive of the chain"),

    # --- system package managers are denied outright
    ("apt-get install -y curl", deny("apt-get install*"), ""),
    ("apt-get remove curl", deny("apt-get remove*"), ""),
    ("apt-get purge curl", deny("apt-get purge*"), ""),
    ("apt-get update", deny("apt-get update*"), ""),
    ("apt-get upgrade -y", deny("apt-get upgrade*"), ""),
    ("apt-get dist-upgrade", deny("apt-get dist-upgrade*"), ""),
    ("apt install curl", deny("apt install*"), ""),
    ("apt remove curl", deny("apt remove*"), ""),
    ("apt purge curl", deny("apt purge*"), ""),
    ("apt update", deny("apt update*"), ""),
    ("apt upgrade", deny("apt upgrade*"), ""),
    ("apt search curl", allow(), "read-only"),
    ("apt list --installed", allow(), ""),
    ("apt full-upgrade", deny("apt full-upgrade*"), "dist-upgrade's apt name"),
    ("apt autoremove", deny("apt autoremove*"), ""),
    ("aptitude install curl", deny("aptitude install*"), ""),
    ("yum install gcc", deny("yum install*"), ""),
    ("yum remove gcc", deny("yum remove*"), ""),
    ("yum update", deny("yum update*"), ""),
    ("yum upgrade", deny("yum upgrade*"), ""),
    ("yum groupinstall 'Development Tools'", deny("yum groupinstall*"), ""),
    ("dnf install gcc", deny("dnf install*"), ""),
    ("dnf remove gcc", deny("dnf remove*"), ""),
    ("dnf update", deny("dnf update*"), ""),
    ("dnf upgrade", deny("dnf upgrade*"), ""),
    ("dnf group install 'Development Tools'", deny("dnf group install*"), ""),
    ("dnf groupinstall 'Development Tools'", deny("dnf groupinstall*"), "dnf's alias, as yum's"),
    ("dnf reinstall gcc", deny("dnf reinstall*"), ""),
    ("zypper install gcc", deny("zypper install*"), ""),
    ("zypper in gcc", deny("zypper in *"), ""),
    ("zypper remove gcc", deny("zypper remove*"), ""),
    ("zypper update", deny("zypper update*"), ""),
    ("zypper info gcc", allow(), "info is not in"),
    ("zypper rm gcc", deny("zypper rm *"), "zypper's alias for remove"),
    ("zypper up", deny("zypper up *"), "zypper's alias for update"),
    ("zypper dup", deny("zypper dup *"), ""),
    ("zypper patches", allow(), "a listing, not zypper patch"),
    ("pacman -S git", deny("pacman -S*"), ""),
    ("pacman -Ss git", allow("pacman -Ss *"), "a search installs nothing"),
    ("pacman -Si git", allow("pacman -Si *"), ""),
    ("pacman -Syu", deny("pacman -S*"), "an upgrade is still refused"),
    ("pacman -R git", deny("pacman -R*"), ""),
    ("pacman -U pkg.tar.zst", deny("pacman -U*"), ""),
    ("pacman -Q", allow(), ""),
    ("pacman --sync git", deny("pacman --sync*"), "the long form of -S"),
    ("pacman --remove git", deny("pacman --remove*"), ""),
    ("apk add curl", deny("apk add*"), ""),
    ("apk del curl", deny("apk del*"), ""),
    ("snap install code", deny("snap install*"), ""),
    ("flatpak install flathub org.x", deny("flatpak install*"), ""),
    ("port install wget", deny("port install*"), ""),
    ("dpkg -i pkg.deb", deny("dpkg -i*"), ""),
    ("dpkg -l", allow(), ""),
    ("dpkg --install pkg.deb", deny("dpkg --install*"), "the long form of -i"),
    ("dpkg -r curl", deny("dpkg -r*"), ""),
    ("dpkg -L curl", allow(), ""),
    ("rpm -i pkg.rpm", deny("rpm -i*"), ""),
    ("rpm -U pkg.rpm", deny("rpm -U*"), ""),
    ("rpm -qa", allow(), ""),
    ("rpm --install pkg.rpm", deny("rpm --install*"), "the long form of -i"),
    ("rpm -e gcc", deny("rpm -e*"), ""),
    ("rpm --eval '%{_libdir}'", allow(), "not --erase"),

    # --- pixi: another channel asks; upload, auth and self-update are denied
    ("pixi add numpy", allow(), "conda-forge, the default"),
    ("pixi install", allow(), ""),
    ("pixi run python fit.py", allow("pixi run *"), ""),
    ("pixi add -c bioconda samtools", ask("pixi * -c *"), ""),
    ("pixi add --channel bioconda samtools", ask("pixi *--channel*"), ""),
    ("pixi add --channel=bioconda samtools", ask("pixi *--channel*"), ""),
    ("pixi init --channel conda-forge", ask("pixi *--channel*"), "any channel flag asks, conda-forge too"),
    ("pixi global install -c bioconda samtools", ask("pixi * -c *"), ""),
    ("pixi upload https://prefix.dev/api/x pkg.conda", deny("pixi upload*"), ""),
    ("pixi auth login prefix.dev --token t", deny("pixi auth*"), ""),
    ("pixi self-update", deny("pixi self-update*"), ""),
    ("pixi workspace channel add bioconda", ask("pixi workspace channel add*"), ""),
    ("pixi workspace channel list", allow(), ""),
    ("pixi add bioconda::samtools", ask("pixi *::*"), "a channel-qualified spec (channel::package)"),
    ("pixi exec --spec bioconda::samtools samtools", ask("pixi *::*"), ""),
    ("pixi run python -c 'print(1)'", allow("pixi run *"), "python's own -c, not pixi's"),
    ("pixi run /opt/homebrew/bin/brew install wget", deny("*/brew *"), "the later rule beats pixi run's allow"),
    # An odd spelling of an ask would otherwise run without asking.
    ("git  push", deny("git push *"), "command-guard: written plainly, it asks"),
    ("'git' push origin main", deny("git push *"), "command-guard"),
    ("/usr/bin/git push", deny("git push *"), "command-guard: by its full path"),
    ("FOO=1 git push", ask("git push *"), "an assignment prefix is still the plain command"),
    ("sudo git push", ask("sudo *"), "the text as written already asks"),
    ("pixi run ssh host", deny("ssh *"), "command-guard: pixi run runs ssh"),
    ("pixi exec --spec openssh ssh host", deny("ssh *"), "command-guard: conda-forge ships openssh"),
    ("pixi exec -s openssh -- ssh host", deny("ssh *"), "command-guard: past pixi's -- too"),
    ("pixi add openssh", allow(), "installing it is not running it"),
    ("pixi global list", allow(), "a pixi subcommand that runs nothing"),
    ("uv run ssh host", deny("ssh *"), "command-guard: uv run runs ssh"),
    ("uv run --with numpy python fit.py", allow(), ""),
    ("uv pip install ssh-audit", allow(), "a package name, not a command"),
    ("uvx --from openssh-wrapper ssh host", deny("ssh *"), "command-guard: uvx runs ssh"),
    ("pipx run scp a b:", deny("scp *"), "command-guard: pipx run runs scp"),
    ("pipx install black", allow(), ""),
    ("parallel ssh {} uptime ::: h1 h2", deny("ssh *"), "command-guard: parallel runs ssh"),
    ("parallel -S h1,h2 echo ::: a b", deny("parallel *-S*"), "parallel itself runs commands on other machines"),
    ("parallel --sshlogin h1 echo ::: a", deny("parallel *--sshlogin*"), ""),
    ("parallel -j 4 gzip ::: a.log b.log", ask("<indirection-bash-wrapper>"), "the gate asks for what parallel runs, as for xargs"),
]


# (command touching a file, (decision, path rule)). The bash path gate runs the
# path rules over a command's path tokens; "none" means no path rule objected.
BASH_PATH = [
    ("cat .env", deny("*.env")),
    ("cp .env /tmp/env.bak", deny("*.env")),
    ("echo KEY=1 >> .env", deny("*.env")),
    ("source config/.env.local", deny("*.env.*")),
    ("cat .env.example", ("none", None)),
    ("grep -r TOKEN ~/.aws/credentials", deny("~/.aws/*")),
    ("cat ~/.ssh/id_ed25519.pub", deny("~/.ssh/*")),
    ("cat $HOME/.netrc", deny("~/.netrc")),
    ("less ~/.kube/config", deny("~/.kube/config")),
    ("cat ~/.docker/config.json", deny("~/.docker/config.json")),
    ("sed -i s/a/b/ .git/config", deny(".git/*")),
    ("cat ~/.pi/agent/auth.json", deny("~/.pi/*")),
    ("openssl x509 -in certs/server.pem -noout", deny("*.pem")),
    ("cat README.md", ("none", None)),
    ("wc -l data/results.csv", ("none", None)),
]


# (tool, path, (decision, path rule)). read/ls prove a read, write a write,
# edit both.
PATHS = [
    ("read", ".env", deny("*.env")),
    ("write", ".env", deny("*.env")),
    ("edit", ".env", deny("*.env")),
    ("read", "src/my.env", deny("*.env")),
    ("read", ".env.local", deny("*.env.*")),
    ("write", ".env.production", deny("*.env.*")),
    ("read", ".env.example", allow("*.env.example")),
    ("read", ".env.example.bak", deny("*.env.*")),
    ("read", "environment.yml", allow()),
    ("read", "dotenv.py", allow()),
    ("read", "sub/../.env", deny("*.env")),
    ("read", ".git/config", deny(".git/*")),
    ("write", ".git/hooks/pre-commit", deny(".git/*")),
    ("read", "vendor/lib/.git/HEAD", deny("*/.git/*")),
    ("read", ".gitignore", allow()),
    ("read", ".github/workflows/ci.yml", allow()),
    ("read", "~/.ssh/id_ed25519", deny("~/.ssh/*")),
    ("read", "~/.ssh/keys/work", deny("~/.ssh/*")),
    ("read", "id_rsa", deny("*id_rsa*")),
    ("read", "backup/id_rsa.pub", deny("*id_rsa*")),
    ("read", "server.pem", deny("*.pem")),
    ("read", "~/.aws/credentials", deny("~/.aws/*")),
    ("read", "~/.config/gh/hosts.yml", deny("~/.config/gh/*")),
    ("read", "~/.config/gcloud/application_default_credentials.json", deny("~/.config/gcloud/*")),
    ("read", "~/.config/nvim/init.lua", allow()),
    ("read", "~/.gnupg/pubring.kbx", deny("~/.gnupg/*")),
    ("read", "~/.azure/accessTokens.json", deny("~/.azure/*")),
    ("read", "~/.kube/config", deny("~/.kube/config")),
    ("read", "~/.kube/cache/discovery", allow()),
    ("read", "~/.docker/config.json", deny("~/.docker/config.json")),
    ("read", "~/.docker/daemon.json", allow()),
    ("read", "~/.netrc", deny("~/.netrc")),
    ("read", "~/.git-credentials", deny("~/.git-credentials")),
    ("read", "~/.npmrc", deny("~/.npmrc")),
    ("read", ".npmrc", allow()),
    ("read", "~/.pypirc", deny("~/.pypirc")),
    ("read", "~/.password-store/email.gpg", deny("~/.password-store/*")),
    ("read", "~/.pi/agent/auth.json", deny("~/.pi/*")),
    ("read", "~/.claude/settings.json", deny("~/.claude/*")),
    ("read", "~/.claude.json", deny("~/.claude.json")),
    ("read", "~/Library/Keychains/login.keychain-db", deny("~/Library/Keychains/*")),
    ("read", "~/Library/Cookies/Cookies.binarycookies", deny("~/Library/Cookies/*")),
    ("read", "~/Library/Safari/History.db", deny("~/Library/Safari/*")),
    ("read", "~/Library/Mail/V10/inbox.mbox", deny("~/Library/Mail/*")),
    ("read", "~/Library/Messages/chat.db", deny("~/Library/Messages/*")),
    ("read", "~/Library/Application Support/Google/Chrome/Default/Login Data",
     deny("~/Library/Application Support/Google/Chrome/*")),
    ("read", "~/Library/Application Support/Firefox/Profiles/x/key4.db",
     deny("~/Library/Application Support/Firefox/*")),
    ("read", "~/Library/Application Support/Code/User/settings.json", allow()),
    ("read", "~/.mozilla/firefox/x/key4.db", deny("~/.mozilla/*")),
    ("read", "~/.config/google-chrome/Default/Cookies", deny("~/.config/google-chrome/*")),
    ("read", "~/.config/chromium/Default/Cookies", deny("~/.config/chromium/*")),
    ("read", "~/.local/share/keyrings/login.keyring", deny("~/.local/share/keyrings/*")),
    ("read", "analysis/results.csv", allow()),
    # A link in the project to a credential is judged by where it points.
    ("read", "aws-link", deny("~/.aws/*")),
]


# (tool, path, (decision, rule)) on the external_directory surface. Paths use
# {install} and {agent} for the temporary install.
EXTERNAL = [
    ("read", "/etc/hosts", ask("*")),
    ("write", "/etc/hosts", ask("*")),
    ("read", "~/Documents/paper.tex", ask("*")),
    ("read", "/tmp/data.csv", allow("{tmp}/**")),
    ("read", "/tmp", allow("{tmp}")),
    ("write", "/tmp/out.csv", ask("*")),
    ("read", "/private/tmp/data.csv", allow("/private/tmp/**")),
    ("read", "/tmpfoo/x", ask("*")),
    ("read", "{install}/README.md", allow("{install}/**")),
    ("read", "{install}", allow("{install}")),
    ("write", "{install}/README.md", ask("*")),
    ("read", "{install}-old/README.md", ask("*")),
    ("read", "{agent}/workflows/review.md", allow("{agent}/workflows/**")),
    ("read", "{agent}/workflows", allow("{agent}/workflows")),
    ("write", "{agent}/workflows/review.md", ask("*")),
    ("write", "~/.cache/elm-pi/worktrees/proj/a.py", allow("~/.cache/elm-pi/worktrees/**")),
    ("read", "~/.cache/elm-pi/worktrees/proj/a.py", allow("~/.cache/elm-pi/worktrees/**")),
    ("write", "~/.cache/elm-pi/other.txt", ask("*")),
    ("write", "/tmp/pi-subagents-uid-501/run/out.md", allow("{tmp}/pi-subagents-uid-*/**")),
    ("write", "/private/tmp/pi-subagents-uid-501/out.md", allow("/private/tmp/pi-subagents-uid-*/**")),
    ("write", "/var/folders/ab/cd/T/pi-subagents-uid-501/out.md", allow("{var}/folders/*/*/T/pi-subagents-uid-*/**")),
    ("write", "/var/folders/ab/cd/T/other/out.md", ask("*")),
]


# (tool, path, auto-allowed as a Pi infrastructure read?)
INFRA = [
    ("read", "{agent}/skills/containers/SKILL.md", True),
    ("grep", "{agent}/npm/node_modules/x/index.ts", True),
    ("ls", "{agent}/skills", True),
    ("write", "{agent}/skills/x.md", False),
    ("edit", "{agent}/skills/x.md", False),
    ("read", "{install}/README.md", False),
    ("read", "~/.cache/elm-pi/worktrees/p/a.py", True),
    ("read", "~/.cache/other/x", False),
    ("find", "/tmp/pi-subagents-uid-501/run/out.md", True),
    ("read", "/tmp/other/out.md", False),
    ("read", "/private/var/folders/ab/cd/T/pi-subagents-uid-1/x.md", True),
]


TOOLS = ["read", "write", "bash", "subagent", "bg_wait", "subagent_supervisor",
         "contact_supervisor", "some_extension_tool"]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48] or "empty"


@functools.lru_cache(maxsize=None)
def results():
    """Run every case in one node process; None when the install is missing."""
    binary = node()
    if not binary or not (PACKAGE / "src/service.ts").exists() or not JITI.exists():
        return None
    # Resolved, so HOME has no symlink in it (macOS /var is /private/var).
    base = Path(tempfile.mkdtemp()).resolve()
    try:
        install, home, cwd = base / "install", base / "home", base / "project"
        agent = install / "agent"
        policy = agent / "extensions/pi-permission-system"
        for d in (policy, home / ".aws", cwd):
            d.mkdir(parents=True)
        text = TEMPLATE.read_text().replace("@AGENT_DIR@", str(agent)).replace("@INSTALL_DIR@", str(install))
        (policy / "config.json").write_text(text)
        (home / ".aws/credentials").write_text("[default]\n")
        (cwd / "aws-link").symlink_to(home / ".aws/credentials")
        fill = lambda p: p.replace("{install}", str(install)).replace("{agent}", str(agent))
        cases = {
            "bash": [c for c, _, _ in BASH],
            "bashPath": [c for c, _ in BASH_PATH],
            "path": [[t, p] for t, p, _ in PATHS],
            "external": [[t, fill(p)] for t, p, _ in EXTERNAL],
            "infra": [[t, fill(p)] for t, p, _ in INFRA],
            "tools": TOOLS,
        }
        (base / "cases.json").write_text(json.dumps(cases))
        run = subprocess.run(
            [binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
             str(JITI), str(PACKAGE), str(agent), str(cwd), str(base / "cases.json"), str(GUARD)],
            cwd=cwd, capture_output=True, text=True, timeout=300,
            env={**os.environ, "HOME": str(home), "NO_COLOR": "1", "PI_CODING_AGENT_DIR": str(agent)})
        if run.returncode != 0:
            raise AssertionError(f"the permission runner failed:\n{run.stderr}")
        out = json.loads(run.stdout)
        # /tmp and /var are links on macOS, and the canonical path's rule is the later one.
        out["fill"] = {"{install}": str(install), "{agent}": str(agent),
                       "{tmp}": os.path.realpath("/tmp"), "{var}": os.path.realpath("/var")}
        return out
    finally:
        shutil.rmtree(base, ignore_errors=True)


class RuleCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = results()
        if cls.out is None:
            raise unittest.SkipTest("needs node and the installed pi-permission-system (run bootstrap.sh)")

    def fill(self, pattern):
        if pattern is None:
            return None
        for key, value in self.out["fill"].items():
            pattern = pattern.replace(key, value)
        return pattern

    def check(self, got, decision, pattern):
        self.assertEqual(decision, got["state"], got)
        self.assertEqual(self.fill(pattern), got["pattern"], got)


class BashRuleTests(RuleCase):
    """A bash command's decision, rule and reason, as the tool-call gate gets them."""

    def check_bash(self, command, decision, pattern, known_gap=False):
        got = self.out["bash"][command]
        if known_gap:
            # Only the decision: a fix may well catch it with a new rule.
            self.assertEqual(decision, got["state"], got)
            return
        self.check(got, decision, pattern)
        rule = BASH_RULES.get(pattern)
        if decision == "deny" and isinstance(rule, dict):
            # The model is told why, so it stops rather than retrying around it.
            self.assertEqual(rule["reason"], got["reason"])


class BashPathTests(RuleCase):
    """The path rules applied to the files a bash command names."""


class PathRuleTests(RuleCase):
    """A file tool's path against the path rules (credentials, .env, .git)."""


class ExternalDirectoryTests(RuleCase):
    """A path outside the project: asks, but for the install, /tmp and sub-agent folders."""


class InfrastructureReadTests(RuleCase):
    """piInfrastructureReadPaths: what reads pi's own files without asking."""


class ToolAndConfigTests(RuleCase):
    """The tool-level rules, and the config loading cleanly in the package."""

    def test_every_tool_is_allowed_and_none_fully_denied(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                self.assertEqual({"state": "allow", "fullyDenied": False}, self.out["tools"][tool])

    def test_the_config_loads_without_issues(self):
        self.assertEqual([], self.out["loadIssues"])
        self.assertEqual([], self.out["policyIssues"])

    def test_bash_has_its_own_catch_all(self):
        # Without bash's own "*", a permissive top-level "*" would leave bash
        # ungated, and the package warns about exactly that.
        self.assertIsNone(self.out["permissiveBash"])


class CommandGuardTests(RuleCase):
    """command-guard.ts as pi runs it: a tool_call handler that refuses a bash call."""

    def test_a_denied_spelling_is_blocked_with_the_rules_reason(self):
        got = self.out["guard"]["denied"]
        self.assertTrue(got["block"])
        self.assertEqual(f"This command runs `ssh host`. {BASH_RULES['ssh *']['reason']}", got["reason"])

    def test_anything_else_is_left_to_the_gate(self):
        for case in ("allowed", "otherTool", "noCommand"):
            with self.subTest(case=case):
                self.assertIsNone(self.out["guard"][case])

    def test_without_the_gates_config_it_adds_nothing(self):
        # The gate reports a config it cannot read; the guard has no rules to add to.
        self.assertIsNone(self.out["guard"]["noConfig"])

    def test_an_engine_set_elsewhere_in_pis_environment_is_refused(self):
        got = self.out["guard"]["envRemote"]
        self.assertEqual(("DOCKER_HOST", "docker ps"), (got["pattern"], got["spelling"]))

    def test_a_local_engine_or_a_command_without_one_is_left_alone(self):
        for case in ("envSocket", "envDefault", "envNotAnEngine"):
            with self.subTest(case=case):
                self.assertIsNone(self.out["guard"][case])

    def test_a_rule_without_a_reason_is_named(self):
        self.assertEqual({"pattern": "x *", "spelling": "x y"}, self.out["guard"]["plainDeny"])


def add(cls, name, method, note=""):
    if note.startswith("BUG:"):
        method = unittest.expectedFailure(method)
    method.__doc__ = note or None
    assert not hasattr(cls, name), name
    setattr(cls, name, method)


def build():
    seen = set()
    for i, (command, (decision, pattern), note) in enumerate(BASH):
        assert command not in seen, command
        seen.add(command)
        add(BashRuleTests, f"test_{i:03d}_{slug(command)}",
            lambda self, c=command, d=decision, p=pattern, g=note.startswith("BUG:"): self.check_bash(c, d, p, g),
            note)
    for i, (command, (decision, pattern)) in enumerate(BASH_PATH):
        add(BashPathTests, f"test_{i:03d}_{slug(command)}",
            lambda self, c=command, d=decision, p=pattern: self.check(self.out["bashPath"][c], d, p))
    for i, (tool, path, (decision, pattern)) in enumerate(PATHS):
        add(PathRuleTests, f"test_{i:03d}_{tool}_{slug(path)}",
            lambda self, k=f"{tool} {path}", d=decision, p=pattern: self.check(self.out["path"][k], d, p))
    for i, (tool, path, (decision, pattern)) in enumerate(EXTERNAL):
        add(ExternalDirectoryTests, f"test_{i:03d}_{tool}_{slug(path)}",
            lambda self, t=tool, p=path, d=decision, pat=pattern:
                self.check(self.out["external"][f"{t} {self.fill(p)}"], d, pat))
    for i, (tool, path, want) in enumerate(INFRA):
        add(InfrastructureReadTests, f"test_{i:03d}_{tool}_{slug(path)}",
            lambda self, t=tool, p=path, w=want: self.assertIs(w, self.out["infra"][f"{t} {self.fill(p)}"]))


build()


if __name__ == "__main__":
    unittest.main()
