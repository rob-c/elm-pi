"""What the task is built to catch: both gluon polarisation sums replaced by -g_{mu nu}, no ghosts.

The same three diagrams, colour sums and 1/256 average as solve.py. The sum
over each gluon's polarisations is the covariant one, which is what a trace
calculation does unless told otherwise: with two external gluons it counts the
unphysical polarisations as well, 15 to 23% at these points.
"""
import json
import sys

import numpy as np

sys.dont_write_bytecode = True      # importing solve.py must not leave a cache in oracle/
from solve import METRIC, read_points, squared  # noqa: E402


def covariant(k):
    """-g_{mu nu} as a sum over the four unit vectors with weights -g^{mu mu}: -1, +1, +1, +1."""
    return [(unit, -METRIC[mu, mu]) for mu, unit in enumerate(np.eye(4))]


json.dump({"msq_%d" % number: squared(point, covariant) for number, point in read_points().items()},
          open("result.json", "w"), indent=1)
