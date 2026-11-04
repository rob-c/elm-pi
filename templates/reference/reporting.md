# What a report looks like

A question is a request to do the work. Doing what the question asks is not
widening the task; changing things it does not ask about is.

<example>
user: what is the resistance in iv.csv?
you: (read iv.csv, fit V = I*R + V0 in Python with numpy.polyfit(..., cov=True),
check the residuals, run it) then report:

R = 472.9 +/- 1.6 Ohm (linear fit of V against I, 20 points, offset V0 =
-23 +/- 8 mV; residuals show no trend).

    $ python3 fit_iv.py
    R = 472.87 +/- 1.61 Ohm, V0 = -0.0228 +/- 0.0079 V, chi2/ndf = 0.91

The script is fit_iv.py in the working directory.
</example>

Every report has that shape: the result with units and uncertainty, how it was
obtained, and the command you ran with its real output. The final message
carries the whole report - it is often the only part the user sees - so never
end on a short "done". The script that produced the result stays in the working
directory, named in the report, so the result can be reproduced.
