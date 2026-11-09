#!/bin/bash
# tools/images.sh <map.svg> <out dir>: <name>-overview.png at a quarter of the size, and 4×3 full-resolution tiles in <out dir>/tiles
set -euo pipefail
svg=$1; out=$2
read -r W H < <(python3 -c "import re,sys;s=open(sys.argv[1]).read(4000);m=re.search(r'width=\"(\d+)\" height=\"(\d+)\"',s);print(m[1],m[2])" "$svg")
here=$(dirname "$0")
name=$(basename "$svg" .svg)
mkdir -p "$out/tiles"
node "$here/shot.js" "$svg" "$out/$name-overview.png" $(( (W + 3) / 4 )) $(( (H + 3) / 4 )) 0 0 0.25
TW=$(( (W + 3) / 4 )); TH=$(( (H + 2) / 3 ))
for r in 0 1 2; do for c in 0 1 2 3; do
  node "$here/shot.js" "$svg" "$out/tiles/tile-r$((r + 1))-c$((c + 1)).png" $TW $TH $((c * TW)) $((r * TH)) 1
done; done
echo "overview $(( (W + 3) / 4 ))x$(( (H + 3) / 4 )), tiles ${TW}x${TH}"
