#!/usr/bin/env bash
# Fails if the README's demo block differs from what the installed facturx-check prints.
set -euo pipefail
cd "$(dirname "$0")/.."
expected=$(awk '/<!-- demo:start -->/{f=1;next} /<!-- demo:end -->/{f=0} f' README.md | sed '1d;$d')
actual=""
for f in consistent profile-mismatch wrong-filename undeclared-schema pdfa-2 no-xmp; do
  [ -n "$actual" ] && actual+=$'\n\n'
  actual+="\$ facturx-check testdata/$f.pdf"$'\n'
  # exit 1 is expected for every fixture except the consistent one
  actual+=$( (facturx-check "testdata/$f.pdf" || test $? -eq 1) | tr -d '\r')
done
if [ "$expected" != "$actual" ]; then
  diff <(echo "$expected") <(echo "$actual") || true
  echo "README demo is out of date" >&2
  exit 1
fi
echo "README demo matches"
