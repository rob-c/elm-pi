"""Writes environment/ for this task: the bench notes. Nothing is random.

    python make_environment.py <environment dir>

Channel B is generated on the saturated branch of an extending dead time: a
true rate of 1.5e6 /s with 1.20 us gives n tau = 1.8, past the maximum at
n tau = 1, so it reads 248 k/s - the same reading a true rate of 401 k/s would
give. The second reading, with the source further away, is what tells them
apart: it follows the inverse square law from the true rate and is higher.
"""
import math
import sys
from pathlib import Path

out = Path(sys.argv[1])

LIVE = 10.0                                   # s, rate checks
TAU_A, TRUE_A = 2.50e-6, 106_810.0            # non-extending
TAU_B, TRUE_B = 1.20e-6, 1.500e6              # extending
NEAR, FAR = 10.0, 14.0                        # cm
RUN = 600.0                                   # s, coincidence run
WIDTH = 40.0e-9                               # s, each logic pulse
SINGLES_A, SINGLES_B, TRUE_COINCIDENCES = 5210.0, 3870.0, 13.007

measured_a = TRUE_A / (1 + TRUE_A * TAU_A)
measured_b = TRUE_B * math.exp(-TRUE_B * TAU_B)
far_b = TRUE_B * (NEAR / FAR) ** 2
measured_b_far = far_b * math.exp(-far_b * TAU_B)
coincidences = TRUE_COINCIDENCES + 2 * WIDTH * SINGLES_A * SINGLES_B


def counts(rate, seconds, step):
    """As read off the scaler, with a space every three digits."""
    return format(int(round(rate * seconds / step) * step), ",").replace(",", " ")


(out / "notes.md").write_text("""# Timing bench: rate checks and coincidence run

## Channel A: LaBr3, constant-fraction discriminator, then a fixed veto gate

- The gate blocks the channel for %.2f us after every accepted pulse. A pulse
  that arrives while it is blocked is lost and does not prolong it
  (non-extending dead time).
- Strong source in the run position: %s counts in %.3f s.

## Channel B: plastic scintillator, updating discriminator

- Output width %.2f us, measured with the pulser. Every pulse that arrives
  during the output restarts it (extending dead time).
- Strong source at %.1f cm: %s counts in %.3f s.
- The same source pulled back to %.1f cm: %s counts in %.3f s.

## Coincidence run

- Weak source; dead-time losses are below 0.1%% in both channels: ignore them.
- Each discriminator sends a logic pulse %.1f ns wide to the overlap (AND)
  coincidence unit, which fires on any overlap of the two.
- Run time %.1f s. Singles at the coincidence unit's inputs: A %s counts,
  B %s counts. Coincidences: %s counts.
- No delayed-coincidence channel was set up for this run.
""" % (TAU_A * 1e6, counts(measured_a, LIVE, 100), LIVE,
       TAU_B * 1e6, NEAR, counts(measured_b, LIVE, 10), LIVE, FAR, counts(measured_b_far, LIVE, 10), LIVE,
       WIDTH * 1e9, RUN, counts(SINGLES_A, RUN, 1), counts(SINGLES_B, RUN, 1), counts(coincidences, RUN, 1)))
print("A reads %.0f /s; B reads %.0f /s at %.0f cm and %.0f /s at %.0f cm; %.3f coincidences/s"
      % (measured_a, measured_b, NEAR, measured_b_far, FAR, coincidences))
