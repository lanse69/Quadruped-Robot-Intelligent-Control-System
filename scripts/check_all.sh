#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---quick}"
PYTHON_BIN="${PYTHON:-python}"

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

activate_venv_if_present() {
  if [[ -d .venv ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    PYTHON_BIN="python"
  fi
}

require_command() {
  if ! has_command "$1"; then
    printf '\n==> required command not found: %s\n' "$1" >&2
    exit 1
  fi
}

cpp_files_expr="find include src apps tests/cpp \( -name '*.hpp' -o -name '*.cpp' \) -print0"

run_cpp_format() {
  require_command clang-format
  run bash -lc "${cpp_files_expr} | xargs -0 clang-format -i"
}

run_python_format() {
  activate_venv_if_present
  run "${PYTHON_BIN}" -m ruff check python tests/python --fix
  run "${PYTHON_BIN}" -m black python tests/python
}

run_cpp_quick() {
  require_command cmake
  run cmake --preset dev-gcc-debug
  run cmake --build --preset dev-gcc-debug
  run ctest --preset dev-gcc-debug --output-on-failure
}

run_cpp_full() {
  run_cpp_quick
  if has_command clang++; then
    run cmake --preset dev-clang-debug
    run cmake --build --preset dev-clang-debug
    run ctest --preset dev-clang-debug --output-on-failure
  else
    printf '\n==> clang++ not found; skip dev-clang-debug preset.\n'
  fi
}

run_python_checks() {
  activate_venv_if_present
  run "${PYTHON_BIN}" -m pytest
  run "${PYTHON_BIN}" -m ruff check python tests/python
  run "${PYTHON_BIN}" -m black --check python tests/python
  run "${PYTHON_BIN}" -m mypy python tests/python
}

run_local_sim_env_check() {
  activate_venv_if_present

  if [[ -f scripts/check_local_sim_env.py ]]; then
    run "${PYTHON_BIN}" scripts/check_local_sim_env.py
  else
    printf '\n==> scripts/check_local_sim_env.py not found; skip local simulation environment check.\n'
  fi
}

run_local_sim_env_check_optional() {
  activate_venv_if_present

  if [[ -f scripts/check_local_sim_env.py ]]; then
    printf '\n==> %s scripts/check_local_sim_env.py (optional in quick mode)\n' "${PYTHON_BIN}"
    "${PYTHON_BIN}" scripts/check_local_sim_env.py || {
      printf '\n==> local simulation environment is not ready; continue quick checks.\n'
    }
  else
    printf '\n==> scripts/check_local_sim_env.py not found; skip local simulation environment check.\n'
  fi
}

run_local_sim_smoke() {
  activate_venv_if_present

  if [[ -f scripts/run_local_sim_demo.py ]]; then
    run "${PYTHON_BIN}" scripts/run_local_sim_demo.py --profile headless_fast --seconds 3
  else
    printf '\n==> scripts/run_local_sim_demo.py not found; skip local simulation smoke demo.\n'
  fi
}

run_format_check() {
  if has_command clang-format; then
    run bash -lc "${cpp_files_expr} | xargs -0 clang-format --dry-run --Werror"
  else
    printf '\n==> clang-format not found; skip C++ format check.\n'
  fi
}

run_tidy() {
  if has_command clang-tidy && [[ -d build/dev-clang-debug ]]; then
    run bash -lc "find apps src tests/cpp -name '*.cpp' -print0 | xargs -0 clang-tidy -p build/dev-clang-debug"
  else
    printf '\n==> clang-tidy or build/dev-clang-debug not available; skip clang-tidy.\n'
  fi
}

print_usage() {
  cat >&2 <<'USAGE'
Usage: scripts/check_all.sh [mode]

Modes:
  --quick       C++ gcc build/test, Python tests/lint/typecheck, optional local-sim environment report.
  --full        --quick plus clang build/test when available, format check, required local-sim check and headless smoke demo.
  --tidy        --full plus clang-tidy when available.
  --tidy-fix    Format first, then run --tidy checks.
  --format      Format C++ and Python sources in place.
  --fix-format  Alias of --format.
  --cpp-only    Run only C++ gcc build/test.
  --python-only Run only Python tests/lint/typecheck.
  --local-sim   Run required local-sim environment check and headless smoke demo.
USAGE
}

case "${MODE}" in
  --format|--fix-format)
    run_cpp_format
    run_python_format
    ;;
  --quick)
    run_cpp_quick
    run_python_checks
    run_local_sim_env_check_optional
    ;;
  --full)
    run_cpp_full
    run_python_checks
    run_format_check
    run_local_sim_env_check
    run_local_sim_smoke
    ;;
  --tidy)
    run_cpp_full
    run_python_checks
    run_format_check
    run_local_sim_env_check
    run_local_sim_smoke
    run_tidy
    ;;
  --tidy-fix)
    run_cpp_format
    run_python_format
    run_cpp_full
    run_python_checks
    run_format_check
    run_local_sim_env_check
    run_local_sim_smoke
    run_tidy
    ;;
  --cpp-only)
    run_cpp_quick
    ;;
  --python-only)
    run_python_checks
    ;;
  --local-sim)
    run_local_sim_env_check
    run_local_sim_smoke
    ;;
  -h|--help)
    print_usage
    exit 0
    ;;
  *)
    print_usage
    exit 2
    ;;
esac

printf '\nAll requested checks passed.\n'