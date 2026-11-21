#!/usr/bin/env python3
"""Validate release metadata and package only the installable HA component."""

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "kickrvent"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Release tag, which must match the manifest version")
    args = parser.parse_args()
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    if manifest["domain"] != COMPONENT.name or hacs["content_in_root"]:
        raise ValueError("Unexpected integration layout")
    version = manifest["version"]
    if args.tag and args.tag != f"v{version}":
        raise ValueError(f"Tag {args.tag} does not match manifest version {version}")
    for key in ("domain", "name", "documentation", "issue_tracker", "codeowners", "version"):
        if not manifest.get(key):
            raise ValueError(f"Missing release metadata: {key}")
    if not (ROOT / "brand" / "icon.png").is_file():
        raise ValueError("Missing HACS brand/icon.png")
    for name in ("icon.png", "icon@2x.png"):
        if not (COMPONENT / "brand" / name).is_file():
            raise ValueError(f"Missing installed brand image: {name}")
    files = sorted(p for p in COMPONENT.rglob("*") if p.is_file() and p.suffix in (".py", ".json", ".png"))
    for path in files:
        if path.suffix == ".json":
            json.loads(path.read_text())
        elif path.suffix == ".py":
            compile(path.read_text(), str(path), "exec")
        elif path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Invalid PNG: {path}")
    strings = json.loads((COMPONENT / "strings.json").read_text())
    for language in ("en", "nl"):
        translated = json.loads((COMPONENT / "translations" / f"{language}.json").read_text())
        if translated.keys() != strings.keys():
            raise ValueError(f"Missing translation sections: {language}")
    archive = ROOT / "artifacts" / f"kickrvent-{version}.zip"
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for path in files:
            package.write(path, path.relative_to(ROOT))
    print(f"Validated {len(files)} component files; created {archive}")


if __name__ == "__main__":
    main()
