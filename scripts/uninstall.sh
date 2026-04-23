#!/usr/bin/env bash
#
# Uninstall/cleanup script for RAG Vision Chatbot
#
# This script removes installed components while preserving user data.
# Use --full for complete removal including all data.
#
set -euo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
ENV_FILE="${ROOT_DIR}/.env"
MODEL_DIR="${ROOT_DIR}/models"
CHROMA_DB="${ROOT_DIR}/chroma_db"
WORKSPACE_DIR="${ROOT_DIR}/data/workspaces"
INSTALL_LOG="${ROOT_DIR}/install.log"
STEPS_DONE="${ROOT_DIR}/.install_steps"
PROXIES_FILE="${ROOT_DIR}/proxies.txt"

# ─── Logging ────────────────────────────────────────────────────────────────

log() {
  printf '[uninstall] %s\n' "$*"
}

info()    { log "INFO: $*"; }
warn()    { log "WARN: $*" >&2; }
error()   { log "ERROR: $*" >&2; }
die()     { error "$*"; exit 1; }

# ─── CLI Flags ───────────────────────────────────────────────────────────────

FULL_CLEAN=false
SKIP_BACKUP=false
DRY_RUN=false

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --full)
        FULL_CLEAN=true
        shift
        ;;
      --skip-backup)
        SKIP_BACKUP=true
        shift
        ;;
      --dry-run)
        DRY_RUN=true
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
Usage: uninstall.sh [OPTIONS]

Options:
  --full         Complete cleanup - remove ALL data including workspaces, uploads, DB
  --skip-backup  Skip backing up .env file before deletion
  --dry-run      Show what would be deleted without actually deleting
  --help, -h     Show this help message

Examples:
  ./uninstall.sh           # Remove venv, dependencies, keep data
  ./uninstall.sh --full    # Complete removal including all data
  ./uninstall.sh --dry-run # Preview what would be deleted
EOF
}

# ─── Helpers ────────────────────────────────────────────────────────────────

run_or_dry() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Would execute: $*"
  else
    "$@"
  fi
}

confirm_destructive() {
  local action="$1"
  local target="$2"

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] Would ${action}: ${target}"
    return 0
  fi

  printf 'This will %s: %s\n' "${action}" "${target}" >&2
  read -r -p "Are you sure? Type 'yes' to confirm: " answer
  if [[ "${answer}" != "yes" ]]; then
    echo "Cancelled."
    return 1
  fi
  return 0
}

# ─── Checks ────────────────────────────────────────────────────────────────

require_linux() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    die "This uninstaller is supported on Linux only."
  fi
}

# ─── Backup ────────────────────────────────────────────────────────────────

backup_env() {
  if [[ "${SKIP_BACKUP}" == "true" ]]; then
    info "Skipping .env backup (--skip-backup)"
    return
  fi

  if [[ ! -f "${ENV_FILE}" ]]; then
    info ".env file not found, skipping backup"
    return
  fi

  local backup="${ENV_FILE}.uninstall-backup.$(date '+%Y%m%d_%H%M%S')"
  run_or_dry cp "${ENV_FILE}" "${backup}"
  info "Backed up .env to ${backup}"
}

backup_proxies() {
  if [[ ! -f "${PROXIES_FILE}" ]]; then
    return
  fi

  local backup="${PROXIES_FILE}.uninstall-backup.$(date '+%Y%m%d_%H%M%S')"
  run_or_dry cp "${PROXIES_FILE}" "${backup}"
  info "Backed up proxies.txt to ${backup}"
}

# ─── Component Removal ──────────────────────────────────────────────────────

remove_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    info "Virtual environment not found at ${VENV_DIR}, skipping"
    return
  fi

  if ! confirm_destructive "remove virtual environment" "${VENV_DIR}"; then
    return
  fi

  run_or_dry rm -rf "${VENV_DIR}"
  info "Removed virtual environment"
}

remove_models() {
  if [[ ! -d "${MODEL_DIR}" ]]; then
    info "Model directory not found, skipping"
    return
  fi

  if ! confirm_destructive "remove all downloaded models" "${MODEL_DIR}"; then
    return
  fi

  run_or_dry rm -rf "${MODEL_DIR}"
  info "Removed model cache"
}

remove_chroma_db() {
  if [[ ! -d "${CHROMA_DB}" ]]; then
    info "ChromaDB directory not found, skipping"
    return
  fi

  if ! confirm_destructive "remove ChromaDB vector database" "${CHROMA_DB}"; then
    return
  fi

  run_or_dry rm -rf "${CHROMA_DB}"
  info "Removed ChromaDB directory"
}

remove_workspaces() {
  if [[ ! -d "${WORKSPACE_DIR}" ]]; then
    info "Workspaces directory not found, skipping"
    return
  fi

  if ! confirm_destructive "remove ALL workspace data" "${WORKSPACE_DIR}"; then
    return
  fi

  run_or_dry rm -rf "${WORKSPACE_DIR}"
  info "Removed workspace directory"
}

remove_install_artifacts() {
  info "Removing installation artifacts..."

  local artifacts=(
    "${INSTALL_LOG}"
    "${STEPS_DONE}"
  )

  for artifact in "${artifacts[@]}"; do
    if [[ -f "${artifact}" ]]; then
      run_or_dry rm -f "${artifact}"
      info "Removed ${artifact}"
    fi
  done
}

remove_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    info ".env file not found, skipping"
    return
  fi

  if ! confirm_destructive "remove configuration file" "${ENV_FILE}"; then
    return
  fi

  run_or_dry rm -f "${ENV_FILE}"
  info "Removed .env file"
}

remove_proxies() {
  if [[ ! -f "${PROXIES_FILE}" ]]; then
    return
  fi

  if ! confirm_destructive "remove proxies file" "${PROXIES_FILE}"; then
    return
  fi

  run_or_dry rm -f "${PROXIES_FILE}"
  info "Removed proxies.txt"
}

# ─── Status ────────────────────────────────────────────────────────────────

show_status() {
  echo ""
  echo "=== Current Installation Status ==="
  echo ""

  echo "- Virtual environment: ${VENV_DIR}"
  [[ -d "${VENV_DIR}" ]] && echo "  [EXISTS]" || echo "  [NOT FOUND]"
  echo ""

  echo "- Model cache: ${MODEL_DIR}"
  [[ -d "${MODEL_DIR}" ]] && echo "  [EXISTS]" || echo "  [NOT FOUND]"
  echo ""

  echo "- ChromaDB: ${CHROMA_DB}"
  [[ -d "${CHROMA_DB}" ]] && echo "  [EXISTS]" || echo "  [NOT FOUND]"
  echo ""

  echo "- Workspace data: ${WORKSPACE_DIR}"
  [[ -d "${WORKSPACE_DIR}" ]] && echo "  [EXISTS]" || echo "  [NOT FOUND]"
  echo ""

  echo "- .env file: ${ENV_FILE}"
  [[ -f "${ENV_FILE}" ]] && echo "  [EXISTS]" || echo "  [NOT FOUND]"
  echo ""

  echo "- Install log: ${INSTALL_LOG}"
  [[ -f "${INSTALL_LOG}" ]] && echo "  [EXISTS]" || echo "  [NOT FOUND]"
  echo ""
}

# ─── Main ────────────────────────────────────────────────────────────────

main() {
  parse_args "$@"

  require_linux

  if [[ "${DRY_RUN}" == "true" ]]; then
    info "Running in DRY-RUN mode - no changes will be made"
  fi

  echo ""
  echo "============================================"
  echo "  RAG Vision Chatbot - Uninstall Script"
  echo "============================================"
  echo ""

  if [[ "${FULL_CLEAN}" == "true" ]]; then
    info "Running in FULL CLEAN mode - all data will be removed"
  fi

  show_status

  # Always backup .env before any destructive action
  backup_env
  backup_proxies

  echo ""

  # Safe removals (user data potentially involved, so we prompt)
  remove_venv

  if [[ "${FULL_CLEAN}" == "true" ]]; then
    remove_models
    remove_chroma_db
    remove_workspaces
  fi

  # Cleanup artifacts
  remove_install_artifacts

  # Dangerous - no backup
  if [[ "${FULL_CLEAN}" == "true" ]]; then
    remove_env_file
    remove_proxies
  fi

  echo ""
  echo "============================================"
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "  DRY-RUN complete - no changes made"
  else
    echo "  Uninstall complete!"
  fi
  echo "============================================"
  echo ""

  if [[ "${FULL_CLEAN}" != "true" ]]; then
    echo "Note: User data directories preserved."
    echo "To completely remove all data, run: $0 --full"
  fi
}

# ─── Entry Point ────────────────────────────────────────────────────────────

main "$@"
