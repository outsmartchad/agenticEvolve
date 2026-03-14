/*
 * find_keys.c — Extract SQLCipher encryption keys from WeChat process memory on macOS
 *
 * Approach A: Scan WeChat's RW memory regions for the PRAGMA key string
 *   x'<64 hex key><32 hex salt>' (96 hex chars = 48 bytes) cached by WCDB.
 *
 * Approach B (fallback): Find raw 16-byte DB salt in memory, then search
 *   nearby memory for high-entropy 32-byte key candidates.
 *
 * Uses mach_vm_region (VM_REGION_BASIC_INFO_64), proven to work on macOS.
 * Adapted from ylytdeng/wechat-decrypt (2k stars).
 *
 * Usage:
 *   cc -O2 -o find_keys find_keys.c -framework Foundation
 *   sudo ./find_keys              # auto-find WeChat PID
 *   sudo ./find_keys <pid>        # specify PID
 *
 * Prerequisites:
 *   codesign --force --deep --sign - ~/Desktop/WeChat.app
 *   (or wherever WeChat is ad-hoc signed)
 *
 * Output: wechat_keys.json  (array of key objects)
 *         all_keys.json     (map of db_name -> enc_key, for decrypt_db.py)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>
#include <unistd.h>
#include <dirent.h>
#include <pwd.h>
#include <sys/stat.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <libproc.h>

/* ── Constants ── */
#define HEX_PATTERN_LEN 96   /* 64 hex (key) + 32 hex (salt) */
#define MIN_HEX_LEN     64
#define MAX_HEX_LEN     192
#define CHUNK_SIZE       (2 * 1024 * 1024)
#define MAX_KEYS         256
#define MAX_DBS          256

/* ── Key entry ── */
typedef struct {
    char key_hex[65];     /* 32-byte key as 64 hex chars + null */
    char salt_hex[33];    /* 16-byte salt as 32 hex chars + null */
    char full_pragma[200]; /* x'<key><salt>' */
    mach_vm_address_t addr;
    int  method;           /* 0=pragma scan, 1=salt-proximity */
} KeyEntry;

static KeyEntry g_keys[MAX_KEYS];
static int g_key_count = 0;

/* ── DB salt registry ── */
typedef struct {
    char salt_hex[33];
    char name[256];
    char full_path[1024];
    unsigned char salt_raw[16];
} DbEntry;

static DbEntry g_dbs[MAX_DBS];
static int g_db_count = 0;

/* ── Helpers ── */
static int is_hex_char(unsigned char c) {
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

static void to_lower(char *s) {
    for (; *s; s++)
        if (*s >= 'A' && *s <= 'F') *s += 32;
}

static pid_t find_wechat_pid(void) {
    FILE *fp = popen("pgrep -x WeChat", "r");
    if (!fp) return -1;
    char buf[64];
    pid_t pid = -1;
    if (fgets(buf, sizeof(buf), fp)) pid = atoi(buf);
    pclose(fp);
    return pid;
}

/* Shannon entropy of raw bytes */
static double byte_entropy(const unsigned char *data, size_t len) {
    int freq[256] = {0};
    for (size_t i = 0; i < len; i++) freq[data[i]]++;
    double ent = 0.0;
    for (int i = 0; i < 256; i++) {
        if (freq[i] == 0) continue;
        double p = (double)freq[i] / len;
        ent -= p * log2(p);
    }
    return ent;
}

/* Check if 32 bytes look like a plausible AES key (high entropy, not ASCII) */
static int is_plausible_key(const unsigned char *data, size_t len) {
    if (len < 32) return 0;
    if (byte_entropy(data, 32) < 3.5) return 0;
    int ascii = 0;
    for (int i = 0; i < 32; i++)
        if (data[i] >= 0x20 && data[i] <= 0x7E) ascii++;
    return ascii <= 24;
}

/* ── DB file collection ── */
static int read_db_salt(const char *path, unsigned char *salt_raw, char *salt_hex) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    unsigned char header[16];
    if (fread(header, 1, 16, f) != 16) { fclose(f); return -1; }
    fclose(f);
    /* Skip unencrypted SQLite databases */
    if (memcmp(header, "SQLite format 3", 15) == 0) return -1;
    memcpy(salt_raw, header, 16);
    for (int i = 0; i < 16; i++) sprintf(salt_hex + i * 2, "%02x", header[i]);
    salt_hex[32] = '\0';
    return 0;
}

static void collect_dbs_in_dir(const char *dir_path) {
    DIR *d = opendir(dir_path);
    if (!d) return;
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL) {
        if (ent->d_name[0] == '.') continue;
        char full[1024];
        snprintf(full, sizeof(full), "%s/%s", dir_path, ent->d_name);
        struct stat st;
        if (stat(full, &st) != 0) continue;
        if (S_ISDIR(st.st_mode)) {
            collect_dbs_in_dir(full); /* recurse */
        } else if (S_ISREG(st.st_mode)) {
            size_t nlen = strlen(ent->d_name);
            if (nlen < 3 || strcmp(ent->d_name + nlen - 3, ".db") != 0) continue;
            if (g_db_count >= MAX_DBS) continue;
            DbEntry *e = &g_dbs[g_db_count];
            if (read_db_salt(full, e->salt_raw, e->salt_hex) != 0) continue;
            /* Extract relative name from db_storage/ */
            const char *rel = strstr(full, "db_storage/");
            if (rel) rel += strlen("db_storage/");
            else rel = ent->d_name;
            strncpy(e->name, rel, sizeof(e->name) - 1);
            strncpy(e->full_path, full, sizeof(e->full_path) - 1);
            fprintf(stderr, "  %s: salt=%s\n", e->name, e->salt_hex);
            g_db_count++;
        }
    }
    closedir(d);
}

static void collect_all_dbs(void) {
    const char *home = getenv("HOME");
    const char *sudo_user = getenv("SUDO_USER");
    if (sudo_user) {
        struct passwd *pw = getpwnam(sudo_user);
        if (pw && pw->pw_dir) home = pw->pw_dir;
    }
    if (!home) home = "/root";

    char base[512];
    snprintf(base, sizeof(base),
        "%s/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files", home);

    fprintf(stderr, "[*] Scanning for DB files under %s\n", base);
    DIR *d = opendir(base);
    if (!d) { fprintf(stderr, "[-] Cannot open %s\n", base); return; }
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL) {
        if (ent->d_name[0] == '.') continue;
        char storage[768];
        snprintf(storage, sizeof(storage), "%s/%s/db_storage", base, ent->d_name);
        struct stat st;
        if (stat(storage, &st) == 0 && S_ISDIR(st.st_mode))
            collect_dbs_in_dir(storage);
    }
    closedir(d);
    fprintf(stderr, "[*] Found %d encrypted DB files\n", g_db_count);
}

/* ── Key deduplication ── */
static int key_already_found(const char *key_hex, const char *salt_hex) {
    for (int i = 0; i < g_key_count; i++) {
        if (strcmp(g_keys[i].key_hex, key_hex) == 0) {
            if (salt_hex[0] == '\0' || g_keys[i].salt_hex[0] == '\0') return 1;
            if (strcmp(g_keys[i].salt_hex, salt_hex) == 0) return 1;
        }
    }
    return 0;
}

static void add_key(const char *key_hex, const char *salt_hex,
                    mach_vm_address_t addr, int method) {
    if (g_key_count >= MAX_KEYS) return;
    if (key_already_found(key_hex, salt_hex)) return;
    KeyEntry *e = &g_keys[g_key_count];
    strncpy(e->key_hex, key_hex, 64); e->key_hex[64] = '\0';
    strncpy(e->salt_hex, salt_hex, 32); e->salt_hex[32] = '\0';
    snprintf(e->full_pragma, sizeof(e->full_pragma), "x'%s%s'",
             e->key_hex, e->salt_hex);
    e->addr = addr;
    e->method = method;
    g_key_count++;
    fprintf(stderr, "[+] Key #%d at 0x%llx (method=%s)\n",
            g_key_count, addr, method == 0 ? "pragma" : "salt-proximity");
}

/* ── Memory region enumeration (proven mach_vm_region approach) ── */
typedef struct {
    mach_vm_address_t base;
    mach_vm_size_t    size;
    int               protection;
} MemRegion;

#define MAX_REGIONS 65536
static MemRegion g_regions[MAX_REGIONS];
static int g_region_count = 0;

static void enumerate_regions(mach_port_t task) {
    mach_vm_address_t addr = 0;
    while (g_region_count < MAX_REGIONS) {
        mach_vm_size_t size = 0;
        vm_region_basic_info_data_64_t info;
        mach_msg_type_number_t info_count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t obj_name;

        kern_return_t kr = mach_vm_region(task, &addr, &size,
            VM_REGION_BASIC_INFO_64, (vm_region_info_t)&info,
            &info_count, &obj_name);
        if (kr != KERN_SUCCESS) break;
        if (size == 0) { addr++; continue; }

        g_regions[g_region_count].base = addr;
        g_regions[g_region_count].size = size;
        g_regions[g_region_count].protection = info.protection;
        g_region_count++;
        addr += size;
    }
    fprintf(stderr, "[*] Enumerated %d memory regions\n", g_region_count);
}

/* ── Approach A: Scan for x'<hex>' PRAGMA key strings ── */
static void scan_pragma_keys(mach_port_t task) {
    fprintf(stderr, "\n[*] Approach A: Scanning for x'<hex>' PRAGMA key strings...\n");
    size_t total_scanned = 0;
    int rw_regions = 0;

    for (int r = 0; r < g_region_count; r++) {
        int prot = g_regions[r].protection;
        /* Scan RW regions (where WCDB stores the PRAGMA string) */
        if ((prot & (VM_PROT_READ | VM_PROT_WRITE)) != (VM_PROT_READ | VM_PROT_WRITE))
            continue;
        mach_vm_address_t base = g_regions[r].base;
        mach_vm_size_t    rsize = g_regions[r].size;
        if (rsize > 500 * 1024 * 1024) continue;
        rw_regions++;

        mach_vm_address_t ca = base;
        while (ca < base + rsize) {
            mach_vm_size_t cs = base + rsize - ca;
            if (cs > CHUNK_SIZE) cs = CHUNK_SIZE;

            vm_offset_t data;
            mach_msg_type_number_t dc;
            kern_return_t kr = mach_vm_read(task, ca, cs, &data, &dc);
            if (kr == KERN_SUCCESS) {
                unsigned char *buf = (unsigned char *)data;
                total_scanned += dc;

                /* Strict 96-char scan (ylytdeng approach) */
                for (size_t i = 0; i + HEX_PATTERN_LEN + 3 < dc; i++) {
                    if (buf[i] != 'x' || buf[i + 1] != '\'') continue;
                    int valid = 1;
                    for (int j = 0; j < HEX_PATTERN_LEN; j++) {
                        if (!is_hex_char(buf[i + 2 + j])) { valid = 0; break; }
                    }
                    if (!valid) continue;
                    if (buf[i + 2 + HEX_PATTERN_LEN] != '\'') continue;

                    char key_hex[65], salt_hex[33];
                    memcpy(key_hex, buf + i + 2, 64); key_hex[64] = '\0';
                    memcpy(salt_hex, buf + i + 2 + 64, 32); salt_hex[32] = '\0';
                    to_lower(key_hex);
                    to_lower(salt_hex);

                    add_key(key_hex, salt_hex, ca + i, 0);
                }

                /* Flexible scan: x'<64-192 hex>' (catch key-only or extended) */
                for (size_t i = 0; i + 4 < dc; i++) {
                    if (buf[i] != 'x' || buf[i + 1] != '\'') continue;
                    size_t hex_len = 0;
                    while (i + 2 + hex_len < dc && is_hex_char(buf[i + 2 + hex_len]))
                        if (++hex_len > MAX_HEX_LEN) break;
                    if (hex_len < MIN_HEX_LEN || hex_len > MAX_HEX_LEN) continue;
                    if (hex_len == HEX_PATTERN_LEN) continue; /* already caught above */
                    if (i + 2 + hex_len >= dc || buf[i + 2 + hex_len] != '\'') continue;

                    char key_hex[65] = {0}, salt_hex[33] = {0};
                    memcpy(key_hex, buf + i + 2, 64); key_hex[64] = '\0';
                    to_lower(key_hex);
                    if (hex_len >= 96) {
                        /* Last 32 hex chars = salt */
                        memcpy(salt_hex, buf + i + 2 + hex_len - 32, 32);
                        salt_hex[32] = '\0';
                        to_lower(salt_hex);
                    }
                    add_key(key_hex, salt_hex, ca + i, 0);
                    i += 2 + hex_len;
                }

                mach_vm_deallocate(mach_task_self(), data, dc);
            }
            /* Overlap to catch boundary-spanning patterns */
            if (cs > HEX_PATTERN_LEN + 3)
                ca += cs - (HEX_PATTERN_LEN + 3);
            else
                ca += cs;
        }
    }
    fprintf(stderr, "[*] Approach A: scanned %d RW regions, %.1f MB, found %d keys so far\n",
            rw_regions, total_scanned / (1024.0 * 1024.0), g_key_count);
}

/* ── Approach B: Salt-proximity key search ── */
static void scan_salt_proximity(mach_port_t task) {
    if (g_db_count == 0) return;
    fprintf(stderr, "\n[*] Approach B: Searching for raw DB salts in memory...\n");

    /* For each DB salt, find it in RW memory */
    for (int d = 0; d < g_db_count; d++) {
        unsigned char *salt = g_dbs[d].salt_raw;
        int salt_found = 0;

        for (int r = 0; r < g_region_count; r++) {
            int prot = g_regions[r].protection;
            if (!(prot & VM_PROT_READ)) continue;
            mach_vm_address_t base = g_regions[r].base;
            mach_vm_size_t rsize = g_regions[r].size;
            if (rsize > 200 * 1024 * 1024) continue;

            mach_vm_address_t ca = base;
            while (ca < base + rsize) {
                mach_vm_size_t cs = base + rsize - ca;
                if (cs > CHUNK_SIZE) cs = CHUNK_SIZE;

                vm_offset_t data;
                mach_msg_type_number_t dc;
                kern_return_t kr = mach_vm_read(task, ca, cs, &data, &dc);
                if (kr != KERN_SUCCESS) { ca += cs; continue; }

                unsigned char *buf = (unsigned char *)data;
                /* Find salt occurrences */
                for (size_t i = 0; i + 16 <= dc; i++) {
                    if (memcmp(buf + i, salt, 16) != 0) continue;
                    mach_vm_address_t salt_addr = ca + i;
                    salt_found++;

                    /* Check nearby offsets for key-like data */
                    int offsets[] = {-128, -96, -64, -32, 32, 64, 96, 128,
                                    -256, -192, 192, 256};
                    for (int o = 0; o < 12; o++) {
                        mach_vm_address_t check_addr = salt_addr + offsets[o];
                        vm_offset_t kdata;
                        mach_msg_type_number_t kdc;
                        kr = mach_vm_read(task, check_addr, 32, &kdata, &kdc);
                        if (kr != KERN_SUCCESS || kdc < 32) continue;
                        if (is_plausible_key((unsigned char *)kdata, kdc)) {
                            char key_hex[65];
                            for (int b = 0; b < 32; b++)
                                sprintf(key_hex + b * 2, "%02x",
                                        ((unsigned char *)kdata)[b]);
                            key_hex[64] = '\0';
                            add_key(key_hex, g_dbs[d].salt_hex, salt_addr, 1);
                        }
                        mach_vm_deallocate(mach_task_self(), kdata, kdc);
                    }
                }
                mach_vm_deallocate(mach_task_self(), data, dc);
                ca += (cs > 16 ? cs - 16 : cs);
            }
        }
        if (salt_found > 0) {
            fprintf(stderr, "  %s: salt found %d times in memory\n",
                    g_dbs[d].name, salt_found);
        }
    }
    fprintf(stderr, "[*] Approach B complete, total keys: %d\n", g_key_count);
}

/* ── Output ── */
static void write_keys_json(void) {
    /* Array format: wechat_keys.json */
    FILE *f = fopen("wechat_keys.json", "w");
    if (!f) { perror("fopen wechat_keys.json"); return; }
    fprintf(f, "[\n");
    for (int i = 0; i < g_key_count; i++) {
        /* Find matching DB */
        const char *db_name = "(unknown)";
        for (int j = 0; j < g_db_count; j++) {
            if (g_keys[i].salt_hex[0] &&
                strcmp(g_keys[i].salt_hex, g_dbs[j].salt_hex) == 0) {
                db_name = g_dbs[j].name;
                break;
            }
        }
        fprintf(f, "  {\n");
        fprintf(f, "    \"key\": \"%s\",\n", g_keys[i].key_hex);
        fprintf(f, "    \"salt\": \"%s\",\n", g_keys[i].salt_hex);
        fprintf(f, "    \"pragma\": \"%s\",\n", g_keys[i].full_pragma);
        fprintf(f, "    \"db\": \"%s\",\n", db_name);
        fprintf(f, "    \"method\": \"%s\",\n",
                g_keys[i].method == 0 ? "pragma" : "salt-proximity");
        fprintf(f, "    \"addr\": \"0x%llx\"\n", g_keys[i].addr);
        fprintf(f, "  }%s\n", (i < g_key_count - 1) ? "," : "");
    }
    fprintf(f, "]\n");
    fclose(f);

    /* Map format: all_keys.json (for decrypt_db.py compatibility) */
    f = fopen("all_keys.json", "w");
    if (!f) { perror("fopen all_keys.json"); return; }
    fprintf(f, "{\n");
    int first = 1;
    for (int i = 0; i < g_key_count; i++) {
        for (int j = 0; j < g_db_count; j++) {
            if (g_keys[i].salt_hex[0] &&
                strcmp(g_keys[i].salt_hex, g_dbs[j].salt_hex) == 0) {
                fprintf(f, "%s  \"%s\": {\"enc_key\": \"%s\"}",
                        first ? "" : ",\n", g_dbs[j].name, g_keys[i].key_hex);
                first = 0;
            }
        }
    }
    fprintf(f, "\n}\n");
    fclose(f);
}

/* ── Main ── */
int main(int argc, char **argv) {
    pid_t pid;
    if (argc > 1)
        pid = atoi(argv[1]);
    else {
        pid = find_wechat_pid();
        if (pid <= 0) {
            fprintf(stderr, "[-] WeChat not running. Launch it first.\n");
            return 1;
        }
    }

    fprintf(stderr, "============================================================\n");
    fprintf(stderr, "  WeChat macOS Memory Key Scanner\n");
    fprintf(stderr, "============================================================\n");
    fprintf(stderr, "[*] WeChat PID: %d\n", pid);

    /* Get task port */
    mach_port_t task;
    kern_return_t kr = task_for_pid(mach_task_self(), pid, &task);
    if (kr != KERN_SUCCESS) {
        fprintf(stderr, "[-] task_for_pid failed: %d (%s)\n",
                kr, mach_error_string(kr));
        fprintf(stderr, "    Ensure:\n");
        fprintf(stderr, "    1. Running as root (sudo)\n");
        fprintf(stderr, "    2. WeChat is ad-hoc signed:\n");
        fprintf(stderr, "       codesign --force --deep --sign - ~/Desktop/WeChat.app\n");
        return 1;
    }
    fprintf(stderr, "[*] Got task port: %u\n", task);

    /* Collect DB salts */
    collect_all_dbs();

    /* Enumerate memory regions */
    enumerate_regions(task);

    /* Approach A: PRAGMA key string scan */
    scan_pragma_keys(task);

    /* Approach B: Salt-proximity search (always run for additional keys) */
    scan_salt_proximity(task);

    /* Summary */
    fprintf(stderr, "\n============================================================\n");
    fprintf(stderr, "[*] Total unique keys found: %d\n", g_key_count);

    if (g_key_count > 0) {
        /* Match keys to DBs */
        fprintf(stderr, "\n%-25s %-66s %s\n", "Database", "Key", "Method");
        fprintf(stderr, "%-25s %-66s %s\n",
            "-------------------------",
            "------------------------------------------------------------------",
            "--------");
        int matched = 0;
        for (int i = 0; i < g_key_count; i++) {
            const char *db = "(no match)";
            for (int j = 0; j < g_db_count; j++) {
                if (g_keys[i].salt_hex[0] &&
                    strcmp(g_keys[i].salt_hex, g_dbs[j].salt_hex) == 0) {
                    db = g_dbs[j].name;
                    matched++;
                    break;
                }
            }
            fprintf(stderr, "%-25s %-66s %s\n",
                    db, g_keys[i].key_hex,
                    g_keys[i].method == 0 ? "pragma" : "salt");
        }
        fprintf(stderr, "\n[*] Matched %d keys to known DBs\n", matched);

        write_keys_json();
        fprintf(stderr, "[+] Written: wechat_keys.json, all_keys.json\n");
    } else {
        fprintf(stderr, "\n[-] No keys found. Possible causes:\n");
        fprintf(stderr, "    1. WeChat not fully loaded / not logged in\n");
        fprintf(stderr, "    2. WeChat version uses different key storage\n");
        fprintf(stderr, "    3. Try scanning WeChatAppEx processes too\n");
        fprintf(stderr, "    4. Try the codec_ctx pointer-chasing approach\n");
    }

    return g_key_count > 0 ? 0 : 2;
}
