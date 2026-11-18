---
skill: changing-code
also: scientific-python
category: code
pitfall: the reported example fixed with a one-level copy of the defaults; the nested gain and pedestal dicts and the masked list are still shared, so the next run, the same run looked up twice, or a caller that edits its result still get wrong constants
timeout_sec: 900
---
In calib.py, calibration(1042) comes back with threshold_mv 45.0 once calibration(1041) has been called. 45.0 is run 1041's override; 1042 has none, so it should be 30.0. Can you fix it?
