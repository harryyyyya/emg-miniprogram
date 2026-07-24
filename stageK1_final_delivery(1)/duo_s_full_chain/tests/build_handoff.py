from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "duo_s_full_chain"
ARTIFACT = ROOT / "artifacts/duo_s_full_chain_runtime_f2"
ZIP_PATH = ARTIFACT / "duo_s_full_chain_runtime_f2.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allowed(path: Path) -> bool:
    forbidden_parts = {"__pycache__", ".pytest_cache", "model"}
    forbidden_suffixes = {".pyc", ".pyo", ".onnx", ".cvimodel", ".so", ".dll", ".bin", ".npy"}
    relative = path.relative_to(SOURCE)
    owned_roots = {"contracts", "runtime", "native", "tests"}
    return (
        bool(relative.parts)
        and relative.parts[0] in owned_roots
        and not any(part in forbidden_parts for part in relative.parts)
        and path.suffix.lower() not in forbidden_suffixes
    )


def main() -> int:
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    source_files = sorted(path for path in SOURCE.rglob("*") if path.is_file() and allowed(path))
    artifact_files = sorted(
        path for path in ARTIFACT.iterdir()
        if path.is_file() and path.name not in {ZIP_PATH.name, ZIP_PATH.name + ".sha256", "package_report.json", "FILE_MANIFEST.json"}
    )
    manifest_entries = []
    for path in source_files + artifact_files:
        archive_name = path.relative_to(ROOT).as_posix()
        manifest_entries.append({"path": archive_name, "size_bytes": path.stat().st_size, "sha256": sha256(path)})
    manifest_path = ARTIFACT / "FILE_MANIFEST.json"
    manifest_path.write_text(json.dumps({"schema_version": 1, "entries": manifest_entries}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_files.append(manifest_path)
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in source_files + artifact_files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    digest = sha256(ZIP_PATH)
    sidecar = ZIP_PATH.with_name(ZIP_PATH.name + ".sha256")
    sidecar.write_text(f"{digest}  {ZIP_PATH.name}\n", encoding="ascii")
    with zipfile.ZipFile(ZIP_PATH) as archive:
        names = archive.namelist()
        forbidden = [name for name in names if any(token in name.lower() for token in (".onnx", ".cvimodel", "__pycache__", ".pyc", ".so", ".dll", "demo_sequence.bin"))]
    report = {
        "status": "PASS" if not forbidden and sidecar.read_text(encoding="ascii").split()[0] == sha256(ZIP_PATH) else "FAIL",
        "zip": str(ZIP_PATH.relative_to(ROOT)),
        "size_bytes": ZIP_PATH.stat().st_size,
        "entry_count": len(names),
        "sha256": digest,
        "sidecar": str(sidecar.relative_to(ROOT)),
        "sidecar_verified": sidecar.read_text(encoding="ascii").split()[0] == sha256(ZIP_PATH),
        "forbidden_entries": forbidden,
    }
    (ARTIFACT / "package_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
