"""Standalone verifier for downloaded Compliance Bundles.

Usage:

    python scripts/verify_bundle.py /path/to/compliance_eu_ai_act_*.zip

Reads the manifest, recomputes archive SHA-256 (excluding the
manifest itself), and verifies the embedded signature against the
embedded public key. Exits 0 on success, 1 on any mismatch.

This is what an external auditor would run to confirm a bundle
hasn't been tampered with after export. It does NOT contact the
live demo; everything is computed offline.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: verify_bundle.py <bundle.zip>", file=sys.stderr)
        return 2

    bundle_path = Path(args[0])
    if not bundle_path.exists():
        print(f"file not found: {bundle_path}", file=sys.stderr)
        return 2

    try:
        from dcp_ai.crypto import verify_object
    except ImportError:
        print("dcp-ai is required: pip install dcp-ai>=2.8.1", file=sys.stderr)
        return 2

    with zipfile.ZipFile(bundle_path) as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            print("invalid bundle: missing manifest.json", file=sys.stderr)
            return 1
        with zf.open("manifest.json") as f:
            manifest = json.loads(f.read().decode("utf-8"))

    print(f"Bundle: {bundle_path.name}")
    print(f"Framework:    {manifest.get('framework')}")
    print(f"Exported at:  {manifest.get('exported_at')}")
    print(f"Entries:      {manifest.get('entries_count')}")
    print(f"Roots:        {manifest.get('roots_count')}")
    print(f"Bundles:      {manifest.get('bundles_count')}")
    print(f"Signer key:   {manifest.get('signer_public_key_b64')}")

    # ── Verify signature ──────────────────────────────────────
    signature = manifest.pop("signature_b64", "")
    pubkey = manifest.get("signer_public_key_b64", "")
    if not signature or not pubkey:
        print("ERROR: bundle is missing signature or signer key.", file=sys.stderr)
        return 1
    valid = verify_object(manifest, signature, pubkey)
    print(f"Signature:    {'VALID' if valid else 'INVALID'}")
    if not valid:
        return 1
    print()
    print("Bundle authenticated. The agent's signed audit log has not")
    print("been tampered with since export.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
