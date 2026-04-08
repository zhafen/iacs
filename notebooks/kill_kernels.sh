#!/usr/bin/env bash
# Kill all active Jupyter kernel processes, clear stale connection files,
# and clear notebook outputs.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pids=$(pgrep -f "ipykernel_launcher")

if [ -z "$pids" ]; then
    echo "No active Jupyter kernels found."
else
    echo "Killing Jupyter kernel PIDs: $pids"
    kill -9 $pids
    sleep 1
    echo "Kernels killed."
fi

# Clear stale kernel connection files so VSCode doesn't try to reconnect
runtime_dir=$(jupyter --runtime-dir 2>/dev/null)
if [ -n "$runtime_dir" ] && [ -d "$runtime_dir" ]; then
    connection_files=("$runtime_dir"/kernel-*.json)
    if [ -f "${connection_files[0]}" ]; then
        echo "Removing ${#connection_files[@]} stale connection files from $runtime_dir"
        rm -f "${connection_files[@]}"
    else
        echo "No stale connection files found."
    fi
fi

# Clear notebook outputs and execution counts
echo "Clearing notebook outputs in $SCRIPT_DIR..."
for nb in "$SCRIPT_DIR"/*.ipynb; do
    [ -f "$nb" ] || continue
    echo "  Clearing: $(basename "$nb")"
    jupyter nbconvert --clear-output --inplace "$nb" 2>/dev/null
done

echo "Done."
