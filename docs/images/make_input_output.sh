#!/bin/bash
TMPDIR=`mktemp -d` || exit 1
convert -delay 50 -loop 0 frames/*.jpg align_input.gif
python3 ../../scripts/align_planet.py "$TMPDIR" ./frames/*.jpg
convert -delay 50 -loop 0 "$TMPDIR/*.jpg" align_output.gif
rm -rf "$TMPDIR"
