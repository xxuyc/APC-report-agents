#!/usr/bin/env bash
set -euo pipefail

knowledge=false
if [[ "${1:-}" == "--knowledge" ]]; then
  knowledge=true
elif [[ -n "${1:-}" ]]; then
  echo "Usage: ./install.sh [--knowledge]" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workbuddy_root="${HOME}/.workbuddy/skills"
skill_link="${workbuddy_root}/APC-report-agents"
mkdir -p "${workbuddy_root}"

if [[ -L "${skill_link}" ]]; then
  existing="$(cd "$(dirname "${skill_link}")" && cd "$(readlink "${skill_link}")" && pwd)"
  if [[ "${existing}" != "${repo_root}" ]]; then
    echo "Install target already links elsewhere and was not changed: ${skill_link}" >&2
    exit 3
  fi
elif [[ -e "${skill_link}" ]]; then
  echo "Install target already exists and was not changed: ${skill_link}" >&2
  exit 3
else
  ln -s "${repo_root}" "${skill_link}"
fi

python_cmd="$(command -v python3 || command -v python)"
"${python_cmd}" -m venv "${repo_root}/.venv"
requirements="requirements.txt"
if [[ "${knowledge}" == "true" ]]; then
  requirements="requirements-knowledge.txt"
fi
"${repo_root}/.venv/bin/python" -m pip install -r "${repo_root}/${requirements}"
"${repo_root}/.venv/bin/python" "${repo_root}/scripts/verify_release.py"
echo "Installed APC Report Agents for the current WorkBuddy user."
echo "Python: ${repo_root}/.venv/bin/python"
