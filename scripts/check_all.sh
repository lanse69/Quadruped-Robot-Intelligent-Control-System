#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---quick}"

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

cpp_files_expr="find include src apps tests/cpp \( -name '*.hpp' -o -name '*.cpp' \) -print0"

run_cpp_format() {
  if has_command clang-format; then
    run bash -lc "${cpp_files_expr} | xargs -0 clang-format -i"
  else
    printf '\n==> clang-format not found; cannot format C++ files.\n' >&2
    exit 1
  fi
}

run_cpp_quick() {
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
  if [[ -d .venv ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
  fi

  run pytest
  run ruff check python tests/python
  run black --check python tests/python
  run mypy python tests/python
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

case "${MODE}" in
  --format|--fix-format)
    run_cpp_format
    ;;
  --quick)
    run_cpp_quick
    run_python_checks
    ;;
  --full)
    run_cpp_full
    run_python_checks
    run_format_check
    ;;
  --tidy)
    run_cpp_full
    run_python_checks
    run_format_check
    run_tidy
    ;;
  --tidy-fix)
    run_cpp_format
    run_cpp_full
    run_python_checks
    run_format_check
    run_tidy
    ;;
  *)
    echo "Usage: $0 [--format|--fix-format|--quick|--full|--tidy|--tidy-fix]" >&2
    exit 2
    ;;
esac

printf '\nAll requested checks passed.\n'