# Timing bench: rate checks and coincidence run

## Channel A: LaBr3, constant-fraction discriminator, then a fixed veto gate

- The gate blocks the channel for 2.50 us after every accepted pulse. A pulse
  that arrives while it is blocked is lost and does not prolong it
  (non-extending dead time).
- Strong source in the run position: 843 000 counts in 10.000 s.

## Channel B: plastic scintillator, updating discriminator

- Output width 1.20 us, measured with the pulser. Every pulse that arrives
  during the output restarts it (extending dead time).
- Strong source at 10.0 cm: 2 479 480 counts in 10.000 s.
- The same source pulled back to 14.0 cm: 3 054 870 counts in 10.000 s.

## Coincidence run

- Weak source; dead-time losses are below 0.1% in both channels: ignore them.
- Each discriminator sends a logic pulse 40.0 ns wide to the overlap (AND)
  coincidence unit, which fires on any overlap of the two.
- Run time 600.0 s. Singles at the coincidence unit's inputs: A 3 126 000 counts,
  B 2 322 000 counts. Coincidences: 8 772 counts.
- No delayed-coincidence channel was set up for this run.
