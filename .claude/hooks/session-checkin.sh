#!/bin/bash
# Stop hook: fires at turn FIRST_CHECKIN, then every CHECKIN_EVERY turns
# after that (2, 10, 18, ... by default) -- an early first check-in
# catches a bad direction before much time is sunk, then the wider
# spacing avoids interrupting a productive stretch. Unconditional, no
# reset on edits/commits: this tracks overall session time investment,
# not design-discussion churn specifically.
#
# {"decision":"block","reason":...} forces that continuation, which
# itself ends in another Stop event -- stop_hook_active is checked below
# so this hook doesn't re-block on the very turn it just caused.
set -euo pipefail

FIRST_CHECKIN=2
CHECKIN_EVERY=8
LOCK_MAX_ATTEMPTS=100
LOCK_SLEEP_SECONDS=0.01

payload=$(cat)

stop_hook_active=$(echo "$payload" | jq -r '.stop_hook_active // false')
if [[ "$stop_hook_active" == "true" ]]; then
  exit 0
fi

# scratchpad_dir is session-scoped and already provided by the hook
# payload in a cloud session; falls back to a sanitized session_id-keyed
# /tmp dir for local CLI sessions where it may be absent.
scratchpad_dir=$(echo "$payload" | jq -r '.scratchpad_dir // empty')
session_id=$(echo "$payload" | jq -r '.session_id // "unknown"')
if [[ -n "$scratchpad_dir" ]]; then
  counter_dir="$scratchpad_dir/session-checkin"
else
  safe_session_id=$(printf '%s' "$session_id" | base64 | tr -d '\n' | tr '/+' '_-' | tr -d '=')
  safe_session_id="${safe_session_id:-unknown}"
  counter_dir="/tmp/claude-session-checkin/$safe_session_id"
fi
mkdir -p "$counter_dir"
counter_file="$counter_dir/turn-count"
lock_dir="$counter_dir/.lock"

lock_acquired=false
for ((i = 0; i < LOCK_MAX_ATTEMPTS; i++)); do
  if mkdir "$lock_dir" 2>/dev/null; then
    lock_acquired=true
    break
  fi
  sleep "$LOCK_SLEEP_SECONDS"
done
if [[ "$lock_acquired" != "true" ]]; then
  exit 0
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

count=0
[[ -f "$counter_file" ]] && count=$(cat "$counter_file")
count=$((count + 1))
echo "$count" > "$counter_file"

if (( count == FIRST_CHECKIN || (count > FIRST_CHECKIN && (count - FIRST_CHECKIN) % CHECKIN_EVERY == 0) )); then
  jq -n --arg n "$count" --arg first "$FIRST_CHECKIN" --arg every "$CHECKIN_EVERY" \
    '{decision:"block", reason: ("Session check-in: " + $n + " turns in this session (first at turn " + $first + ", then every " + $every + " after that). Pause and tell the user directly: is the current approach/scope still the right one, or is it time to simplify, park, or wrap up? Then stop normally -- this is a prompt to check in, not an instruction to act on unprompted.")}'
fi

exit 0
