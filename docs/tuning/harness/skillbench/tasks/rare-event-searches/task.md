---
skill: rare-event-searches
also: statistics-and-significance, hep-likelihood-limits
category: particle
pitfall: excess over sqrt(background) quoted as the significance of an on/off excess; a Gaussian, classical one-sided or CLs limit where the plan says Feldman-Cousins; signal containment or unit conversions left out of the exposure
timeout_sec: 900
---
counts.csv has the counts and live times from our ON/OFF observations of the two targets, and notes.md the analysis plan and target B's exposure. What is the significance of target A's excess, and for target B what are the 90% CL upper limit on the signal counts, the median limit we expected, and the upper limit on the integral flux above 200 GeV? Write result.json with significance_sigma, limit_counts, expected_limit_counts and flux_limit_cm2_s (photons per cm^2 per s).
