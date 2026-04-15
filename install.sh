#!/usr/bin/env bash
set -euo pipefail

umask 077

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

info() {
  printf '[install] %s\n' "$*"
}

warn() {
  printf '[install] warning: %s\n' "$*" >&2
}

die() {
  printf '[install] error: %s\n' "$*" >&2
  exit 1
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

ensure_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    info "Creating virtual environment at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
}

install_requirements() {
  info "Installing selected dependency sets"
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
}

install_requirements_file() {
  local requirements_file="$1"
  if [[ ! -f "${requirements_file}" ]]; then
    die "Missing requirements file: ${requirements_file}"
  fi
  info "Installing $(basename "${requirements_file}")"
  "${VENV_DIR}/bin/python" -m pip install -r "${requirements_file}"
}

install_paddle_runtime() {
  if [[ "${ACCELERATOR}" == "CUDA" ]]; then
    info "Installing PaddlePaddle 3.2.2 runtime for OCR"
    if "${VENV_DIR}/bin/python" -m pip install paddlepaddle==3.2.2; then
      return
    fi
    warn "Automatic PaddlePaddle installation failed; OCR will need a compatible paddlepaddle wheel."
    warn "See README.md if you want to install a CUDA-specific PaddlePaddle wheel manually."
  fi

  info "Installing PaddlePaddle 3.2.2 runtime"
  "${VENV_DIR}/bin/python" -m pip install paddlepaddle==3.2.2
}

download_model_snapshot() {
  local repo_id="$1"
  local target_dir="$2"
  local description="$3"

  mkdir -p "$(dirname "${target_dir}")"
  info "Downloading ${description} into ${target_dir}"
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
}

preload_ocr_assets() {
  info "Preloading OCR engine assets"
  "${VENV_DIR}/bin/python" - <<'PY'
from types import SimpleNamespace

from ocr_service import preload_ocr_engine

preload_ocr_engine(SimpleNamespace(debug=False))
PY
}

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

write_env() {
  local env_file_path="$1"
  shift

  if [[ ! -f "${ENV_EXAMPLE}" ]]; then
    die ".env.example was not found."
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

cuda_available() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi >/dev/null 2>&1 && return 0
  fi
  return 1
}

require_linux
find_python

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

if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
  OCR_PROVIDER_CHOICE="$(prompt_choice "Choose an OCR provider:" "PaddleOCR" "EasyOCR")"
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

if [[ "$(prompt_yes_no "Enable YouTube transcript uploads?" "n")" == "yes" ]]; then
  YOUTUBE_TRANSCRIPTS_VALUE="true"
fi

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

if [[ "${RAG_ENABLED_VALUE}" == "true" ]]; then
  BGE_MODEL_PATH="${RAG_MODEL_DIR}"
else
  BGE_MODEL_PATH="BAAI/bge-m3"
fi

if [[ "${OCR_ENABLED_VALUE}" == "false" ]]; then
  OCR_PRELOAD="false"
fi

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

ensure_proxies
ensure_venv
install_requirements
if [[ "${RAG_ENABLED_VALUE}" == "true" ]]; then
  download_model_snapshot "${RAG_MODEL_REPO}" "${RAG_MODEL_DIR}" "BGE-M3 embedding model"
fi
if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
  preload_ocr_assets
fi

info "Installation summary"
printf '  profile: %s\n' "${PROFILE}"
printf '  accelerator: %s\n' "${ACCELERATOR}"
printf '  image processing stack: %s\n' "${IMAGE_STACK}"
printf '  DeepSeek API configured: %s\n' "$( [[ -n "${DEEPSEEK_API_KEY}" ]] && printf yes || printf no )"
printf '  OpenRouter API configured: %s\n' "$( [[ -n "${OPENROUTER_API_KEY}" ]] && printf yes || printf no )"
printf '  workspace root: %s\n' "${ROOT_DIR}/data/workspaces"
printf '  ChromaDB path: %s\n' "${ROOT_DIR}/chroma_db"
printf '  RAG_ENABLED: %s\n' "${RAG_ENABLED_VALUE}"
printf '  BGE_M3_MODEL_PATH: %s\n' "${BGE_MODEL_PATH}"
printf '  OCR_ENABLED: %s\n' "${OCR_ENABLED_VALUE}"
if [[ "${OCR_ENABLED_VALUE}" == "true" ]]; then
  printf '  OCR_PROVIDER: %s\n' "${OCR_PROVIDER_VALUE}"
fi
printf '  YOUTUBE_TRANSCRIPTS_ENABLED: %s\n' "${YOUTUBE_TRANSCRIPTS_VALUE}"
printf '  model cache: %s\n' "${MODEL_DIR}"
printf '  .env: %s\n' "${ENV_FILE}"
printf '  virtualenv: %s\n' "${VENV_DIR}"

info "Next step: activate the virtual environment and run the app"
printf '  source "%s/bin/activate"\n' "${VENV_DIR}"
printf '  python app.py\n'
