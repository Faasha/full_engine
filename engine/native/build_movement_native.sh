#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SRC="engine/native/movement_native.c"
OUT="engine/native/libmovement_native.so"

cc -O3 -fPIC -shared "$SRC" -o "$OUT"

echo "Built $OUT"
