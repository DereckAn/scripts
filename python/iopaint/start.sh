#!/bin/zsh
# Launch IOPaint web UI. Usage: ./start.sh [cpu|mps]  (default cpu)
cd "${0:A:h}"
exec .venv/bin/iopaint start --model=lama --device="${1:-cpu}" --port=8080
