#!/bin/sh
# Native shell/install checks of actual signed release assets. Only the engine
# pull is simulated; signatures, network downloads and installed files are real.
# The actual linux/amd64 wallet runtime is accepted separately against its digest.
set -eu

die() { printf 'platform-check: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 3 ] || die "usage: check-wallet-platform.sh ASSETS VERSION SOURCE_COMMIT"
platform_assets=$(cd "$1" && pwd)
platform_version=$2
platform_commit=$3
printf '%s\n' "$platform_version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || die "invalid version"
printf '%s\n' "$platform_commit" | grep -Eq '^[0-9a-f]{40}$' || die "invalid source commit"
for name in install.sh rustok release.manifest release.manifest.sigstore.json; do
    [ -f "$platform_assets/$name" ] && [ ! -L "$platform_assets/$name" ] || die "missing or nonregular asset: $name"
done

platform_work=$(mktemp -d)
trap 'rm -rf "$platform_work"' EXIT
trap 'exit 1' HUP INT TERM
platform_identity="https://github.com/rustok-org/mcp/.github/workflows/release-shelf.yml@refs/tags/wallet-tui-v$platform_version"
platform_issuer=https://token.actions.githubusercontent.com
platform_manifest="$platform_assets/release.manifest"
platform_bundle="$platform_assets/release.manifest.sigstore.json"
cosign version
cosign verify-blob "$platform_manifest" --bundle "$platform_bundle" \
    --certificate-identity "$platform_identity" --certificate-oidc-issuer "$platform_issuer"
grep -qx "wallet_version=$platform_version" "$platform_manifest" || die "manifest version differs"
grep -qx "source_commit=$platform_commit" "$platform_manifest" || die "manifest source differs"
platform_image=$(sed -n 's/^image_ref=//p' "$platform_manifest")
printf '%s\n' "$platform_image" | grep -Eq '^ghcr\.io/rustok-org/rustok-wallet-tui@sha256:[0-9a-f]{64}$' || die "invalid image"
cosign verify "$platform_image" \
    --certificate-identity https://github.com/rustok-org/mcp/.github/workflows/wallet-publish.yml@refs/heads/main \
    --certificate-oidc-issuer "$platform_issuer"
if cosign verify-blob "$platform_manifest" --bundle "$platform_bundle" \
    --certificate-identity "${platform_identity}-wrong" --certificate-oidc-issuer "$platform_issuer"; then
    die "wrong signer identity was accepted"
fi

mkdir "$platform_work/engine"
cat > "$platform_work/engine/podman" <<'ENGINE'
#!/bin/sh
set -eu
[ "$#" -eq 2 ] && [ "$1" = pull ] && [ "$2" = "$RUSTOK_PLATFORM_IMAGE" ] || exit 1
printf '%s\n' "$*" >> "$RUSTOK_PLATFORM_LOG"
ENGINE
chmod +x "$platform_work/engine/podman"
platform_tools="$platform_work/engine"
platform_log="$platform_work/engine.log"
platform_home="$platform_work/home ' \$(touch INJECTED)"
mkdir "$platform_home"

run_install() {
    env -u RUSTOK_IMAGE -u RUSTOK_NO_MODIFY_PATH \
        HOME="$platform_home" XDG_DATA_HOME="$platform_home/data" SHELL=/bin/bash \
        PATH="$platform_tools:$PATH" RUSTOK_PLATFORM_IMAGE="$platform_image" \
        RUSTOK_PLATFORM_LOG="$platform_log" \
        sh "$1" --manifest "$2" --bundle "$platform_bundle" < /dev/null
}

run_install "$platform_assets/install.sh" "$platform_manifest"
platform_installed="$platform_home/.local/bin/rustok"
cmp "$platform_installed" "$platform_assets/rustok"
cmp "$platform_home/data/rustok/release.manifest" "$platform_manifest"
grep -qx "pull $platform_image" "$platform_log" || die "installer did not request the verified digest"
[ "$(wc -l < "$platform_log" | tr -d ' ')" -eq 1 ] || die "unexpected engine effects"
# The child shell must expand HOME after receiving the isolated test environment.
# shellcheck disable=SC2016
env HOME="$platform_home" XDG_DATA_HOME="$platform_home/data" \
    sh -c '. "$HOME/.bashrc"; command -v rustok; rustok version' > "$platform_work/version.log"
cat "$platform_work/version.log"
grep -qF "wallet selected $platform_version ($platform_image)" "$platform_work/version.log" || die "installed selection differs"
[ ! -e INJECTED ] && [ ! -e "$platform_work/INJECTED" ] || die "profile executed path contents"
printf '%s\n' 'PASS native signed installation, immutable selection and quoted PATH'

expect_refusal() {
    platform_reason=$1
    shift
    if run_install "$@" > "$platform_work/refusal.log" 2>&1; then
        die "invalid installation succeeded: $platform_reason"
    fi
    cat "$platform_work/refusal.log"
    grep -qF "$platform_reason" "$platform_work/refusal.log" || die "refusal failed for another reason"
    cmp "$platform_installed" "$platform_assets/rustok"
    cmp "$platform_home/data/rustok/release.manifest" "$platform_manifest"
    [ "$(wc -l < "$platform_log" | tr -d ' ')" -eq 1 ] || die "refused install reached engine"
}

cp "$platform_manifest" "$platform_work/invalid.manifest"
printf '%s\n' 'unexpected=field' >> "$platform_work/invalid.manifest"
expect_refusal 'unknown release manifest field' "$platform_assets/install.sh" "$platform_work/invalid.manifest"
sed "s/^source_commit=./source_commit=G/" "$platform_manifest" > "$platform_work/unsigned.manifest"
expect_refusal 'invalid source commit' "$platform_assets/install.sh" "$platform_work/unsigned.manifest"
# Change a valid field, so the real cryptographic rejection is observed after parsing.
sed "s/^installer_sha256=./installer_sha256=f/" "$platform_manifest" > "$platform_work/tampered.manifest"
if cmp -s "$platform_manifest" "$platform_work/tampered.manifest"; then
    sed "s/^installer_sha256=./installer_sha256=0/" "$platform_manifest" > "$platform_work/tampered.manifest"
fi
expect_refusal 'signature verification failed' "$platform_assets/install.sh" "$platform_work/tampered.manifest"
cp "$platform_assets/install.sh" "$platform_work/tampered-install.sh"
printf '\n# changed bytes\n' >> "$platform_work/tampered-install.sh"
expect_refusal 'installer bytes do not match' "$platform_work/tampered-install.sh" "$platform_manifest"

mkdir "$platform_work/old-verifier"
cat > "$platform_work/old-verifier/cosign" <<'OLD'
#!/bin/sh
[ "$1" = version ] || exit 1
printf '%s\n' 'GitVersion: v2.6.0'
OLD
chmod +x "$platform_work/old-verifier/cosign"
platform_tools="$platform_work/old-verifier:$platform_work/engine"
expect_refusal 'cosign 3+ is required' "$platform_assets/install.sh" "$platform_manifest"
printf '%s\n' 'PASS native manifest/signature/hash/old-verifier refusals preserve installed bytes'

# A corrupt installed record must fail before normal selection can continue.
cp "$platform_work/invalid.manifest" "$platform_home/data/rustok/release.manifest"
if env HOME="$platform_home" XDG_DATA_HOME="$platform_home/data" sh "$platform_installed" version; then
    die "corrupt installed manifest was accepted"
fi
printf '%s\n' 'PASS native installed-manifest refusal'
uname -a
printf 'platform-check: complete for %s, source %s, image %s\n' "$platform_version" "$platform_commit" "$platform_image"
