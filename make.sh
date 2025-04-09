#!/usr/bin/env bash

hello() {
  echo "Hello World"
}

tests() {
  if ! lzop --version &> /dev/null; then
    echo "lzop is not installed"
    exit 1
  fi
  echo "lzop installed"

  if ! zip --version &> /dev/null; then
    echo "zip is not installed"
    exit 1
  fi
  echo "zip installed"

  if ! ssh -V &> /dev/null; then
    echo "ssh is not installed"
    exit 1
  fi
  echo "ssh installed"

  if ! command -v python3 &> /dev/null; then
    echo "python3 is required"
    exit 1
  fi
  echo "python3 installed"

  python_version=$(python3 -c "import sys;print(sys.version_info[0:2][1])")
  if [[ $python_version -lt 8 ]]; then
    echo "python 3.8 or higher required"
    exit 1
  fi
  echo "python 3.8 or higher installed"

  if ! python3 -c "import polars as pl"; then
    echo "polars module is not installed"
    exit 1
  fi
  echo "polars installed"

  if ! python3 -c "import typer"; then
    echo "typer module is not installed"
    exit 1
  fi
  echo "typer installed"

  if ! python3 -c "import tqdm"; then
    echo "tqdm module is not installed"
    exit 1
  fi
  echo "tqdm installed"

  echo "Tests complete"
}

config() {
  echo "Preparing current folder..."
  mkdir -p ./var/static
  echo "Prep done"
}

install() {
    echo "Installing Python modules"
    pip3 install polars tqdm 
}

clean() {
  echo "Cleaning up..."
  rm -f ${STATIC_DIR}/*
  unset $(grep -v '^#' .env | sed -E 's/(.*)=.*/\1/' | xargs)
  echo "Clean up done"
}

# Main
if ! [ -f .env ]; then
  echo ".env file not found!"
  exit 1
fi

export $(grep -v '^#' .env | xargs)

if [[ -z ${WORKING_DIR} ]]; then
  export WORKING_DIR=$(pwd)/var
fi

if [[ -z ${STATIC_DIR} ]]; then
  export STATIC_DIR=${WORKING_DIR}/static
fi

case "$1" in
  hello)
    hello
    ;;
  tests)
    tests
    ;;
  config)
    config
    ;;
  install)
    config
    ;;
  clean)
    clean
    ;;
  *)
    echo "Usage: $0 {hello|tests|config|clean}"
    exit 1
    ;;
esac
