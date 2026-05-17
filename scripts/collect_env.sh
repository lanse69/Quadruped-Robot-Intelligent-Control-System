#!/usr/bin/env bash
# Collect development environment information for QRICS.
# This script is read-only: it does not install packages or modify system config.

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/reports/env"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_FILE="${REPORT_DIR}/env_report_${TIMESTAMP}.txt"

mkdir -p "${REPORT_DIR}"

section() {
  printf '

================================================================================
' | tee -a "${REPORT_FILE}" >/dev/null
  printf '%s
' "$1" | tee -a "${REPORT_FILE}" >/dev/null
  printf '================================================================================
' | tee -a "${REPORT_FILE}" >/dev/null
}

run_cmd() {
  local title="$1"
  shift
  printf '
$ %s
' "$*" | tee -a "${REPORT_FILE}" >/dev/null
  if command -v "$1" >/dev/null 2>&1; then
    "$@" >>"${REPORT_FILE}" 2>&1 || true
  else
    printf 'NOT FOUND: %s
' "$1" >>"${REPORT_FILE}"
  fi
}

run_shell() {
  local title="$1"
  local cmd="$2"
  local expanded_cmd
  expanded_cmd="$(printf '%b' "${cmd}")"
  printf '
$ %s
' "${expanded_cmd}" | tee -a "${REPORT_FILE}" >/dev/null
  bash -lc "${expanded_cmd}" >>"${REPORT_FILE}" 2>&1 || true
}

{
  echo "QRICS Environment Report"
  echo "Generated at: $(date -Is)"
  echo "Repository root: ${ROOT_DIR}"
  echo "User: ${USER:-unknown}"
  echo "Shell: ${SHELL:-unknown}"
} >"${REPORT_FILE}"

section "1. Operating System"
run_cmd "uname" uname -a
if [ -f /etc/os-release ]; then
  printf '
$ cat /etc/os-release
' >>"${REPORT_FILE}"
  cat /etc/os-release >>"${REPORT_FILE}" 2>&1 || true
fi
run_shell "lsb_release" "command -v lsb_release >/dev/null 2>&1 && lsb_release -a || true"

section "2. CPU / Memory / Disk"
run_shell "cpu" "lscpu | sed -n '1,30p'"
run_cmd "memory" free -h
run_cmd "disk" df -h .
run_shell "block devices" "command -v lsblk >/dev/null 2>&1 && lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | sed -n '1,40p' || true"

section "3. GPU / NVIDIA / CUDA"
run_shell "pci gpu" "command -v lspci >/dev/null 2>&1 && lspci | grep -Ei 'vga|3d|display|nvidia|amd|intel' || true"
run_cmd "nvidia-smi" nvidia-smi
run_cmd "nvcc" nvcc --version
run_shell "cuda paths" "ls -ld /usr/local/cuda* 2>/dev/null || true"
run_shell "nvidia driver modules" "lsmod | grep -E 'nvidia|nouveau' || true"

section "4. Core Development Tools"
run_cmd "git" git --version
run_cmd "gcc" gcc --version
run_cmd "g++" g++ --version
run_cmd "clang" clang --version
run_cmd "clang++" clang++ --version
run_cmd "cmake" cmake --version
run_cmd "make" make --version
run_cmd "ninja" ninja --version
run_cmd "pkg-config" pkg-config --version
run_cmd "ccache" ccache --version

section "5. Python"
run_cmd "python3" python3 --version
run_cmd "python" python --version
run_shell "python executable" "command -v python3 || true; command -v python || true"
run_shell "pip" "python3 -m pip --version 2>/dev/null || true"
run_shell "venv module" "python3 - <<'PY'
import importlib.util
print('venv:', 'OK' if importlib.util.find_spec('venv') else 'MISSING')
print('ensurepip:', 'OK' if importlib.util.find_spec('ensurepip') else 'MISSING')
PY"
run_shell "python packages" "python3 - <<'PY'
mods = ['numpy', 'torch', 'pybind11', 'pytest', 'ruff', 'black', 'mypy']
for m in mods:
    try:
        mod = __import__(m)
        print(f'{m}: {getattr(mod, "__version__", "installed")}')
    except Exception as exc:
        print(f'{m}: NOT FOUND ({exc.__class__.__name__})')
PY"
run_shell "torch cuda" "python3 - <<'PY'
try:
    import torch
    print('torch:', torch.__version__)
    print('torch.cuda.is_available:', torch.cuda.is_available())
    print('torch.version.cuda:', torch.version.cuda)
    print('cuda.device_count:', torch.cuda.device_count())
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            print(f'cuda.device[{i}]:', torch.cuda.get_device_name(i))
except Exception as exc:
    print('torch check failed:', repr(exc))
PY"

section "6. Conda / Mamba / uv"
run_cmd "conda" conda --version
run_cmd "mamba" mamba --version
run_cmd "uv" uv --version
run_shell "conda envs" "command -v conda >/dev/null 2>&1 && conda env list || true"
run_shell "uv python list" "command -v uv >/dev/null 2>&1 && uv python list 2>/dev/null | sed -n '1,40p' || true"

section "7. Docker / Container Tools"
run_cmd "docker" docker --version
run_shell "docker info" "command -v docker >/dev/null 2>&1 && docker info | sed -n '1,80p' || true"
run_cmd "docker compose" docker compose version
run_cmd "podman" podman --version
run_cmd "nvidia-container-cli" nvidia-container-cli --version

section "8. Isaac / Omniverse Hints"
run_shell "isaac common dirs" "find \$HOME -maxdepth 4 \( -iname '*isaac*' -o -iname '*omniverse*' \) -type d 2>/dev/null | sed -n '1,80p'"
run_shell "isaac python packages" "python3 - <<'PY'
mods = ['isaaclab', 'isaacsim', 'omni', 'carb']
for m in mods:
    try:
        __import__(m)
        print(f'{m}: installed/importable')
    except Exception as exc:
        print(f'{m}: NOT FOUND ({exc.__class__.__name__})')
PY"

section "9. Repository / Git Status"
run_shell "git root" "git -C '${ROOT_DIR}' rev-parse --show-toplevel 2>/dev/null || true"
run_shell "git remotes" "git -C '${ROOT_DIR}' remote -v 2>/dev/null || true"
run_shell "git branch" "git -C '${ROOT_DIR}' branch --show-current 2>/dev/null || true"
run_shell "git status" "git -C '${ROOT_DIR}' status --short 2>/dev/null || true"

section "10. Network Basics"
run_shell "github dns" "getent hosts github.com || true"
run_shell "python ssl" "python3 - <<'PY'
import ssl, sys
print('python:', sys.version.replace('\n', ' '))
print('openssl:', ssl.OPENSSL_VERSION)
PY"

section "11. Environment Variables of Interest"
run_shell "env filtered" "env | grep -E '^(PATH|LD_LIBRARY_PATH|CUDA_HOME|CUDA_PATH|CONDA_PREFIX|VIRTUAL_ENV|PYTHONPATH|CC|CXX)=' | sort || true"

section "12. Report Notes"
cat >>"${REPORT_FILE}" <<'REPORT_END'
This report is read-only. It records system, compiler, Python, GPU, Docker, Isaac and Git state at collection time.
REPORT_END

printf 'Environment report generated:
%s
' "${REPORT_FILE}"
printf 'Inspect it with:
cat "%s"
' "${REPORT_FILE}"
