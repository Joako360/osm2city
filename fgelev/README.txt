A patched version of fgelev.

I added a cmd line flag "--expire". Usage:
fgelev --expire <INTEGER>

I *THINK* fgelev expires the loaded scenery part once it hasn't been accessed 
in the last $expire probes. By default this value is rather small (10),
and automated elevation probing by osm2city was painfully slow due to frequent
terrain reloads.

Increasing $expire to O(10^7) solves this problem.
