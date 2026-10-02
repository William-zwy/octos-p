#!/bin/sh
# Build a commit-bound Agent ZIP and fail closed before upload.
set -eu

script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
cd "$script_dir"

if [ -n "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all -- arc skills/arc-project-context)" ]; then
  echo "error: refusing to package a dirty source tree; commit the release first" >&2
  exit 2
fi

select_python() {
  # Windows Git Bash may expose a Store python3 shim without PyYAML while
  # "python" resolves to the provisioned runtime. Probe the actual dependency
  # before selecting a candidate; this stays domain-neutral and portable.
  for candidate in "${PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import yaml' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}
if ! python_cmd=$(select_python); then
  echo "error: no usable Python interpreter with PyYAML (tried PYTHON, python3, python)" >&2
  exit 3
fi

output="${1:-../octos-arc-bundle.zip}"
case "$output" in
  /*) ;;
  *) output="$script_dir/$output" ;;
esac
shape_output="${output%.zip}.shape.json"
binding_output="${output%.zip}.binding.json"
checksum_output="${output}.sha256"
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/octos-arc-pack.XXXXXX")
temp_archive="$temp_dir/agent.zip"
cleanup() { rm -rf "$temp_dir"; }
trap cleanup EXIT HUP INT TERM

commit=$(git -C "$repo_root" rev-parse HEAD)
git -c core.autocrlf=false -C "$repo_root" archive --format=zip --output="$temp_archive" HEAD:arc -- \
  main.py octos_stdio.py requirement_order.py acceptance.py guard.py llm_proxy.py codegen.py \
  run_controls.py seed_isolation.py requirement_contract.py build_identity.py package_shape.py hooks requirements.txt \
  arcbench_agent_runtime public-tests

identity_script="$script_dir/build_identity.py"
gate_script="$script_dir/package_gate.py"
to_python_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}
skill_archive="$temp_dir/skill.zip"
git -c core.autocrlf=false -C "$repo_root" archive --format=zip \
  --prefix=skills/arc-project-context/ --output="$skill_archive" \
  HEAD:skills/arc-project-context -- SKILL.md manifest.json index.js main
temp_archive_native=$(to_python_path "$temp_archive")
skill_archive_native=$(to_python_path "$skill_archive")
"$python_cmd" -c 'import sys,zipfile; dst=zipfile.ZipFile(sys.argv[1],"a"); src=zipfile.ZipFile(sys.argv[2]); [(dst.writestr(i,src.read(i.filename))) for i in src.infolist() if not i.is_dir()]; src.close(); dst.close()' \
  "$temp_archive_native" "$skill_archive_native"
identity_script_native=$(to_python_path "$identity_script")
gate_script_native=$(to_python_path "$gate_script")
temp_archive_native=$(to_python_path "$temp_archive")
"$python_cmd" "$identity_script_native" embed --archive "$temp_archive_native" --commit "$commit" >/dev/null

task_key="${ARCBENCH_TASK_KEY:-${ARCBENCH_TASK:-}}"
suite_key="${ARCBENCH_TEST_SUITE_KEY:-${ARCBENCH_SUITE_KEY:-}}"
identity_mode="${ARCBENCH_PLATFORM_IDENTITY_MODE:-suite_required}"
suite_provenance="${ARCBENCH_SUITE_PROVENANCE:-}"
requirements_sha="${ARCBENCH_REQUIREMENTS_SHA256:-${ARCBENCH_REQUIREMENTS_HASH:-}}"
if [ -z "$task_key" ] || [ -z "$requirements_sha" ]; then
  echo "error: ARCBENCH_TASK_KEY and ARCBENCH_REQUIREMENTS_SHA256 are required" >&2
  exit 4
fi
if [ "$identity_mode" = "suite_required" ] && [ -z "$suite_key" ]; then
  echo "error: suite_required packaging needs ARCBENCH_TEST_SUITE_KEY" >&2
  exit 4
fi

mkdir -p "$(dirname "$output")"
rm -f "$output" "$shape_output" "$binding_output" "$checksum_output"
mv "$temp_archive" "$output"
output_native=$(to_python_path "$output")
shape_output_native=$(to_python_path "$shape_output")
binding_output_native=$(to_python_path "$binding_output")
"$python_cmd" "$gate_script_native" bind --archive "$output_native" --shape-output "$shape_output_native" \
  --output "$binding_output_native" --source-commit "$commit" --task-key "$task_key" \
  --suite-key "$suite_key" --suite-provenance "$suite_provenance" --identity-mode "$identity_mode" \
  --requirements-sha256 "$requirements_sha"
sha256=$("$python_cmd" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$output_native")
printf '%s  %s\n' "$sha256" "$(basename "$output")" > "$checksum_output"
echo "Packaging complete: $output"
echo "SHA256: $sha256"
echo "Binding: $binding_output"
