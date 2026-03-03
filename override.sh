#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEDULER="$SCRIPT_DIR/scheduler.py"
OVERRIDE_FILE="$SCRIPT_DIR/override.txt"

if [[ ! -f "$SCHEDULER" ]]; then
    echo "scheduler.py not found in $SCRIPT_DIR"
    exit 1
fi

# Extract FUNCTION_MAP keys
mapfile -t FUNCTIONS < <(
    awk '
        $0 ~ /^FUNCTION_MAP *= *{/ { in_map=1; next }
        in_map && $0 ~ /^}/ { in_map=0 }
        in_map {
            if (match($0, /"([^"]+)":/, a)) {
                print a[1]
            }
        }
    ' "$SCHEDULER"
)

if [[ ${#FUNCTIONS[@]} -eq 0 ]]; then
    echo "No functions found in FUNCTION_MAP"
    exit 1
fi

echo
echo "Available e-ink image functions:"
echo "--------------------------------"

for i in "${!FUNCTIONS[@]}"; do
    printf "  [%2d] %s\n" "$((i+1))" "${FUNCTIONS[$i]}"
done

echo
read -rp "Select function number (or ENTER to cancel): " choice

if [[ -z "${choice}" ]]; then
    echo "Cancelled."
    exit 0
fi

if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#FUNCTIONS[@]} )); then
    echo "Invalid selection."
    exit 1
fi

selected="${FUNCTIONS[$((choice-1))]}"

echo "$selected" > "$OVERRIDE_FILE"

echo
echo "Override set to: $selected"
echo "Written to: $OVERRIDE_FILE"


