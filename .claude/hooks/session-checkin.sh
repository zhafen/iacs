#!/bin/bash
# Stop hook: every CHECKIN_EVERY turns, unconditionally (no reset on
# edits/commits -- this tracks overall session time investment, not
# design-discussion churn specifically), force one extra turn asking
# whether the current approach/scope is still the right one.
#
# {"decision":"block","reason":...} forces that continuation, which
# itself ends in another Stop event -- stop_hook_active is checked below
# so this hook doesn't re-block on the very turn it just caused.
set -euo pipefail

CHECKIN_EVERY=8

payload=$(cat)

stop_hook_active=$(echo "$payload" | jq -r '.stop_hook_active // false')
if [[ "$stop_hook_active" == "true" ]]; then
  exit 0
fi

# scratchpad_dir is session-scoped and already provided by the hook
# payload in a cloud session; falls back to a session_id-keyed /tmp dir
# for local CLI sessions where it may be absent.
scratchpad_dir=$(echo "$payload" | jq -r '.scratchpad_dir // empty')
session_id=$(echo "$payload" | jq -r '.session_id // "unknown"')
counter_dir="${scratchpad_dir:-/tmp/claude-session-checkin-$session_id}"
mkdir -p "$counter_dir"
counter_file="$counter_dir/turn-count"

count=0
[[ -f "$counter_file" ]] && count=$(cat "$counter_file")
count=$((count + 1))
echo "$count" > "$counter_file"

if (( count % CHECKIN_EVERY == 0 )); then
  jq -n --arg n "$count" --arg every "$CHECKIN_EVERY" \
    '{decision:"block", reason: ("Session check-in: " + $n + " turns in this session (every " + $every + "). Pause and tell the user directly: is the current approach/scope still the right one, or is it time to simplify, park, or wrap up? Then stop normally -- this is a prompt to check in, not an instruction to act on unprompted.")}'
fi

exit 0
