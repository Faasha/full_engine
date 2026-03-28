#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SRC="engine/native/field_diffuse.c"
OUT="engine/native/libfield_diffuse.so"

cc -O3 -fPIC -shared "$SRC" -o "$OUT"

echo "Built $OUT"
