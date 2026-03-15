#!/bin/bash
# agenticEvolve installer
# Usage: curl -fsSL https://raw.githubusercontent.com/outsmartchad/agenticEvolve/main/scripts/install.sh | bash
set -euo pipefail

EXODIR="$HOME/.agenticEvolve"
REPO="https://github.com/outsmartchad/agenticEvolve.git"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    agenticEvolve — installer         ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── Prerequisites ──────────────────────────────────────────
MISSING=0

if ! command -v python3 &>/dev/null; then
    echo "  [!!] Python 3 not found. Install: https://python.org"
    MISSING=1
fi

if ! command -v git &>/dev/null; then
    echo "  [!!] git not found."
    MISSING=1
fi

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "  Install missing prerequisites and re-run."
    exit 1
fi

# ── Clone / Update ─────────────────────────────────────────
if [ -d "$EXODIR/.git" ]; then
    echo "  Updating existing installation..."
    git -C "$EXODIR" pull --ff-only 2>/dev/null || true
else
    echo "  Cloning agenticEvolve..."
    git clone "$REPO" "$EXODIR"
fi

# ── Python deps ────────────────────────────────────────────
echo "  Installing dependencies..."
pip install -r "$EXODIR/requirements.txt" -q 2>/dev/null || pip3 install -r "$EXODIR/requirements.txt" -q 2>/dev/null || true

# ── Add ae to PATH ─────────────────────────────────────────
chmod +x "$EXODIR/ae"

# Detect shell rc file
SHELL_RC=""
if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "$SHELL")" = "zsh" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "${BASH_VERSION:-}" ] || [ "$(basename "$SHELL")" = "bash" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

# Check if already on PATH
if command -v ae &>/dev/null; then
    echo "  [OK] ae already on PATH"
elif [ -n "$SHELL_RC" ]; then
    # Add to shell rc
    if ! grep -q 'agenticEvolve' "$SHELL_RC" 2>/dev/null; then
        echo '' >> "$SHELL_RC"
        echo '# agenticEvolve' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.agenticEvolve:$PATH"' >> "$SHELL_RC"
        echo "  [OK] Added ae to PATH in $(basename "$SHELL_RC")"
    else
        echo "  [OK] PATH entry exists in $(basename "$SHELL_RC")"
    fi
    export PATH="$EXODIR:$PATH"
else
    echo "  [--] Could not detect shell rc file."
    echo "       Add this to your shell profile:"
    echo "       export PATH=\"\$HOME/.agenticEvolve:\$PATH\""
    export PATH="$EXODIR:$PATH"
fi

# ── Check Claude Code ──────────────────────────────────────
echo ""
if command -v claude &>/dev/null; then
    echo "  [OK] Claude Code installed"
else
    echo "  [!!] Claude Code not found — install it to use the agent:"
    echo "       npm install -g @anthropic-ai/claude-code"
    echo "       claude   # authenticate"
fi

# ── Run setup wizard ───────────────────────────────────────
echo ""
echo "  Running setup wizard..."
echo ""
"$EXODIR/ae" setup

# ── Done ───────────────────────────────────────────────────
echo ""
if [ -n "$SHELL_RC" ]; then
    echo "  Reload your shell to use the ae command:"
    echo "    source ~/${SHELL_RC##*/}"
fi
echo ""
