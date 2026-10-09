#!/usr/bin/env python3
"""Read-only static signature search of REDMAGIC firmware partitions.

Find likely GameAssist / Hunt backend consumers in APK, JAR, DEX and native files.
A string match is NOT proof of execution or image-processing behavior.
"""

import argparse
import json
import os
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

SIGNATURES = {
    "set_surfaceflinger": b"set_surfaceflinger",
    "game_color_invert": b"cn.nubia.intent.action.game_color_invert",
    "game_strengthen_mode_value": b"game_strengthen_mode_value",
    "IGameAssistController": b"IGameAssistController",
    "getGameAssist": b"getGameAssist",
    "GameAssistController": b"GameAssistController",
    "game_gfrc_mode": b"game_gfrc_mode",
    "MindSyncManager": b"MindSyncManager",
    "game_color_transform": b"game_color_transform",
}
WEIGHTS = {
    "set_surfaceflinger": 100, "game_color_invert": 100,
    "game_strengthen_mode_value": 70, "IGameAssistController": 65,
    "getGameAssist": 65, "GameAssistController": 20,
    "game_gfrc_mode": 15, "MindSyncManager": 10,
    "game_color_transform": 35,
}
ARCHIVES = {".apk", ".jar", ".zip"}
SCANNED_SUFFIXES = {
    ".apk", ".jar", ".zip", ".dex", ".vdex", ".odex", ".oat", ".art",
    ".so", ".xml", ".json", ".txt", ".prop", ".rc", ".cfg", ".conf",
    ".bin", ".dat", ".cil", ".policy", ".map", ".pb", ".ini",
}
INNER_SUFFIXES = {".dex", ".so", ".xml", ".arsc", ".vdex", ".odex", ".oat", ".rc", ".txt", ".prop", ".json"}
BLOCK = 2 * 1024 * 1024
MAX_ENTRY_SIZE = 260 * 1024 * 1024
MAX_RAW_SIZE = 700 * 1024 * 1024
MAX_EXPORT_BYTES = 100 * 1024 * 1024
MAX_TOTAL_EXPORT_BYTES = 220 * 1024 * 1024
MAX_MEMBERS_EXPORTED = 5
NEEDLES = {k: (v.lower(), v.decode("ascii").lower().encode("utf-16le")) for k, v in SIGNATURES.items()}
MAX_NEEDLE_LENGTH = max(len(v) for pairs in NEEDLES.values() for v in pairs)

def scan_reader(reader):
    found, tail = set(), b""
    while True:
        chunk = reader.read(BLOCK)
        if not chunk:
            break
        data = (tail + chunk).lower()
        for key, variants in NEEDLES.items():
            if key not in found and any(variant in data for variant in variants):
                found.add(key)
        if len(found) == len(SIGNATURES):
            break
        tail = data[-(MAX_NEEDLE_LENGTH - 1):]
    return found

def inspect_path(path):
    hits, members = set(), {}
    if path.suffix.lower() in ARCHIVES:
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.is_dir() or entry.file_size > MAX_ENTRY_SIZE:
                    continue
                name = entry.filename.lower()
                if not (name.endswith(tuple(INNER_SUFFIXES)) or name == "androidmanifest.xml"):
                    continue
                with archive.open(entry) as reader:
                    found = scan_reader(reader)
                if found:
                    hits.update(found)
                    members[entry.filename] = sorted(found)
    elif path.stat().st_size <= MAX_RAW_SIZE:
        with path.open("rb") as reader:
            hits = scan_reader(reader)
    return sorted(hits), members

def score(row):
    result = sum(WEIGHTS.get(key, 0) for key in row["matches"])
    path = row["path"].lower()
    if any(word in path for word in ("framework", "service", "surface", "display", "nubia", "zte", "redmagic", "game")):
        result += 18
    return result

def export_candidate(root, row, output):
    relative = Path(row["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe relative path")
    src = root / relative
    if "GameAssist15_5.apk" in str(src):
        return None, 0
    directory = output / "candidates" / row["partition"] / relative.parent
    directory.mkdir(parents=True, exist_ok=True)
    if src.stat().st_size <= MAX_EXPORT_BYTES:
        dest = directory / src.name
        shutil.copyfile(src, dest)
        return str(dest.relative_to(output)), dest.stat().st_size
    if src.suffix.lower() in ARCHIVES and row["members"]:
        dest = directory / (src.name + ".selected.zip")
        with zipfile.ZipFile(src) as source, zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as target:
            choices = list(row["members"].keys())[:MAX_MEMBERS_EXPORTED]
            if "AndroidManifest.xml" in source.namelist() and "AndroidManifest.xml" not in choices:
                choices.append("AndroidManifest.xml")
            for member in choices:
                if source.getinfo(member).file_size <= MAX_ENTRY_SIZE:
                    target.writestr(member, source.read(member))
        if dest.stat().st_size <= MAX_EXPORT_BYTES:
            return str(dest.relative_to(output)), dest.stat().st_size
        dest.unlink(missing_ok=True)
    return None, 0

def scan_partition(root, partition, output):
    root = root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    file_count = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not Path(parent, d).is_symlink()]
        for basename in files:
            path = Path(parent, basename)
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in SCANNED_SUFFIXES and "bin" not in path.parts:
                continue
            file_count += 1
            try:
                matches, members = inspect_path(path)
                if matches:
                    rows.append({
                        "partition": partition, "path": str(path.relative_to(root)),
                        "size": path.stat().st_size, "matches": matches, "members": members,
                    })
            except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
                if len(errors) < 75:
                    errors.append(f"{path.relative_to(root)}: {type(error).__name__}: {str(error)[:90]}")
    with (output / "all_matches.jsonl").open("a", encoding="utf-8") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    candidates = output / "candidates"
    exported_total = sum(p.stat().st_size for p in candidates.rglob("*") if p.is_file()) if candidates.exists() else 0
    exported = []
    for row in sorted(rows, key=lambda r: (-score(r), r["size"])):
        if exported_total >= MAX_TOTAL_EXPORT_BYTES:
            break
        if score(row) < 50:
            continue
        try:
            copied, length = export_candidate(root, row, output)
            if copied:
                exported_total += length
                exported.append({"path": copied, "size": length})
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            if len(errors) < 75:
                errors.append(f"export {row['path']}: {error}")
    summary = {
        "partition": partition, "files_scanned": file_count,
        "matching_files": len(rows), "candidates_exported": exported,
        "scan_errors": errors,
    }
    (output / f"summary_{partition}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{partition}] scanned {file_count} files, matched {len(rows)}, exported {len(exported)} files", flush=True)

def finalize(output):
    file = output / "all_matches.jsonl"
    rows = [json.loads(row) for row in file.read_text(encoding="utf-8").splitlines() if row.strip()] if file.exists() else []
    totals = Counter(key for row in rows for key in row["matches"])
    reports = sorted(output.glob("summary_*.json"))
    lines = [
        "# REDMAGIC Hunt backend static scan", "",
        "Source: REDMAGIC Astra LtiRom global-fifteen recovery archive.",
        "Text matches alone do not prove a registered receiver or active renderer.", "",
        "## Signatures",
    ]
    for key in SIGNATURES:
        lines.append(f"- {key}: {totals[key]} matching files")
    lines.extend(["", "## Highest-priority candidates", "", "| Partition | Path | Matches | Score |", "|---|---|---|---:|"])
    for row in sorted(rows, key=lambda r: -score(r))[:90]:
        path = row["path"].replace("|", "/")
        matched = ", ".join(row["matches"])
        lines.append(f"| {row['partition']} | {path} | {matched} | {score(row)} |")
    lines.extend(["", "## Extraction status", ""])
    for path in reports:
        entry = json.loads(path.read_text(encoding="utf-8"))
        lines.append(f"- {entry['partition']}: {entry['files_scanned']} scanned, {entry['matching_files']} matching, {len(entry['candidates_exported'])} exported, {len(entry['scan_errors'])} read/export errors")
    lines.extend([
        "", "## Next", "",
        "- Trace server-side IGameAssistController.invake handler / 6001.",
        "- Identify broadcast receiver for game_color_invert.",
        "- Follow calls to vendor display and native services.",
        "- Do not assume actual GPU behavior from static strings.",
    ])
    output.mkdir(parents=True, exist_ok=True)
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--partition")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        finalize(args.output)
    else:
        if not args.root or not args.partition:
            parser.error("--root and --partition required")
        scan_partition(args.root, args.partition, args.output)

if __name__ == "__main__":
    main()
