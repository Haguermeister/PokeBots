#!/bin/zsh

PICO="http://YOUR_PICO_IP:8080"
RESET_TIME=3.5

zmodload zsh/datetime
START_TIME=$EPOCHREALTIME

# -----------------------
# Helpers
# -----------------------

rand_wait() {
  local RAND=$(od -An -tu4 -N4 /dev/urandom | tr -d ' ')
  local DELAY=$(awk -v min="$1" -v max="$2" -v r="$RAND" 'BEGIN { printf "%.2f", min + (r / 4294967295.0) * (max - min) }')
  echo "Random wait: $DELAY seconds"
  sleep "$DELAY"
}

send_pico() {
  local ENDPOINT=$1
  local BODY=${2-}
  if [[ -n "$BODY" ]]; then
    curl -s -o /dev/null --max-time 2 -X POST "$PICO/$ENDPOINT" -d "$BODY" 2>/dev/null
  else
    curl -s -o /dev/null --max-time 2 -X POST "$PICO/$ENDPOINT" 2>/dev/null
  fi
}

press() {
  send_pico "cmd" "press $1 120" &
  sleep "${2:-0.5}"
  wait $!
}

hold_button() {
  send_pico "cmd" "press $1 $2" &
  sleep "$(awk -v ms="$2" 'BEGIN { printf "%.2f", ms / 1000 + 0.05 }')"
  wait $!
}

repeat_press() {
  for ((i=1; i<=$3; i++)); do
    press "$1" "$2"
  done
}

# -----------------------
# Sequence
# -----------------------

echo "Starting sequence..."

send_pico "reset"
sleep "$RESET_TIME"

# Title screen — rand wait on Charizard, hold A through it
repeat_press A 0.4 2
rand_wait 0.17 2
hold_button A 1800
sleep 0.6

# Load save + pick pokemon
press A 1.2
repeat_press A 0.2 30
press A 0.9

# "This pokemon is energetic" — rand wait, then decline rename + rival picks
rand_wait 0.17 2
repeat_press B 0.2 40
sleep 2.3

# Open menu + navigate to summary
press X 1.2
repeat_press A 0.3 7
sleep 0.5

echo "Sequence complete"

END_TIME=$EPOCHREALTIME
ELAPSED=$(printf "%.3f" "$(( END_TIME - START_TIME ))")
echo "Runtime: ${ELAPSED}s"