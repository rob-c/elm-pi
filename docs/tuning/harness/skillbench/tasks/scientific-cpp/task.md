---
skill: scientific-cpp
also: changing-code
category: code
pitfall: the reported overflow (squares summed in an int) patched and only the reported example rerun; std::accumulate with an int initial value still overflows the mean on long runs, which the sanitizer build or a numpy comparison on the long run in data/ shows
timeout_sec: 900
---
adcstat.cpp prints rms nan for the pedestal run of the new 16-bit module, while the 12-bit runs come out fine: README.md has the commands and what they print. Fix it so that its numbers are right - all of the test-beam data go through it next week - and keep the command line and the output format as they are.
