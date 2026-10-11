#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$(id -u)" == 0 ]]; then
  echo 'Run make setup as the participating account, never root.' >&2
  exit 1
fi
if [[ ! -t 0 ]]; then
  echo 'Setup needs an interactive terminal. For CI, use uv sync --locked and make check.' >&2
  exit 1
fi
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
case "$(uname -s)" in
  Darwin) xcode-select -p >/dev/null || { xcode-select --install; echo 'Finish Apple’s installation, then rerun make setup.'; exit 1; } ;;
  Linux) . /etc/os-release; [[ "$ID" == ubuntu ]] || { echo 'Only Ubuntu is supported on Linux.'; exit 1; } ;;
  *) echo 'Only macOS and Ubuntu are supported.'; exit 1 ;;
esac
if ! command -v uv >/dev/null; then
  read -r -p 'Install uv and uvx in ~/.local/bin using Astral’s official installer? (y/n) [n]: ' answer
  [[ "$answer" == y || "$answer" == yes ]] || { echo 'Paused; rerun make setup when ready.'; exit 1; }
  if ! command -v curl >/dev/null; then
    read -r -p 'Install curl through apt using administrator permission? (y/n) [n]: ' answer
    [[ "$answer" == y || "$answer" == yes ]] || exit 1
    sudo apt-get update
    sudo apt-get install -y curl
  fi
  installer="$(mktemp)"
  trap 'rm -f -- "$installer"' EXIT
  curl --fail --location --silent --show-error https://astral.sh/uv/install.sh --output "$installer"
  UV_INSTALL_DIR="$HOME/.local/bin" INSTALLER_NO_MODIFY_PATH=1 sh "$installer"
  rm -f -- "$installer"
  trap - EXIT
fi
bash bootstrap.sh
exec .venv/bin/python src/boflow.py setup
