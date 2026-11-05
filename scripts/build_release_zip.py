"""Build the HACS release asset from tracked integration files only."""

import argparse
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

DOMAIN = "hoymiles_home"
PREFIX = Path("custom_components") / DOMAIN


def tracked_files(root):
    raw = subprocess.check_output(["git", "ls-files", "-z", "--", PREFIX.as_posix()], cwd=root)
    return [Path(name.decode("utf-8")) for name in raw.split(b"\0") if name]


def build_archive(root, output):
    root, output = Path(root), Path(output)
    manifest = json.loads((root / PREFIX / "manifest.json").read_text())
    if manifest.get("domain") != DOMAIN or not isinstance(manifest.get("version"), str):
        raise ValueError("Unexpected integration manifest")
    files = []
    for relative in sorted(tracked_files(root)):
        name = relative.relative_to(PREFIX)
        source = root / relative
        if (".." in relative.parts or "__pycache__" in name.parts
                or source.is_symlink() or not source.is_file()
                or source.resolve() != (root / PREFIX).resolve().joinpath(name)):
            raise ValueError("Unsafe or missing release file")
        if source.suffix in {".pyc", ".pyo"} or any(part.startswith(".") for part in name.parts):
            raise ValueError("Unexpected generated or hidden release file")
        files.append((source, name.as_posix()))
    license_file = root / "LICENSE"
    if not license_file.is_file() or license_file.is_symlink() or license_file.resolve() != root.resolve() / "LICENSE":
        raise ValueError("Release license is missing or unsafe")
    if "LICENSE" in {name for _, name in files}:
        raise ValueError("Ambiguous release license")
    files.append((license_file, "LICENSE"))
    if "manifest.json" not in {name for _, name in files}:
        raise ValueError("Release manifest is not tracked")
    if output.resolve().is_relative_to((root / PREFIX).resolve()):
        raise ValueError("Release output must be outside the integration directory")
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for source, name in files:
            # Stable metadata and paths relative to the integration directory:
            # HACS extracts directly into custom_components/hoymiles_home.
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    count = build_archive(root, args.output)
    print(f"Built HACS package: {count} integration files")


if __name__ == "__main__":
    main()
