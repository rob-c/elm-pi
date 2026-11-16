"""A launch the launcher itself ends: the lines to print and the exit code.

Every refusal the reference launcher prints is a group of lines on stderr followed
by `exit N`, so the shape that travels from the code that decides to the code
that prints is a list of finished lines. Keeping the lines finished - rather
than a template plus arguments - is what lets the two implementations be
compared line for line.
"""

# Exit codes this launcher uses, named where the distinction matters:
#   1  the install cannot start as it is (missing key, missing file)
#   2  the caller asked for something this install does not offer
CANNOT_START = 1
REFUSED = 2


class Refusal(Exception):
    """Raised anywhere, printed once at the top, returned as `code`.

    Not an error: a refusal is a decision the launcher makes on purpose, with
    the route that works printed beside it.
    """

    def __init__(self, *lines, code=REFUSED):
        self.code = code
        self.lines = [str(line) for line in lines]
        super().__init__(self.lines[0] if self.lines else "")

    @classmethod
    def about(cls, headline, *details, code=REFUSED):
        """The usual shape: `pi: <headline>`, then four-space detail lines."""
        return cls("pi: " + headline, *("    " + detail for detail in details), code=code)
