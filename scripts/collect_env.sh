#!/usr/bin/env bash
set -u

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
REPORT_DIR="${REPO_ROOT}/reports/env"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
REPORT_PATH="${REPORT_DIR}/env_report_${TIMESTAMP}.txt"

mkdir -p "${REPORT_DIR}"

run_cmd() {
  local cmd="$1"
  {
    printf "\n$ %s\n" "${cmd}"
    bash -lc "${cmd}"
  } >>"${REPORT_PATH}" 2>&1 || true
}

run_python() {
  local code="$1"
  {
    printf "\n$ python3 - <<'PY'\n%s\nPY\n" "${code}"
    python3 -c "${code}"
  } >>"${REPORT_PATH}" 2>&1 || true
}

section() {
  local title="$1"
  {
    printf "\n\n================================================================================\n"
    printf "%s\n" "${title}"
    printf "================================================================================\n"
  } >>"${REPORT_PATH}"
}

{
  printf "QRICS Environment Report\n"
  printf "Generated at: %s\n" "$(date --iso-8601=seconds)"
  printf "Repository root: %s\n" "${REPO_ROOT}"
  printf "User: %s\n" "$(whoami)"
  printf "Shell: %s\n" "${SHELL:-unknown}"
} >"${REPORT_PATH}"

section "1. Operating System"
run_cmd "uname -a"
run_cmd "cat /etc/os-release"
run_cmd "command -v lsb_release >/dev/null 2>&1 && lsb_release -a || true"

section "2. CPU / Memory / Disk"
run_cmd "lscpu | sed -n '1,30p'"
run_cmd "free -h"
run_cmd "df -h ."
run_cmd "command -v lsblk >/dev/null 2>&1 && lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | sed -n '1,40p' || true"

section "3. GPU / NVIDIA / CUDA"
run_cmd "command -v lspci >/dev/null 2>&1 && lspci | grep -Ei 'vga|3d|display|nvidia|amd|intel' || true"
run_cmd "nvidia-smi"
run_cmd "nvcc --version"
run_cmd "ls -ld /usr/local/cuda* 2>/dev/null || true"
run_cmd "lsmod | grep -E 'nvidia|nouveau' || true"

section "4. Core Development Tools"
run_cmd "git --version"
run_cmd "gcc --version"
run_cmd "g++ --version"
run_cmd "clang --version"
run_cmd "clang++ --version"
run_cmd "clang-format --version"
run_cmd "clang-tidy --version"
run_cmd "cmake --version"
run_cmd "make --version"
run_cmd "ninja --version"
run_cmd "pkg-config --version"
run_cmd "ccache --version"
run_cmd "gdb --version | head -n 1"
run_cmd "valgrind --version"

section "5. Python"
run_cmd "python3 --version"
run_cmd "python --version"
run_cmd "command -v python3 || true; command -v python || true"
run_cmd "python3 -m pip --version 2>/dev/null || true"

run_python $'import importlib.util\nprint("venv:", "OK" if importlib.util.find_spec("venv") else "MISSING")\nprint("ensurepip:", "OK" if importlib.util.find_spec("ensurepip") else "MISSING")'

run_python $'mods = ["numpy", "torch", "pybind11", "pytest", "ruff", "black", "mypy"]\nfor m in mods:\n    try:\n        mod = __import__(m)\n        version = getattr(mod, "__version__", "installed")\n        print(f"{m}: {version}")\n    except Exception as exc:\n        print(f"{m}: NOT FOUND ({exc.__class__.__name__})")'

run_python $'try:\n    import torch\n    print("torch:", torch.__version__)\n    print("torch.cuda.is_available:", torch.cuda.is_available())\n    print("torch.version.cuda:", torch.version.cuda)\n    print("cuda.device_count:", torch.cuda.device_count())\n    if torch.cuda.is_available():\n        for i in range(torch.cuda.device_count()):\n            print(f"cuda.device[{i}]:", torch.cuda.get_device_name(i))\nexcept Exception as exc:\n    print("torch check failed:", repr(exc))'

section "6. Conda / Mamba / uv"
run_cmd "conda --version"
run_cmd "mamba --version"
run_cmd "uv --version"
run_cmd "command -v conda >/dev/null 2>&1 && conda env list || true"
run_cmd "command -v uv >/dev/null 2>&1 && uv python list 2>/dev/null | sed -n '1,40p' || true"

section "7. Docker / Container Tools"
run_cmd "docker --version"
run_cmd "command -v docker >/dev/null 2>&1 && docker info | sed -n '1,80p' || true"
run_cmd "docker compose version"
run_cmd "podman --version"
run_cmd "nvidia-container-cli --version"

section "8. Isaac / Omniverse Hints"
run_cmd "find \$HOME -maxdepth 4 \\( -iname '*isaac*' -o -iname '*omniverse*' \\) -type d 2>/dev/null | sed -n '1,80p'"
run_python $'mods = ["isaaclab", "isaacsim", "omni", "carb"]\nfor m in mods:\n    try:\n        __import__(m)\n        print(f"{m}: installed/importable")\n    except Exception as exc:\n        print(f"{m}: NOT FOUND ({exc.__class__.__name__})")'

section "9. Repository / Git Status"
run_cmd "git -C '${REPO_ROOT}' rev-parse --show-toplevel 2>/dev/null || true"
run_cmd "git -C '${REPO_ROOT}' remote -v 2>/dev/null || true"
run_cmd "git -C '${REPO_ROOT}' branch --show-current 2>/dev/null || true"
run_cmd "git -C '${REPO_ROOT}' status --short 2>/dev/null || true"

section "10. Network Basics"
run_cmd "getent hosts github.com || true"
run_python $'import ssl, sys\nprint("python:", sys.version.replace("\\n", " "))\nprint("openssl:", ssl.OPENSSL_VERSION)'

section "11. Environment Variables of Interest"
run_cmd "env | grep -E '^(PATH|LD_LIBRARY_PATH|CUDA_HOME|CUDA_PATH|CONDA_PREFIX|VIRTUAL_ENV|PYTHONPATH|CC|CXX)=' | sort || true"

section "12. Report Notes"
{
  printf "This report is read-only. It records system, compiler, Python, GPU, Docker, Isaac and Git state at collection time.\n"
} >>"${REPORT_PATH}"

printf "Environment report generated:\n%s\n" "${REPORT_PATH}"
printf "Inspect it with:\ncat \"%s\"\n" "${REPORT_PATH}"
