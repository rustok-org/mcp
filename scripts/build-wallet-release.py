#!/usr/bin/env python3
"""Build release assets from the final checkout, without a self-referencing commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUER = "https://token.actions.githubusercontent.com"
IMAGE_REPO = "ghcr.io/rustok-org/rustok-wallet-tui"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def constant(text: str, name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing release constant {name}")
    return match.group(1)


def build(output: Path, version: str, commit: str, *, package: bool, check: bool = False) -> None:
    """Generate a manifest first; package only after its real signature verifies."""
    output = output.resolve()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("expected X.Y.Z")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("expected full lowercase source commit")
    installer = ROOT / "scripts/install.sh"
    shim = ROOT / "cli/rustok"
    text = installer.read_text(encoding="utf-8")
    if constant(text, "WALLET_VERSION") != version:
        raise ValueError("tag and installer version differ")
    image_digest = constant(text, "WALLET_DIGEST")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
        raise ValueError("unfilled image digest")
    if constant(text, "SHIM_SHA256") != digest(shim):
        raise ValueError("unfilled shim checksum")
    fields = {
        "format": "rustok-wallet-release-v1",
        "wallet_version": version,
        "source_commit": commit,
        "image_ref": f"{IMAGE_REPO}@{image_digest}",
        "installer_sha256": digest(installer),
        "shim_sha256": digest(shim),
    }
    manifest = "".join(f"{key}={value}\n" for key, value in fields.items()).encode("ascii")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "release.manifest"
    if not package and not check:
        manifest_path.write_bytes(manifest)
        shutil.copyfile(installer, output / "install.sh")
        shutil.copyfile(shim, output / "rustok")
        return
    if manifest_path.read_bytes() != manifest:
        raise ValueError("signed manifest differs from final checkout")
    if digest(output / "install.sh") != fields["installer_sha256"]:
        raise ValueError("installer asset differs from signed manifest")
    if digest(output / "rustok") != fields["shim_sha256"]:
        raise ValueError("shim asset differs from signed manifest")
    identity = (
        "https://github.com/rustok-org/mcp/.github/workflows/"
        f"release-shelf.yml@refs/tags/wallet-tui-v{version}"
    )
    cosign = shutil.which("cosign")
    if cosign is None:
        raise ValueError("trusted cosign is required to package a signed release")
    # Fixed executable, validated identity and absolute file arguments; no shell.
    subprocess.run(  # noqa: S603
        [
            cosign,
            "verify-blob",
            str(manifest_path),
            "--bundle",
            str(output / "release.manifest.sigstore.json"),
            "--certificate-identity",
            identity,
            "--certificate-oidc-issuer",
            ISSUER,
        ],
        check=True,
    )
    skill_path = ROOT / "skills/rustok-wallet-tui/SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    if skill.count("@INSTALLER_SHA256@") != 1:
        raise ValueError("skill must carry exactly one bootstrap hash placeholder")
    skill = skill.replace("@INSTALLER_SHA256@", fields["installer_sha256"])
    metadata = (ROOT / "skills/rustok-wallet-tui/claw.json").read_bytes()
    if json.loads(metadata)["version"] != version:
        raise ValueError("skill metadata version differs from release")
    if check:
        if (output / "SKILL.md").read_bytes() != skill.encode("utf-8"):
            raise ValueError("published bootstrap differs from final checkout")
        expected = {
            "SKILL.md": skill.encode("utf-8"),
            "claw.json": metadata,
            **{
                name: (output / name).read_bytes()
                for name in ("install.sh", "release.manifest", "release.manifest.sigstore.json")
            },
        }
        with zipfile.ZipFile(output / "wallet-skill.zip") as archive:
            if sorted(archive.namelist()) != sorted(expected):
                raise ValueError("skill archive has missing, duplicate or unexpected members")
            if any(archive.read(name) != data for name, data in expected.items()):
                raise ValueError("skill archive bytes differ from verified release")
        return
    (output / "SKILL.md").write_text(skill, encoding="utf-8")
    with zipfile.ZipFile(output / "wallet-skill.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("SKILL.md", skill)
        archive.writestr("claw.json", metadata)
        for name in ("install.sh", "release.manifest", "release.manifest.sigstore.json"):
            archive.write(output / name, name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--package", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    build(args.output, args.version, args.commit, package=args.package, check=args.check)


if __name__ == "__main__":
    main()
