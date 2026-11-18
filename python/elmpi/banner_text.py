"""The "Powered by ELM" banner text.

A session started at a terminal opens by crediting the service it runs on and
the team that hosts it, while pi takes its few seconds to start. The text is
the reference launcher's, byte for byte; banner.py decides when to draw it and how
to colour it, so that a test can compare this with the original line for line.

Plain ASCII, and colours from the 256-colour palette - 22 (#005f00, dark green)
on 255 (#eeeeee, light grey), about 6.9:1 contrast - whose entries are fixed
RGB in practically every terminal, unlike the 16 basic colours each theme
redefines (and "bold is bright" recolours).
"""

BANNER = """\

Powered by ELM:

     .-----.       EEEEEEE  LL       MM     MM
  .-'  (@)  '-.    EE       LL       MMM   MMM
 ( (@)  |  (@) )   EEEEE    LL       MM MMM MM
  '-- '.|.' --'    EE       LL       MM     MM
   o_.--'--._o     EEEEEEE  LLLLLLL  MM     MM

elm-pi uses only the models the University of Edinburgh hosts on ELM,
which are free at the point of use. Thank you to the ELM team at EDINA.
https://elm.edina.ac.uk/elm

"""
