#!/usr/bin/env bash
#
# Enhanced installation script for RAG Vision Chatbot
#
# Features:
#   - Detailed step-by-step error handling
#   - System requirements checks (Python, disk space, GPU)
#   - Resume support (skip completed steps)
#   - --force and --skip flags for fine-grained control
#   - Alternative RAG model selection
#   - Post-install health checks
#
set -euo pipefail

umask 077

# ─── Constants ────────────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
ENV_FILE="${ROOT_DIR}/.env"
ENV_EXAMPLE="${ROOT_DIR}/.env.example"
PROXIES_EXAMPLE="${ROOT_DIR}/proxies.example.txt"
PROXIES_FILE="${ROOT_DIR}/proxies.txt"
MODEL_DIR="${ROOT_DIR}/models"
RAG_MODEL_DIR="${MODEL_DIR}/rag/bge-m3"
RAG_MODEL_REPO="BAAI/bge-m3"
PYTHON_BIN=""

# ─── Logging ──────────────────────────────────────────────────────────────────

INSTALL_LOG="${ROOT_DIR}/install.log"
STEPS_DONE="${ROOT_DIR}/.install_steps"

log_with_ts() {
  local level="$1"
  shift
  printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${level}" "$*" | tee -a "${INSTALL_LOG}"
}

info()    { log_with_ts "INFO" "$*"; }
warn()    { log_with_ts "WARN" "$*" >&2; }
error()   { log_with_ts "ERROR" "$*" >&2; }
step()    { log_with_ts "STEP" "[$1] $2"; }

die() {
  error "$*"
  exit 1
}

# ─── Step Tracking ─────────────────────────────────────────────────────────────

mark_step_done() {
  printf '%s\n' "$1" >> "${STEPS_DONE}"
}

is_step_done() {
  grep -qxF "$1" "${STEPS_DONE}" 2>/dev/null
}

clear_steps() {
  rm -f "${STEPS_DONE}"
}

# ─── CLI Flags ─────────────────────────────────────────────────────────────────

FORCE_REINSTALL=false
SKIP_MODEL=false
SKIP_OCR=false
SKIP_DEPS=false
RESUME=false

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force)
        FORCE_REINSTALL=true
        shift
        ;;
      --skip-model)
        SKIP_MODEL=true
        shift
        ;;
      --skip-ocr)
        SKIP_OCR=true
        shift
        ;;
      --skip-deps)
        SKIP_DEPS=true
        shift
        ;;
      --resume)
        RESUME=true
        shift
        ;;
      --help|-h)
        show_help
        exit 0
        ;;
      *)
        die "Unknown option: $1. Use --help for usage."
        ;;
    esac
  done
}

show_help() {
  cat <<'EOF'
Usage: install.sh [OPTIONS]

Options:
  --force        Force reinstallation even if components exist
  --skip-model   Skip RAG model download
  --skip-ocr     Skip OCR engine installation
  --skip-deps    Skip dependency installation
  --resume       Resume from last incomplete step
  --help, -h     Show this help message

Environment variables (for non-interactive/CI usage):
  INSTALL_SKIP_PROMPTS=1     Skip all prompts, use defaults or env values
  INSTALL_PROFILE=Low|Medium|High
  INSTALL_ACCELERATOR=CUDA|CPU
  INSTALL_RAG_MODEL=BAAI/bge-m3|ollama|none
  DEEPSEEK_API_KEY=<key>
  OPENROUTER_API_KEY=<key>
EOF
}

# ─── System Requirements Check ─────────────────────────────────────────────────

check_python_version() {
  step "SYS_CHECK" "Checking Python version..."
  local version
  version=$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  local major minor
  major=$(echo "${version}" | cut -d. -f1)
  minor=$(echo "${version}" | cut -d. -f2)

  if [[ "${major}" -lt 3 ]] || { [[ "${major}" -eq 3 ]] && [[ "${minor}" -lt 9 ]]; }; then
    die "Python 3.9+ required, but found Python ${major}.${minor}"
  fi
  info "Python version: ${major}.${minor} (OK)"
}

check_disk_space() {
  step "SYS_CHECK" "Checking available disk space..."
  local required_mb=5000
  local available_mb
  available_mb=$(df -m "${ROOT_DIR}" 2>/dev/null | awk 'NR==2 {print $4}')

  if [[ -z "${available_mb}" ]]; then
    warn "Could not determine disk space, proceeding anyway..."
    return
  fi

  if [[ "${available_mb}" -lt "${required_mb}" ]]; then
    die "Insufficient disk space. Required: ${required_mb}MB, Available: ${available_mb}MB"
  fi
  info "Disk space: ${available_mb}MB available (OK)"
}

check_gpu() {
  step "SYS_CHECK" "Checking GPU availability..."
  if command -v nvidia-smi >/dev/null 2>&1; then
    if nvidia-smi >/dev/null 2>&1; then
      local gpu_name
      gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
      info "NVIDIA GPU detected: ${gpu_name}"
      return 0
    fi
  fi
  info "No NVIDIA GPU found (CPU mode will be used)"
  return 1
}

check_dependencies() {
  step "SYS_CHECK" "Checking system dependencies..."

  local missing_deps=()

  for cmd in curl pip git; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
      missing_deps+=("${cmd}")
    fi
  done

  if [[ ${#missing_deps[@]} -gt 0 ]]; then
    die "Missing required commands: ${missing_deps[*]}. Please install them first."
  fi
  info "System dependencies: OK"
}

# ─── Init ─────────────────────────────────────────────────────────────────────

init_log() {
  mkdir -p "$(dirname "${INSTALL_LOG}")"
  touch "${INSTALL_LOG}"
  info "=== Installation started ==="
  info "Root directory: ${ROOT_DIR}"
}

require_linux() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    die "This installer is supported on Linux only."
  fi
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
    return
  fi
  die "python3 is required but was not found."
}

# ─── Interactive Prompts ───────────────────────────────────────────────────────

prompt_choice() {
  local prompt_text="$1"
  shift
  local -a choices=("$@")
  local selection=""

  while [[ -z "${selection}" ]]; do
    printf '\n%s\n' "${prompt_text}" >&2
    local i=1
    for choice in "${choices[@]}"; do
      printf '  %s) %s\n' "${i}" "${choice}" >&2
      i=$((i + 1))
    done
    read -r -p "> " selection
    if [[ "${selection}" =~ ^[0-9]+$ ]] && [[ "${selection}" -ge 1 ]] && [[ "${selection}" -le ${#choices[@]} ]]; then
      printf '%s\n' "${choices[$((selection - 1))]}"
      return
    fi
    selection=""
    warn "Invalid choice, try again."
  done
}

prompt_yes_no() {
  local prompt_text="$1"
  local default_value="${2:-y}"
  local suffix="[Y/n]"
  if [[ "${default_value}" == "n" ]]; then
    suffix="[y/N]"
  fi

  while true; do
    read -r -p "${prompt_text} ${suffix} " answer
    answer="${answer:-${default_value}}"
    case "${answer}" in
      y|Y|yes|YES) printf 'yes\n'; return ;;
      n|N|no|NO) printf 'no\n'; return ;;
    esac
    warn "Please answer yes or no."
  done
}

prompt_text() {
  local prompt_text="$1"
  local default_value="${2:-}"
  local answer=""
  if [[ -n "${default_value}" ]]; then
    read -r -p "${prompt_text} [${default_value}] " answer
    printf '%s\n' "${answer:-${default_value}}"
    return
  fi
  read -r -p "${prompt_text} " answer
  printf '%s\n' "${answer}"
}

# ─── RAG Model Selection ───────────────────────────────────────────────────────

RAG_MODEL_OPTIONS=(
  "BAAI/bge-m3 (default, high quality)"
  "ollama (local, using ollama server)"
  "none (skip RAG installation)"
)

prompt_rag_model() {
  if [[ "${INSTALL_SKIP_PROMPTS:-}" == "1" ]] && [[ -n "${INSTALL_RAG_MODEL:-}" ]]; then
    printf '%s\n' "${INSTALL_RAG_MODEL}"
    return
  fi

  prompt_choice "Select RAG embedding model:" "${RAG_MODEL_OPTIONS[@]}"
}

resolve_rag_model() {
  local selection="$1"
  case "${selection}" in
    *"ollama"*)
      printf 'ollama\n'
      ;;
    *"none"*)
      printf 'none\n'
      ;;
    *)
      printf 'BAAI/bge-m3\n'
      ;;
  esac
}

# ─── Environment Configuration ─────────────────────────────────────────────────

write_env() {
  local env_file_path="$1"
  shift

  if [[ ! -f "${ENV_EXAMPLE}" ]]; then
    die ".env.example was not found at ${ENV_EXAMPLE}"
  fi

  # Backup existing .env if --force and file exists
  if [[ "${FORCE_REINSTALL}" == "true" ]] && [[ -f "${env_file_path}" ]]; then
    local backup="${env_file_path}.backup.$(date '+%Y%m%d_%H%M%S')"
    cp "${env_file_path}" "${backup}"
    info "Backed up existing .env to ${backup}"
  fi

  if [[ ! -f "${env_file_path}" ]]; then
    cp "${ENV_EXAMPLE}" "${env_file_path}"
  fi

  "${PYTHON_BIN}" - "$env_file_path" "$@" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
updates = {}
for item in sys.argv[2:]:
    key, value = item.split("=", 1)
    updates[key] = value

lines = path.read_text().splitlines()
used = set()
output = []
pattern_cache = {}

for line in lines:
    replaced = False
    for key, value in updates.items():
        pattern = pattern_cache.get(key)
        if pattern is None:
            pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}=.*$")
            pattern_cache[key] = pattern
        if pattern.match(line):
            output.append(f"{key}={value}")
            used.add(key)
            replaced = True
            break
    if not replaced:
        output.append(line)

for key, value in updates.items():
    if key not in used:
        output.append(f"{key}={value}")

path.write_text("\n".join(output) + "\n")
PY
}

ensure_proxies() {
  if [[ -f "${PROXIES_FILE}" ]]; then
    return
  fi
  if [[ -f "${PROXIES_EXAMPLE}" ]]; then
    cp "${PROXIES_EXAMPLE}" "${PROXIES_FILE}"
  fi
}

# ─── Venv & Dependencies ────────────────────────────────────────────────────────

ensure_venv() {
  if is_step_done "VENV" && [[ "${FORCE_REINSTALL}" != "true" ]]; then
    info "Virtual environment already exists, skipping creation."
    return
  fi

  step "VENV" "Creating virtual environment at ${VENV_DIR}"
  if [[ ! -d "${VENV_DIR}" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
  mark_step_done "VENV"
}

install_requirements() {
  if is_step_done "DEPS" && [[ "${FORCE_REINSTALL}" != "true" ]] && [[ "${SKIP_DEPS}" != "true" ]]; then
    info "Dependencies already installed, skipping."
    return
  fi

  if [[ "${SKIP_DEPS}" == "true" ]]; then
    info "Skipping dependency installation (--skip-deps)."
    return
  fi

  step "DEPS" "Installing dependencies"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip

  install_requirements_file "${ROOT_DIR}/requirements.txt"

  if [[ "${RAG_ENABLED_VALUE}" == "true" ]]; then
    install_requirements_file "${ROOT_DIR}/requirements-rag.txt"
  fi

  if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
    if [[ "${OCR_PROVIDER_VALUE}" == "paddleocr" ]]; then
      install_paddle_runtime
      install_requirements_file "${ROOT_DIR}/requirements-ocr-paddle.txt"
    else
      install_requirements_file "${ROOT_DIR}/requirements-ocr-easy.txt"
    fi
  fi

  if [[ "${YOUTUBE_TRANSCRIPTS_VALUE}" == "true" ]]; then
    install_requirements_file "${ROOT_DIR}/requirements-youtube-transcript.txt"
  fi

  mark_step_done "DEPS"
}

install_requirements_file() {
  local requirements_file="$1"
  if [[ ! -f "${requirements_file}" ]]; then
    error "Missing requirements file: ${requirements_file}"
    die "Required file not found: ${requirements_file}"
  fi
  info "Installing $(basename "${requirements_file}")"
  if ! "${VENV_DIR}/bin/python" -m pip install -r "${requirements_file}"; then
    error "Failed to install requirements from: ${requirements_file}"
    die "Dependency installation failed. Check ${INSTALL_LOG} for details."
  fi
}

install_paddle_runtime() {
  step "PADDLE" "Installing PaddlePaddle runtime"
  if [[ "${ACCELERATOR}" == "CUDA" ]]; then
    info "Installing PaddlePaddle 3.2.2 with CUDA support"
    if ! "${VENV_DIR}/bin/python" -m pip install paddlepaddle==3.2.2 2>&1 | tee -a "${INSTALL_LOG}"; then
      warn "Automatic PaddlePaddle CUDA installation failed."
      warn "You may need to install a CUDA-specific wheel manually. See README.md"
    fi
  else
    info "Installing PaddlePaddle 3.2.2 (CPU)"
    if ! "${VENV_DIR}/bin/python" -m pip install paddlepaddle==3.2.2 2>&1 | tee -a "${INSTALL_LOG}"; then
      error "Failed to install PaddlePaddle"
      die "PaddlePaddle installation failed. Try installing manually or use EasyOCR instead."
    fi
  fi
}

# ─── Model Download ─────────────────────────────────────────────────────────────

download_model_snapshot() {
  local repo_id="$1"
  local target_dir="$2"
  local description="$3"

  mkdir -p "$(dirname "${target_dir}")"
  step "MODEL" "Downloading ${description} into ${target_dir}"

  "${VENV_DIR}/bin/python" - "${repo_id}" "${target_dir}" <<'PY'
from huggingface_hub import snapshot_download
import sys

repo_id = sys.argv[1]
target_dir = sys.argv[2]

try:
    snapshot_download(
        repo_id=repo_id,
        local_dir=target_dir,
        local_dir_use_symlinks=False,
    )
except Exception as exc:
    raise SystemExit(f"Failed to download {repo_id} into {target_dir}: {exc}") from exc
PY

  if [[ $? -ne 0 ]]; then
    error "Model download failed: ${description}"
    die "Failed to download ${repo_id}. Check ${INSTALL_LOG} for details."
  fi
  info "Successfully downloaded ${description}"
}

# ─── OCR Preload ───────────────────────────────────────────────────────────────

preload_ocr_assets() {
  if is_step_done "OCR_PRELOAD" && [[ "${FORCE_REINSTALL}" != "true" ]]; then
    info "OCR assets already preloaded, skipping."
    return
  fi

  if [[ "${SKIP_OCR}" == "true" ]]; then
    info "Skipping OCR preload (--skip-ocr)."
    return
  fi

  step "OCR_PRELOAD" "Preloading OCR engine assets"
  local ocr_output
  ocr_output=$("${VENV_DIR}/bin/python" - <<'PYEOF'
from types import SimpleNamespace

try:
    from ocr_service import preload_ocr_engine
    preload_ocr_engine(SimpleNamespace(debug=False))
    print("OCR_PRELOAD_SUCCESS")
except Exception as exc:
    print("OCR_PRELOAD_FAILED: {}".format(exc), file=__import__('sys').stderr)
    raise
PYEOF
)
  echo "${ocr_output}" | tee -a "${INSTALL_LOG}"
  if ! echo "${ocr_output}" | grep -q "OCR_PRELOAD_SUCCESS"; then
    warn "OCR preload encountered an issue. OCR may still work but could benefit from a manual preload."
  fi
  mark_step_done "OCR_PRELOAD"
}

# ─── Health Checks ─────────────────────────────────────────────────────────────

run_health_checks() {
  step "HEALTH" "Running post-installation health checks"

  local failed=0

  info "Checking Python imports..."
  check_import "flask" || failed=$((failed + 1))
  check_import "chromadb" || failed=$((failed + 1))
  check_import "numpy" || failed=$((failed + 1))

  if [[ "${RAG_ENABLED_VALUE}" == "true" ]]; then
    info "Checking RAG components..."
    check_import "rag" || failed=$((failed + 1))
    check_import "rag_service" || failed=$((failed + 1))
    check_import "sentence_transformers" || failed=$((failed + 1))
  fi

  if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
    info "Checking OCR components..."
    if [[ "${OCR_PROVIDER_VALUE}" == "paddleocr" ]]; then
      check_import "paddleocr" || failed=$((failed + 1))
      check_import "paddle" || failed=$((failed + 1))
    else
      check_import "easyocr" || failed=$((failed + 1))
    fi
    check_import "PIL" || failed=$((failed + 1))
  fi

  info "Checking environment configuration..."
  if [[ -f "${ENV_FILE}" ]]; then
    if grep -q "DEEPSEEK_API_KEY=your-deepseek" "${ENV_FILE}" 2>/dev/null; then
      warn "DEEPSEEK_API_KEY is still set to placeholder value in .env"
    fi
  else
    error ".env file not found!"
    failed=$((failed + 1))
  fi

  if [[ ${failed} -gt 0 ]]; then
    warn "Health checks completed with ${failed} warning(s). Review above for details."
    return 1
  fi

  info "All health checks passed!"
  return 0
}

check_import() {
  local module="$1"
  if "${VENV_DIR}/bin/python" -c "import ${module}" 2>/dev/null; then
    info "  [OK] ${module}"
    return 0
  else
    warn "  [FAIL] ${module} - import failed"
    return 1
  fi
}

# ─── CUDA Helper ───────────────────────────────────────────────────────────────

cuda_available() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi >/dev/null 2>&1 && return 0
  fi
  return 1
}

# ─── Main Flow ────────────────────────────────────────────────────────────────

main() {
  parse_args "$@"

  init_log
  require_linux
  find_python

  info "Running system requirements checks..."
  check_python_version
  check_disk_space
  check_dependencies

  if cuda_available; then
    check_gpu
  fi

  # ── Interactive Configuration ───────────────────────────────────────────────

  if [[ "${INSTALL_SKIP_PROMPTS:-}" != "1" ]]; then
    info "Starting interactive configuration..."
    info "Select system profile"
    PROFILE="$(prompt_choice "Choose a profile:" "Low" "Medium" "High")"
    info "Selected profile: ${PROFILE}"

    info "Select accelerator"
    ACCELERATOR="$(prompt_choice "Choose an accelerator:" "CUDA" "CPU")"
    info "Selected accelerator: ${ACCELERATOR}"

    IMAGE_STACK="$(prompt_choice "Choose an image processing stack:" "None" "OCR only")"
    info "Selected image processing stack: ${IMAGE_STACK}"

    if [[ "${ACCELERATOR}" == "CUDA" ]] && ! cuda_available; then
      warn "CUDA was selected, but no NVIDIA runtime was detected."
      answer="$(prompt_yes_no "Continue in CPU mode instead?" "y")"
      if [[ "${answer}" == "yes" ]]; then
        ACCELERATOR="CPU"
      else
        die "CUDA setup is required for the selected mode."
      fi
    fi

    # ── API Keys ───────────────────────────────────────────────────────────────

    DEEPSEEK_API_KEY="$(prompt_text "Enter your DeepSeek API key (leave blank to skip):")"
    OPENROUTER_API_KEY="$(prompt_text "Enter your OpenRouter API key (leave blank to skip):")"
    if [[ -z "${DEEPSEEK_API_KEY}" && -z "${OPENROUTER_API_KEY}" ]]; then
      die "At least one provider API key is required."
    fi

    OPENROUTER_HTTP_REFERER=""
    OPENROUTER_APP_TITLE=""
    if [[ -n "${OPENROUTER_API_KEY}" ]]; then
      OPENROUTER_HTTP_REFERER="$(prompt_text "Optional OpenRouter HTTP Referer header:")"
      OPENROUTER_APP_TITLE="$(prompt_text "Optional OpenRouter app title:")"
    fi

    # ── RAG Model Selection ─────────────────────────────────────────────────────

    RAG_MODEL_SELECTION="$(prompt_rag_model)"
    RAG_MODEL_VALUE="$(resolve_rag_model "${RAG_MODEL_SELECTION}")"

  else
    # Non-interactive mode via environment variables
    info "Running in non-interactive mode (INSTALL_SKIP_PROMPTS=1)"

    PROFILE="${INSTALL_PROFILE:-Medium}"
    ACCELERATOR="${INSTALL_ACCELERATOR:-CPU}"
    DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
    OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
    OPENROUTER_HTTP_REFERER="${OPENROUTER_HTTP_REFERER:-}"
    OPENROUTER_APP_TITLE="${OPENROUTER_APP_TITLE:-}"
    RAG_MODEL_VALUE="${INSTALL_RAG_MODEL:-BAAI/bge-m3}"
    IMAGE_STACK="${INSTALL_IMAGE_STACK:-OCR only}"

    [[ -z "${DEEPSEEK_API_KEY}" && -z "${OPENROUTER_API_KEY}" ]] && \
      die "At least one API key is required. Set DEEPSEEK_API_KEY or OPENROUTER_API_KEY"
  fi

  # ── Profile-Based Configuration ───────────────────────────────────────────────

  RAG_ENABLED_VALUE="false"
  OCR_ENABLED_VALUE="false"
  OCR_PROVIDER_VALUE="paddleocr"
  OCR_PRELOAD="false"
  BGE_MODEL_PATH="BAAI/bge-m3"
  BGE_BATCH_SIZE="8"
  BGE_DEVICE="cpu"
  BGE_PRELOAD="false"
  YOUTUBE_TRANSCRIPTS_VALUE="false"

  case "${PROFILE}" in
    Low)
      RAG_ENABLED_VALUE="false"
      BGE_BATCH_SIZE="8"
      ;;
    Medium)
      RAG_ENABLED_VALUE="true"
      BGE_BATCH_SIZE="16"
      ;;
    High)
      RAG_ENABLED_VALUE="true"
      BGE_BATCH_SIZE="32"
      ;;
    *)
      die "Unknown profile: ${PROFILE}"
      ;;
  esac

  # ── Image Stack Configuration ─────────────────────────────────────────────────

  case "${IMAGE_STACK}" in
    "None")
      OCR_ENABLED_VALUE="false"
      ;;
    "OCR only")
      OCR_ENABLED_VALUE="true"
      OCR_PRELOAD="true"
      ;;
    *)
      die "Unknown image processing stack: ${IMAGE_STACK}"
      ;;
  esac

  # ── OCR Provider Selection ───────────────────────────────────────────────────

  if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
    if [[ "${INSTALL_SKIP_PROMPTS:-}" != "1" ]]; then
      OCR_PROVIDER_CHOICE="$(prompt_choice "Choose an OCR provider:" "PaddleOCR" "EasyOCR")"
    else
      OCR_PROVIDER_CHOICE="${INSTALL_OCR_PROVIDER:-PaddleOCR}"
    fi

    case "${OCR_PROVIDER_CHOICE}" in
      PaddleOCR)
        OCR_PROVIDER_VALUE="paddleocr"
        ;;
      EasyOCR)
        OCR_PROVIDER_VALUE="easyocr"
        ;;
      *)
        die "Unknown OCR provider: ${OCR_PROVIDER_CHOICE}"
        ;;
    esac
    info "Selected OCR provider: ${OCR_PROVIDER_CHOICE}"
  fi

  # ── YouTube Transcripts ───────────────────────────────────────────────────────

  if [[ "${INSTALL_SKIP_PROMPTS:-}" != "1" ]]; then
    if [[ "$(prompt_yes_no "Enable YouTube transcript uploads?" "n")" == "yes" ]]; then
      YOUTUBE_TRANSCRIPTS_VALUE="true"
    fi
  else
    YOUTUBE_TRANSCRIPTS_VALUE="${INSTALL_YOUTUBE_TRANSCRIPTS:-false}"
  fi

  # ── Accelerator & Device Configuration ──────────────────────────────────────

  if [[ "${ACCELERATOR}" == "CUDA" ]]; then
    BGE_DEVICE="cuda"
    BGE_PRELOAD="true"
    if [[ "${RAG_ENABLED_VALUE}" == "false" ]]; then
      BGE_PRELOAD="false"
    fi
  else
    BGE_DEVICE="cpu"
    BGE_PRELOAD="false"
  fi

  # ── RAG Model Path Configuration ─────────────────────────────────────────────

  case "${RAG_MODEL_VALUE}" in
    ollama)
      RAG_ENABLED_VALUE="true"
      BGE_MODEL_PATH="ollama"
      BGE_PRELOAD="false"
      info "RAG enabled with Ollama (requires external ollama server)"
      ;;
    none)
      RAG_ENABLED_VALUE="false"
      BGE_MODEL_PATH=""
      info "RAG disabled"
      ;;
    *)
      if [[ "${RAG_MODEL_VALUE}" != "BAAI/bge-m3" ]]; then
        RAG_ENABLED_VALUE="true"
        BGE_MODEL_PATH="${RAG_MODEL_VALUE}"
      else
        if [[ "${RAG_ENABLED_VALUE}" == "true" ]]; then
          BGE_MODEL_PATH="${RAG_MODEL_DIR}"
        fi
      fi
      ;;
  esac

  if [[ "${OCR_ENABLED_VALUE}" == "false" ]]; then
    OCR_PRELOAD="false"
  fi

  # ── Resume Support ───────────────────────────────────────────────────────────

  if [[ "${RESUME}" == "true" ]]; then
    info "Resume mode: skipping completed steps from previous run"
  fi

  # ── Write Environment File ───────────────────────────────────────────────────

  step "ENV" "Writing environment configuration to ${ENV_FILE}"
  write_env "${ENV_FILE}" \
    "DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}" \
    "OPENROUTER_API_KEY=${OPENROUTER_API_KEY}" \
    "OPENROUTER_HTTP_REFERER=${OPENROUTER_HTTP_REFERER}" \
    "OPENROUTER_APP_TITLE=${OPENROUTER_APP_TITLE}" \
    "PROJECT_WORKSPACE_ROOT=${ROOT_DIR}/data/workspaces" \
    "CHROMA_DB_PATH=${ROOT_DIR}/chroma_db" \
    "RAG_ENABLED=${RAG_ENABLED_VALUE}" \
    "OCR_ENABLED=${OCR_ENABLED_VALUE}" \
    "OCR_PROVIDER=${OCR_PROVIDER_VALUE}" \
    "OCR_PRELOAD=${OCR_PRELOAD}" \
    "YOUTUBE_TRANSCRIPTS_ENABLED=${YOUTUBE_TRANSCRIPTS_VALUE}" \
    "BGE_M3_MODEL_PATH=${BGE_MODEL_PATH}" \
    "BGE_M3_DEVICE=${BGE_DEVICE}" \
    "BGE_M3_BATCH_SIZE=${BGE_BATCH_SIZE}" \
    "BGE_M3_PRELOAD=${BGE_PRELOAD}"
  mark_step_done "ENV"

  ensure_proxies

  # ── Create Virtual Environment ─────────────────────────────────────────────

  ensure_venv

  # ── Install Dependencies ─────────────────────────────────────────────────────

  install_requirements

  # ── Download RAG Model ───────────────────────────────────────────────────────

  if [[ "${RAG_ENABLED_VALUE}" == "true" ]] && [[ "${RAG_MODEL_VALUE}" == "BAAI/bge-m3" ]]; then
    if [[ "${SKIP_MODEL}" == "true" ]]; then
      info "Skipping RAG model download (--skip-model)"
    else
      download_model_snapshot "${RAG_MODEL_REPO}" "${RAG_MODEL_DIR}" "BGE-M3 embedding model"
    fi
  fi

  # ── Preload OCR Assets ────────────────────────────────────────────────────────

  if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
    preload_ocr_assets
  fi

  # ── Health Checks ───────────────────────────────────────────────────────────

  run_health_checks

  # ── Summary ─────────────────────────────────────────────────────────────────

  step "SUMMARY" "Installation complete"
  info "Installation summary:"
  printf '  profile: %s\n' "${PROFILE}" | tee -a "${INSTALL_LOG}"
  printf '  accelerator: %s\n' "${ACCELERATOR}" | tee -a "${INSTALL_LOG}"
  printf '  image processing stack: %s\n' "${IMAGE_STACK}" | tee -a "${INSTALL_LOG}"
  printf '  DeepSeek API configured: %s\n' "$( [[ -n "${DEEPSEEK_API_KEY}" ]] && printf yes || printf no )" | tee -a "${INSTALL_LOG}"
  printf '  OpenRouter API configured: %s\n' "$( [[ -n "${OPENROUTER_API_KEY}" ]] && printf yes || printf no )" | tee -a "${INSTALL_LOG}"
  printf '  RAG enabled: %s\n' "${RAG_ENABLED_VALUE}" | tee -a "${INSTALL_LOG}"
  printf '  RAG model: %s\n' "${RAG_MODEL_VALUE}" | tee -a "${INSTALL_LOG}"
  printf '  BGE_M3_MODEL_PATH: %s\n' "${BGE_MODEL_PATH}" | tee -a "${INSTALL_LOG}"
  printf '  OCR enabled: %s\n' "${OCR_ENABLED_VALUE}" | tee -a "${INSTALL_LOG}"
  if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
    printf '  OCR provider: %s\n' "${OCR_PROVIDER_VALUE}" | tee -a "${INSTALL_LOG}"
  fi
  printf '  YouTube transcripts: %s\n' "${YOUTUBE_TRANSCRIPTS_VALUE}" | tee -a "${INSTALL_LOG}"
  printf '  workspace root: %s\n' "${ROOT_DIR}/data/workspaces" | tee -a "${INSTALL_LOG}"
  printf '  ChromaDB path: %s\n' "${ROOT_DIR}/chroma_db" | tee -a "${INSTALL_LOG}"
  printf '  model cache: %s\n' "${MODEL_DIR}" | tee -a "${INSTALL_LOG}"
  printf '  install log: %s\n' "${INSTALL_LOG}" | tee -a "${INSTALL_LOG}"
  printf '  virtualenv: %s\n' "${VENV_DIR}" | tee -a "${INSTALL_LOG}"

  info "Next steps:"
  printf '  Activate virtual environment: source "%s/bin/activate"\n' "${VENV_DIR}" | tee -a "${INSTALL_LOG}"
  printf '  Run the application: python app.py\n' | tee -a "${INSTALL_LOG}"

  info "=== Installation finished successfully ==="
  info "Full log available at: ${INSTALL_LOG}"
}

# ─── Entry Point ───────────────────────────────────────────────────────────────

main "$@"
