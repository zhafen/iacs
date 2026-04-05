#!/usr/bin/env bash
# Kill all active Jupyter kernel processes.

pids=$(pgrep -f "ipykernel_launcher")

if [ -z "$pids" ]; then
    echo "No active Jupyter kernels found."
    exit 0
fi

echo "Killing Jupyter kernel PIDs: $pids"
kill $pids
echo "Done."
