#!/usr/bin/env bash
set -euo pipefail
product_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(id -u)" == 0 ]]; then
  echo 'Run bootstrap as the participating account, not root.' >&2
  exit 1
fi
case "$(uname -s)" in
  Darwin|Linux) ;;
  *) echo 'Only macOS and Ubuntu are supported.' >&2; exit 1 ;;
esac
command -v git >/dev/null || { echo 'Install Git first.' >&2; exit 1; }
if ! command -v uv >/dev/null; then
  echo 'Install uv using https://docs.astral.sh/uv/getting-started/installation/ then rerun.' >&2
  exit 1
fi
state_dir="${BOFLOW_STATE:-$HOME/.local/share/boflow}"
umask 077
mkdir -p "$state_dir/bin"
uv sync --locked --project "$product_dir"
"$product_dir/.venv/bin/python" "$product_dir/src/boflow.py" install-launcher
printf 'Installed. Next: %s/bin/boflow enroll --repo OWNER/PRIVATE-REPO\n' "$state_dir"
