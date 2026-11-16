"""The launcher's own flags: the ones consumed here, and the rest for pi.

`pi --fast`, `pi --remote`, `pi --manual` are this install's, not pi's. They
are taken out of the argument list before anything else looks at it, and the
remaining arguments are exactly what pi would have been given - same order,
same `--`, same option values - which matters because pi's parser sees only
what is left.

The parse stops looking for flags at `--`, and skips the value of an option
that takes one, so `pi -p "--remote is great"` is a prompt and `pi --name
--fast` names a session instead of turning discovery off.
"""

from dataclasses import dataclass, field

from elmpi.argwalk import takes_value


@dataclass
class Switches:
    """What the caller asked this install for, before pi sees anything."""

    fast: bool = False
    offline: bool = False
    trusted: bool = False
    llama: bool = False
    mistral: bool = False
    remote: bool = False
    computer_use: bool = True
    workflows: bool = True
    with_all: bool = False
    mode: str = ""
    rest: list = field(default_factory=list)

    @property
    def network_flag(self):
        """The network mode this run's flags chose, or "" for the default."""
        from elmpi import network
        if self.offline:
            return network.OFFLINE
        if self.remote or self.mode == network.YOLO:
            return network.YOLO
        if self.trusted:
            return network.TRUSTED
        return ""

    @property
    def model_flag(self):
        """The model a shortcut asked for, if any: --llama or --mistral."""
        if self.llama:
            return "llama"
        return "mistral" if self.mistral else ""


# Each flag this launcher consumes, and what it sets. `--with-all` turns the
# workflow tools on as well: "every optional extra" includes them.
CONSUMED = {
    "--fast": (("fast", True),),
    "--offline": (("offline", True),),
    "--trusted-remote": (("trusted", True),),
    "--llama": (("llama", True),),
    "--mistral": (("mistral", True),),
    "--remote": (("remote", True),),
    "--no-computer-use": (("computer_use", False),),
    "--workflows": (("workflows", True),),
    "--no-workflows": (("workflows", False),),
    "--with-all": (("with_all", True), ("workflows", True)),
    "--manual": (("mode", "manual"),),
    "--read-only-auto": (("mode", "read-only-auto"),),
    "--auto": (("mode", "auto"),),
    "--yolo": (("mode", "yolo"),),
}


def parse(argv, env):
    """Split `argv` into this launcher's switches and pi's arguments."""
    # Offered by default; PI_ELM_WORKFLOWS=0 (or --no-workflows) leaves the
    # workflow tool out. Computer use is the other way round: it comes with
    # --remote unless PI_ELM_COMPUTER_USE=0 says no.
    switches = Switches(
        workflows=env.get("PI_ELM_WORKFLOWS", "1") != "0",
        computer_use=env.get("PI_ELM_COMPUTER_USE") != "0",
    )
    previous = ""
    for argument in argv:
        if previous:
            switches.rest.append(argument)
            if previous != "stop":
                previous = ""
            continue
        if argument == "--":
            previous = "stop"
            switches.rest.append(argument)
            continue
        consumed = CONSUMED.get(argument)
        if consumed is None:
            switches.rest.append(argument)
            if takes_value(argument):
                previous = "value"
            continue
        for name, value in consumed:
            setattr(switches, name, value)
    return switches


def conflict(switches):
    """--llama and --mistral each choose the model; both is a question."""
    return switches.llama and switches.mistral
