---
name: package-admin
description: "Setting up a service or a cluster there is no recipe for here - a scheduler, a database, several that talk to each other: research each step in its documentation, do it, check it, search the exact error when it fails."
---

# Setting up software you have no recipe for

You are the administrator, and you have not installed this before. What you
remember of it is a draft: package names, option names and defaults change
between versions and between distributions, and a setup written from memory
fails at the third step for a reason the documentation states in a sentence.
So the documentation is read first, and again at every failure.

## The loop

For the whole job, then for each step of it:

1. **Research.** The first question is always whether the distribution
   already packages it ("NAME ubuntu 22.04 package", `apt-cache search NAME`
   or `dnf search NAME` in a throwaway container): packages built for this
   distribution and this machine's processor are the plainest route there is,
   and a search for "NAME docker" finds other people's images instead. Then
   `web_search` for the software's own installation and
   configuration documentation, naming the operating system and its version
   ("slurm quick start administrator guide", "munge installation ubuntu 22.04
   package"). Read the pages that answer, with `get_search_content`. Prefer the
   project's own manual and the distribution's package page over a blog or an
   answer site, and open the manual itself with `fetch_content` - a search
   snippet is not the page. When two sources disagree, the one for your version
   wins: **the version you install is the one whose documentation applies**.
   A distribution's package is often years behind the project's current
   manual, and an option from the newer manual is an "unrecognized key" in the
   older program. Find the version first (`apt-cache policy NAME`, `NAME --version`)
   and read for that.
2. **Write down what you found** in `INSTALL-LOG.md`, as you go: the question,
   the answer in a line, the URL. Before the first command, the plan: which
   packages, which daemons run where, which ports and files they share, in what
   order they start, and the command that shows each one is up.
3. **Do one step.** One package set, one daemon, one configuration file.
   Take the plainest route the documentation offers: the distribution's own
   packages before building from source, one image for every machine of a
   cluster, the stock way of sharing configuration before anything invented.
   Each machine runs what the user said it runs and nothing more: a controller
   that also runs a worker is not "one head node and one compute node".
4. **Check it with the software's own status command** before the next step -
   not by its having exited without an error. A daemon is up when its client
   answers, not when it was started.
5. **When it fails, search before you edit.** Take the exact message, quote it
   in a `web_search` with the software's name and version, and read what it
   means. Two attempts at a fix without a search between them is guessing.
   Record the cause and the source in the notes.

## Do not conclude it cannot be done from one error

"This cannot work in a container", "this version requires X" - that is a claim
about someone else's software, and it needs their documentation behind it: the
page and the sentence. Search for how others run it in the situation you are
in ("NAME in docker without systemd", "NAME rootless", "NAME disable cgroup").
If the sources do say it is impossible, say so with the URL and stop: do not
build something else in its place and present it as what was asked for.

## What is fixed on this machine

These are this install's rules, not the software's. Research how to work
within them; none of them is the end of the task.

- Containers reach each other only on a network made with `--internal`, and
  have **no internet when they run**: everything is installed in the image
  (`docker build`, which asks the user once), nothing at start-up.
- **A build has the internet; your own shell does not.** `curl` from the
  shell goes through this session's proxy, which refuses most hosts (403,
  "not on the allowlist"), so it cannot tell you whether a `RUN` step in a
  `docker build` can download something - the build is not behind that proxy.
  And a host name that "could not be resolved" inside a build is a wrong
  name, not a blocked one: look the repository's real address up in its
  installation guide before concluding anything.
- **A build has no terminal.** A package install that stops to ask a question
  (apt asking for a time zone is the usual one) waits until the time limit
  with nothing printed. Install without questions - for apt,
  `DEBIAN_FRONTEND=noninteractive` on the `RUN` line - and when a build goes
  silent for minutes, look at its last line (`--progress=plain`) before
  running it again.
- No `--privileged`, no host network, no host cgroups: inside a container
  `/sys/fs/cgroup` is read-only and there is no systemd. Software that wants
  either has a documented way to run without it; find that.
- A command that names a `.key` or `.pem` file is refused as secret access,
  even for a file inside a container. Create keys in the image build, or with
  the software's own key tool, not by copying them about with `docker cp`.
- Check the processor (`uname -m`): on an Apple Silicon Mac it is arm64, and
  an image or binary built only for amd64 runs under emulation - slowly, and
  for daemons often not at all. Use what is built for this machine.
- Images: an official base (`ubuntu`, `debian`, `rockylinux`, `mariadb` - a
  name with no publisher in front) and the distribution's own packages on it.
  Another publisher's ready-made image asks the user first.
- See the `containers` skill for the commands, and for several containers
  that talk to each other.

## Finish

- Prove it end to end with a real use of the thing (a job run, a query
  answered, a message delivered), from the place a user would do it.
- Say what is running, the commands to use it and to remove all of it. If
  any part of what was asked for is not working, the first line of your reply
  says which part - before anything that does work.
- `INSTALL-LOG.md` stays: the steps that worked, in order, each with its
  source, and every dead end with what the error turned out to mean. The next
  person installs from that file.
