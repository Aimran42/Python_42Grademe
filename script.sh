#!/bin/sh

alias grademe="python grademe.py"
alias examshell="python grademe.py"

cd "$(dirname "$0")"
exec uv run --with-requirements requirements.txt python grademe.py "$@"
