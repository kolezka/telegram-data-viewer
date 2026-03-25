#!/usr/bin/env bash
# extract-keys.sh — Extract Telegram encryption keys from macOS Keychain
# Usage: ./extract-keys.sh [backup_dir]
# Extracts encryption keys needed to decrypt Telegram databases

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
BACKUP_DIR="${1:-./tg_$(date +"%Y-%m-%d_%H-%M-%S")}"
KEYS_FILE="$BACKUP_DIR/telegram_keys.json"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

log()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()     { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()    { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Functions ─────────────────────────────────────────────────────────────────
extract_telegram_keys() {
    local keys_json=""
    
    log "Searching for Telegram keys in keychain..." >&2
    
    # Common Telegram keychain entries
    local key_patterns=(
        "Telegram"
        "ru.keepcoder.Telegram"
        "6N38VWS5BX.ru.keepcoder.Telegram"
        "postbox"
        "local_storage"
        "temp_key"
        "tempKeyEncrypted"
        "masterKey"
    )
    
    # Extract keys and build JSON
    keys_json="{"
    local first_key=true
    
    for pattern in "${key_patterns[@]}"; do
        log "  Searching for pattern: $pattern" >&2
        
        # Search generic passwords
        while IFS= read -r line; do
            if [[ -n "$line" ]]; then
                local account=$(echo "$line" | cut -d: -f1)
                local service=$(echo "$line" | cut -d: -f2)
                
                # Try to extract the actual password
                local password=""
                if password=$(security find-generic-password -a "$account" -s "$service" -w 2>/dev/null); then
                    if [[ "$first_key" == "false" ]]; then
                        keys_json+=","
                    fi
                    keys_json+="\"${account}_${service}\": \"$password\""
                    first_key=false
                    ok "    Found key: $account @ $service" >&2
                fi
            fi
        done < <(security dump-keychain 2>/dev/null | grep -A1 -B1 "$pattern" | grep -E "acct|svce" | paste - - | sed 's/.*"\(.*\)".*/\1/' | tr ' ' ':' 2>/dev/null || true)
        
        # Search internet passwords
        while IFS= read -r line; do
            if [[ -n "$line" ]]; then
                local account=$(echo "$line" | cut -d: -f1)
                local server=$(echo "$line" | cut -d: -f2)
                
                # Try to extract the actual password
                local password=""
                if password=$(security find-internet-password -a "$account" -s "$server" -w 2>/dev/null); then
                    if [[ "$first_key" == "false" ]]; then
                        keys_json+=","
                    fi
                    keys_json+="\"${account}_${server}\": \"$password\""
                    first_key=false
                    ok "    Found internet key: $account @ $server" >&2
                fi
            fi
        done < <(security dump-keychain 2>/dev/null | grep -A1 -B1 "$pattern" | grep -E "acct|srvr" | paste - - | sed 's/.*"\(.*\)".*/\1/' | tr ' ' ':' 2>/dev/null || true)
    done
    
    keys_json+="}"
    echo "$keys_json"
}

extract_tempkey() {
    log "Extracting tempkey file..." >&2
    
    local tempkey_info=""
    
    # Look for .tempkeyEncrypted file in backup
    local tempkey_files=(
        "$BACKUP_DIR/.tempkeyEncrypted"
        "$BACKUP_DIR"/*/.tempkeyEncrypted
        "$HOME/Library/Group Containers/6N38VWS5BX.ru.keepcoder.Telegram/appstore/.tempkeyEncrypted"
    )
    
    for tempkey_file in "${tempkey_files[@]}"; do
        if [[ -f "$tempkey_file" ]]; then
            log "  Found tempkey file: $tempkey_file" >&2
            local hex_key=$(hexdump -v -e '1/1 "%02x"' "$tempkey_file")
            tempkey_info+="{\"file\": \"$tempkey_file\", \"hex_data\": \"$hex_key\"},"
            
            # Copy tempkey to backup if not already there
            if [[ "$tempkey_file" != "$BACKUP_DIR"* ]]; then
                cp -p "$tempkey_file" "$BACKUP_DIR/" 2>/dev/null || true
            fi
        fi
    done
    
    # Remove trailing comma and wrap in array
    if [[ -n "$tempkey_info" ]]; then
        echo "[${tempkey_info%,}]"
    else
        echo "[]"
    fi
}

extract_device_keys() {
    log "Extracting device-specific keys..." >&2
    
    # Look for Telegram-specific device keys
    local device_keys=""
    
    # Check for postbox encryption keys by account
    if [[ -d "$BACKUP_DIR" ]]; then
        for account_dir in "$BACKUP_DIR"/account-*; do
            if [[ -d "$account_dir" ]]; then
                local account_id=$(basename "$account_dir" | sed 's/account-//')
                log "  Searching keys for account: $account_id" >&2
                
                # Try various key naming patterns
                local key_names=(
                    "postbox_key_$account_id"
                    "storage_key_$account_id"
                    "db_key_$account_id"
                    "$account_id"
                )
                
                for key_name in "${key_names[@]}"; do
                    if key_value=$(security find-generic-password -s "Telegram" -a "$key_name" -w 2>/dev/null); then
                        device_keys+="{\"account\": \"$account_id\", \"key_name\": \"$key_name\", \"key_value\": \"$key_value\"},"
                        ok "    Found account key: $key_name" >&2
                    fi
                done
            fi
        done
    fi
    
    # Remove trailing comma and wrap in array
    if [[ -n "$device_keys" ]]; then
        device_keys="[${device_keys%,}]"
    else
        device_keys="[]"
    fi
    
    echo "$device_keys"
}

# ── Main ──────────────────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

log "Starting Telegram keychain extraction..."
log "Output directory: $BACKUP_DIR"

# Extract all Telegram-related keys
all_keys=$(extract_telegram_keys)
device_keys=$(extract_device_keys)
tempkey_data=$(extract_tempkey)

# Create comprehensive keys file
cat > "$KEYS_FILE" << EOF
{
    "extraction_time": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "device": "$(hostname)",
    "telegram_keys": $all_keys,
    "device_keys": $device_keys,
    "tempkey_files": $tempkey_data,
    "notes": "Keys extracted from macOS keychain for Telegram database decryption"
}
EOF

ok "Keys extracted to: $KEYS_FILE"

# Show summary
key_count=$(echo "$all_keys" | jq 'length' 2>/dev/null || echo "0")
device_key_count=$(echo "$device_keys" | jq 'length' 2>/dev/null || echo "0")
tempkey_count=$(echo "$tempkey_data" | jq 'length' 2>/dev/null || echo "0")

log "Summary:"
log "  Telegram keys found: $key_count"
log "  Device keys found: $device_key_count"
log "  Tempkey files found: $tempkey_count"

if [[ "$key_count" -eq 0 && "$device_key_count" -eq 0 && "$tempkey_count" -eq 0 ]]; then
    warn "No keys found! This could mean:"
    warn "  1. Telegram is not installed or never run"
    warn "  2. Keys are stored with different naming patterns"
    warn "  3. Additional permissions needed for keychain access"
    echo ""
    log "Try running with sudo or check Security & Privacy settings"
fi

echo ""
ok "Key extraction complete!"