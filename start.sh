#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Optional venv (used when deps were installed)
if [[ -d .venv && -x .venv/bin/python ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  PYTHON="${ROOT}/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

# Best-effort optional install (may be blocked in some environments)
if ! "$PYTHON" -c "import demucs, torch" 2>/dev/null; then
  if [[ "${INSTALL_DEPS:-0}" == "1" ]]; then
    echo "[start] INSTALL_DEPS=1 → installing torch (CPU) + demucs…"
    "$PYTHON" -m pip install -U pip wheel
    "$PYTHON" -m pip install torch --index-url https://download.pytorch.org/whl/cpu || true
    "$PYTHON" -m pip install -r requirements.txt || true
  else
    echo "[start] Demucs/torch not found — using ffmpeg mid/side fallback."
    echo "[start] To try AI install later: INSTALL_DEPS=1 ./start.sh"
  fi
fi

mkdir -p data/uploads data/outputs
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8765}"
export DEMUCS_MODEL="${DEMUCS_MODEL:-htdemucs}"
export DEMUCS_DEVICE="${DEMUCS_DEVICE:-cpu}"
export DEMUCS_SEGMENT="${DEMUCS_SEGMENT:-7}"
export STEM_PROVIDER="${STEM_PROVIDER:-auto}"
export STEMSPLIT_BASE_URL="${STEMSPLIT_BASE_URL:-https://stemsplit.io}"
export STEMSPLIT_QUALITY="${STEMSPLIT_QUALITY:-BALANCED}"
export STEMSPLIT_OUTPUT_FORMAT="${STEMSPLIT_OUTPUT_FORMAT:-WAV}"
# STEMSPLIT_API_KEY: set in the environment; do not hardcode

if [[ -n "${STEMSPLIT_API_KEY:-}" ]]; then
  echo "[start] StemSplit API key detected (provider auto→stemsplit unless STEM_PROVIDER overrides)."
else
  echo "[start] No STEMSPLIT_API_KEY — using local demucs/ffmpeg unless STEM_PROVIDER=stemsplit."
fi

echo "[start] Stem Splitter PWA → http://127.0.0.1:${PORT}/"
exec "$PYTHON" app.py
