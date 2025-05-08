#!/usr/bin/env bash

# Bootstrap environment and run a job.

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RKOJOBS_DIR=${BIN_DIR}/../src
PYTHONPATH+=:${RKOJOBS_DIR}

REQUIREMENTS_TXT=
VENV_DIR=
JOB_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--python-path)
      PYTHONPATH+=:$2
      shift
      ;;
    -r|--requirements-txt)
      REQUIREMENTS_TXT=$2
      shift
      ;;
    -e|--venv)
      REQUIREMENTS_TXT=$2
      shift
      ;;
    *)
      JOB_ARGS+=("$1")
      ;;
  esac
  shift
done

: "${WORKSPACE:=$(pwd)}"
: "${VENV_DIR:=${WORKSPACE}/.venv}"

: "${PYTHON:=python}"

if ! which -s "${PYTHON}"; then
  PYTHON=python3
  if ! which -s "${PYTHON}"; then
    echo "No python interpreter found. Set PYTHON=/path/to/bin/python"
    exit 1
  fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  ${PYTHON} -m venv "${VENV_DIR}" > /dev/null
  source "${VENV_DIR}/bin/activate" > /dev/null
  if [[ -f "${REQUIREMENTS_TXT}" ]]; then
    pip install -r "${REQUIREMENTS_TXT}" > /dev/null
  fi
else
  source "${VENV_DIR}/bin/activate" > /dev/null
fi

pushd "${WORKSPACE}" > /dev/null || exit 1
PYTHONPATH=".:${PYTHONPATH}" python -m rkojob "${JOB_ARGS[@]}"
RC=$?
popd > /dev/null || exit 1
exit $RC
