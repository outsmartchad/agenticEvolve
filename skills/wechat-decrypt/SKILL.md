# WeChat macOS Database Decryption

Decrypt WeChat's encrypted SQLCipher databases on macOS and export messages, contacts, and other data.

## Prerequisites

- macOS with WeChat 4.x installed and running (logged in)
- WeChat must be ad-hoc signed: `codesign --force --deep --sign - ~/Desktop/WeChat.app`
  (copy from /Applications first if SIP blocks signing there)
- `sqlcipher` CLI: `brew install sqlcipher`
- Tools located at `~/.agenticEvolve/tools/wechat-decrypt/`

## Tools

| Tool | Purpose |
|------|---------|
| `find_keys` | C binary — extract PRAGMA keys from WeChat process memory via Mach VM API |
| `find_keys_yl` | C binary — ylytdeng's proven scanner (backup) |
| `extract_key.py` | Python — combined PRAGMA scan + codec_ctx pointer chasing |
| `decrypt_db.py` | Python — decrypt all 16 SQLCipher DBs using extracted keys |
| `export_messages.py` | Python — read/search/export decrypted messages |

## Workflow

### Step 1: Extract Keys

```bash
cd ~/.agenticEvolve/tools/wechat-decrypt
sudo ./find_keys              # primary (C, both approaches)
# OR
sudo ./find_keys_yl           # backup (ylytdeng's proven scanner)
# OR
sudo python3 extract_key.py   # Python with codec_ctx fallback
```

Output: `wechat_keys.json` (array), `all_keys.json` (map for decrypt_db.py)

### Step 2: Decrypt Databases

```bash
python3 decrypt_db.py --output ./decrypted
```

Decrypts all 16 DB files to `./decrypted/` using HMAC-SHA512 verification.

### Step 3: Export Messages

```bash
# List conversations
python3 export_messages.py --list

# Export specific contact
python3 export_messages.py --contact "hichenyuxuan"

# Export specific group
python3 export_messages.py --group "49563067654@chatroom"

# Search messages
python3 export_messages.py --search "keyword"

# Recent N messages
python3 export_messages.py --recent 50

# Export all as JSON
python3 export_messages.py --all --format json -o messages.json

# Export all as CSV
python3 export_messages.py --all --format csv -o messages.csv
```

## Database Schema (macOS WeChat 4.x)

- **DB location**: `~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/<wxid>/db_storage/`
- **Encryption**: SQLCipher 4, AES-256-CBC, HMAC-SHA512, PBKDF2 256K iterations, 4096 page size
- **Message tables**: `Msg_<md5(username)>` — each table = one conversation
- **Name2Id**: Maps usernames to table hashes
- **Group messages**: Content format is `sender_wxid:\ncontent`

## Key DBs

| DB | Contents |
|----|----------|
| `message/message_0.db` | Chat messages |
| `contact/contact.db` | Contact list (870+ contacts) |
| `session/session.db` | Recent conversations |
| `sns/sns.db` | Moments/timeline |
| `favorite/favorite.db` | Saved favorites |

## Technical Notes

- Key extraction uses `mach_vm_region` (VM_REGION_BASIC_INFO_64), NOT `mach_vm_region_recurse`
- WCDB caches PRAGMA key string `x'<64 hex key><32 hex salt>'` in RW heap memory
- Salt = first 16 bytes of each .db file; matched against extracted key salts
- HMAC verification: PBKDF2(key, salt XOR 0x3A, 2 iters) → HMAC-SHA512 over page 1

Source: https://github.com/ylytdeng/wechat-decrypt + https://github.com/cocohahaha/wechat-decrypt-macos
