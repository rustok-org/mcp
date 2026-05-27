#!/usr/bin/env bash
set -euo pipefail

# Install rustok-agent-mcp from GitHub Releases
# Usage: curl -fsSL https://raw.githubusercontent.com/rustok-org/mcp/main/scripts/install.sh | bash

REPO="rustok-org/mcp"
BINARY="rustok-agent-mcp"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

# Detect OS
OS=$(uname -s)
case "$OS" in
    Linux*)     PLATFORM="linux" ;;
    Darwin*)    PLATFORM="darwin" ;;
    MINGW*|MSYS*|CYGWIN*)
        PLATFORM="windows"
        ;;
    *)
        echo "Unsupported OS: $OS"
        exit 1
        ;;
esac

# Detect architecture
ARCH=$(uname -m)
case "$ARCH" in
    x86_64|amd64)   ARCH_TARGET="x86_64" ;;
    arm64|aarch64)  ARCH_TARGET="aarch64" ;;
    *)
        echo "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

# Map platform/arch to artifact name
if [ "$PLATFORM" = "linux" ] && [ "$ARCH_TARGET" = "x86_64" ]; then
    ARTIFACT="${BINARY}-x86_64-linux"
    EXT="tar.gz"
elif [ "$PLATFORM" = "linux" ] && [ "$ARCH_TARGET" = "aarch64" ]; then
    ARTIFACT="${BINARY}-aarch64-linux"
    EXT="tar.gz"
elif [ "$PLATFORM" = "darwin" ] && [ "$ARCH_TARGET" = "aarch64" ]; then
    ARTIFACT="${BINARY}-aarch64-darwin"
    EXT="tar.gz"
elif [ "$PLATFORM" = "darwin" ] && [ "$ARCH_TARGET" = "x86_64" ]; then
    ARTIFACT="${BINARY}-x86_64-darwin"
    EXT="tar.gz"
elif [ "$PLATFORM" = "windows" ] && [ "$ARCH_TARGET" = "x86_64" ]; then
    ARTIFACT="${BINARY}-x86_64-windows"
    EXT="zip"
else
    echo "No prebuilt binary available for ${PLATFORM}/${ARCH_TARGET}"
    echo "Supported: linux/x86_64, linux/arm64, macos/arm64, macos/x86_64, windows/x86_64"
    exit 1
fi

# Fetch latest release tag from GitHub API
echo "Fetching latest release..."
LATEST_URL="https://api.github.com/repos/${REPO}/releases/latest"

CURL_ARGS=(-fsSL)
if [ -n "${GITHUB_TOKEN:-}" ]; then
    CURL_ARGS+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi

if command -v python3 >/dev/null 2>&1; then
    TAG=$(curl "${CURL_ARGS[@]}" "$LATEST_URL" | python3 -c "import sys, json; print(json.load(sys.stdin)['tag_name'])")
else
    TAG=$(curl "${CURL_ARGS[@]}" "$LATEST_URL" | grep -o '"tag_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n 1 | sed 's/.*"\([^"]*\)".*/\1/')
fi

if [ -z "$TAG" ]; then
    echo "Failed to determine latest release."
    exit 1
fi

echo "Latest release: ${TAG}"

# Download URL
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${TAG}/${ARTIFACT}.${EXT}"
CHECKSUM_URL="https://github.com/${REPO}/releases/download/${TAG}/${ARTIFACT}.${EXT}.sha256"

# Create temp directory
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Downloading ${ARTIFACT}.${EXT}..."
curl -fsSL -o "${TMP_DIR}/${ARTIFACT}.${EXT}" "$DOWNLOAD_URL"

# Verify checksum
echo "Verifying checksum..."
if curl -fsSL -o "${TMP_DIR}/${ARTIFACT}.${EXT}.sha256" "$CHECKSUM_URL" 2>/dev/null; then
    cd "$TMP_DIR"
    EXPECTED=$(awk '{print $1}' "${ARTIFACT}.${EXT}.sha256" | tr '[:upper:]' '[:lower:]')
    if command -v sha256sum >/dev/null 2>&1; then
        ACTUAL=$(sha256sum "${ARTIFACT}.${EXT}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
    elif command -v shasum >/dev/null 2>&1; then
        ACTUAL=$(shasum -a 256 "${ARTIFACT}.${EXT}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
    else
        echo "Warning: no sha256 tool found, skipping checksum verification"
        ACTUAL=""
    fi
    if [ -n "$ACTUAL" ] && [ "$EXPECTED" != "$ACTUAL" ]; then
        echo "Checksum mismatch! Expected: $EXPECTED, got: $ACTUAL"
        exit 1
    fi
    if [ -n "$ACTUAL" ]; then
        echo "Checksum OK"
    fi
else
    echo "Warning: checksum file not found, skipping verification"
fi

# Extract
echo "Extracting..."
if [ "$EXT" = "tar.gz" ]; then
    tar xzf "${ARTIFACT}.${EXT}"
else
    unzip -q "${ARTIFACT}.${EXT}"
fi

# Install
mkdir -p "$INSTALL_DIR"

if [ "$PLATFORM" = "windows" ]; then
    cp "${BINARY}.exe" "$INSTALL_DIR/"
    INSTALLED_PATH="${INSTALL_DIR}/${BINARY}.exe"
else
    cp "$BINARY" "$INSTALL_DIR/"
    chmod +x "${INSTALL_DIR}/${BINARY}"
    INSTALLED_PATH="${INSTALL_DIR}/${BINARY}"
fi

# Verify
echo "Verifying installation..."
if "$INSTALLED_PATH" --help >/dev/null 2>&1; then
    echo ""
    echo "✅ ${BINARY} installed to ${INSTALLED_PATH}"
    echo ""
    echo "Version:"
    "$INSTALLED_PATH" --version 2>/dev/null || "$INSTALLED_PATH" --help | head -n 3
    echo ""
    echo "Next steps:"
    echo "  1. Ensure ${INSTALL_DIR} is in your PATH:"
    echo "     export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    echo "  2. Set your wallet password:"
    echo "     export RUSTOK_AGENT_PASSWORD=\"your-strong-password\""
    echo "  3. Run with stdio (Claude Desktop):"
    echo "     ${BINARY} --transport stdio"
    echo "  4. Or run HTTP server:"
    echo "     ${BINARY} --transport http"
else
    echo "❌ Installation verification failed."
    exit 1
fi
