#!/usr/bin/env python3
"""ROM Explorer v2: select files from public HTTPS ROM archives in GitHub Actions.

Supports ZIP, consecutively split ZIP, TAR/TAR.GZ/TGZ, raw EROFS/ext4 images,
and full Android block-OTA system*.transfer.list + *.new.dat[.br] partitions.
This is intentionally not a universal firmware unpacker (payload.bin, sparse
Android images, incremental OTAs and encrypted archives are not supported).
"""
import argparse
import csv
import fnmatch
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

CHUNK = 1024 * 1024
MAX_DOWNLOAD = 14 * 1024**3
MAX_ITEM = 500 * 1024**2
MAX_OUTPUT = 750 * 1024**2
MAX_LISTED = 200_000
KNOWN_PARTITIONS = ("system", "system_ext", "product", "vendor", "odm")

class ExplorerError(RuntimeError):
    pass

def safe_path(value):
    """Return a portable relative archive path, or None for unsafe members."""
    if not value or "\x00" in value or "\\" in value or re.match(r"^[A-Za-z]:", value):
        return None
    value = value.rstrip("/")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in (".", "..") for p in path.parts):
        return None
    return path.as_posix()

def patterns_from(raw):
    items = [part.strip() for part in re.split(r"[,;\n]+", raw) if part.strip()]
    if len(items) > 30:
        raise ExplorerError("At most 30 filename patterns are allowed")
    for item in items:
        if item.startswith("/") or "\\" in item or "\x00" in item or ".." in item.split("/"):
            raise ExplorerError("Unsafe filename pattern: " + item)
    return items

def is_match(path, patterns):
    if not patterns:
        return True
    path = path.casefold()
    basename = path.rsplit("/", 1)[-1]
    for item in patterns:
        pattern = item.casefold()
        if fnmatch.fnmatchcase(path, pattern):
            return True
        if "/" not in pattern and fnmatch.fnmatchcase(basename, pattern):
            return True
        if "/" in pattern and fnmatch.fnmatchcase(path, "*/" + pattern):
            return True
    return False

def public_https(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ExplorerError("Only public HTTPS direct-download URLs are accepted")
    try:
        port = parts.port
    except ValueError as exc:
        raise ExplorerError("Invalid HTTPS port") from exc
    if port not in (None, 443):
        raise ExplorerError("Only standard HTTPS port 443 is allowed")
    host = parts.hostname
    if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
        raise ExplorerError("Local/private hosts are not permitted")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ExplorerError("Cannot resolve source host: " + host) from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ExplorerError("Source URL resolves to a non-public address")
    return url

class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def source_urls(url, count):
    if not 1 <= count <= 20:
        raise ExplorerError("Part count must be between 1 and 20")
    if count == 1:
        return [url]
    parts = urllib.parse.urlsplit(url)
    path = parts.path
    if path.lower().endswith(".zip.00"):
        path = path[:-3]
    elif not path.lower().endswith(".zip"):
        raise ExplorerError("For split ZIP enter the base .zip URL or first .zip.00 URL")
    return [
        urllib.parse.urlunsplit(parts._replace(path=path + ".%02d" % index))
        for index in range(count)
    ]

def download(url, count, dest, sha256=""):
    opener = urllib.request.build_opener(HTTPSRedirects())
    urls = source_urls(url, count)
    digest = hashlib.sha256()
    downloaded = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as target:
        for number, part_url in enumerate(urls, 1):
            public_https(part_url)
            print("Downloading part %d/%d on GitHub runner..." % (number, len(urls)), flush=True)
            req = urllib.request.Request(part_url, headers={
                "User-Agent": "ROM-Explorer-v2/1.0",
                "Accept": "application/octet-stream",
            })
            with opener.open(req, timeout=90) as source:
                public_https(source.geturl())
                mime = source.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if mime in ("text/html", "application/xhtml+xml"):
                    raise ExplorerError("URL returned a web page, not a direct archive download")
                reported = source.headers.get("Content-Length")
                if reported and downloaded + int(reported) > MAX_DOWNLOAD:
                    raise ExplorerError("Source exceeds 14 GiB download limit")
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > MAX_DOWNLOAD:
                        raise ExplorerError("Source exceeds 14 GiB download limit")
                    target.write(block)
                    digest.update(block)
    actual = digest.hexdigest()
    if sha256:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise ExplorerError("Expected SHA-256 must have 64 hexadecimal digits")
        if actual.lower() != sha256.lower():
            raise ExplorerError("SHA-256 mismatch; refusing to inspect the archive")
    print("Downloaded %d bytes on GitHub runner (sha256 %s)" % (downloaded, actual), flush=True)
    return actual

class Explorer:
    def __init__(self, out, work, mode, patterns, partitions, max_files):
        self.out, self.work = out, work
        self.mode, self.patterns = mode, patterns
        self.partitions, self.max_files = partitions, max_files
        self.count, self.listed, self.bytes = 0, 0, 0
        self.results, self.notes = [], []
        out.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        self.file = (out / "FILE_LIST.csv").open("w", encoding="utf-8", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(("scope", "path", "size_bytes"))

    def consider(self, scope, name, size, opener):
        path = safe_path(name)
        if path is None or size < 0:
            return
        self.count += 1
        if not is_match(path, self.patterns):
            return
        if self.listed < MAX_LISTED:
            self.writer.writerow((scope, path, size))
            self.listed += 1
        elif self.listed == MAX_LISTED:
            self.notes.append("Inventory truncated at %d matching entries" % MAX_LISTED)
            self.listed += 1
        if self.mode == "list":
            return
        if len(self.results) >= self.max_files:
            raise ExplorerError("Too many matches; refine filename patterns (max %d files)" % self.max_files)
        if size > MAX_ITEM or self.bytes + size > MAX_OUTPUT:
            raise ExplorerError("Selected file(s) exceed 500 MiB/file or 750 MiB/run")
        target = self.out / "selected" / scope / path
        target.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        written = 0
        with opener() as source, target.open("xb") as dest:
            while True:
                block = source.read(CHUNK)
                if not block:
                    break
                written += len(block)
                if written > size or written > MAX_ITEM or self.bytes + written > MAX_OUTPUT:
                    raise ExplorerError("Extracted member exceeds declared size or output limit")
                h.update(block)
                dest.write(block)
        if written != size:
            raise ExplorerError("Truncated archive member: " + path)
        self.bytes += written
        self.results.append({"path": str(target.relative_to(self.out)), "bytes": written, "sha256": h.hexdigest()})
        print("Extracted: %s (%d bytes)" % (path, written), flush=True)

    def process_zip(self, archive):
        with zipfile.ZipFile(archive) as z:
            members = z.infolist()
            for info in members:
                if info.is_dir():
                    continue
                clean = safe_path(info.filename)
                if clean is not None:
                    self.consider("archive", clean, info.file_size, lambda i=info: z.open(i))
            lookup = {}
            for info in members:
                if safe_path(info.filename) is None:
                    continue
                lookup.setdefault(PurePosixPath(info.filename).name.lower(), info)
            for partition in self.partitions:
                transfer = lookup.get(partition + ".transfer.list")
                data = lookup.get(partition + ".new.dat.br") or lookup.get(partition + ".new.dat")
                image_info = lookup.get(partition + ".img")
                if transfer and data:
                    image = self.work / (partition + ".img")
                    try:
                        self.restore_partition(z, transfer, data, image)
                        self.walk_image(image, partition)
                    finally:
                        image.unlink(missing_ok=True)
                elif image_info:
                    image = self.work / (partition + ".img")
                    try:
                        if image_info.file_size > MAX_DOWNLOAD:
                            raise ExplorerError("Embedded partition image exceeds size limit")
                        with z.open(image_info) as src, image.open("xb") as dest:
                            shutil.copyfileobj(src, dest, CHUNK)
                        self.walk_image(image, partition)
                    finally:
                        image.unlink(missing_ok=True)
                else:
                    self.notes.append("No mountable full image found for partition: " + partition)
            if "payload.bin" in lookup:
                self.notes.append("Android payload.bin is not supported in v2")

    def process_tar(self, archive):
        with tarfile.open(archive, "r:*") as tf:
            for member in tf:
                if not member.isfile():
                    continue  # Never follow archive links or devices
                clean = safe_path(member.name)
                if clean is not None:
                    self.consider("archive", clean, member.size, lambda m=member: tf.extractfile(m))
        if self.partitions:
            self.notes.append("Nested Android partition mounting is supported for ZIP, not TAR, in v2")

    def restore_partition(self, z, transfer, data, image):
        list_file = self.work / (image.stem + ".transfer.list")
        if transfer.file_size > 4 * 1024**2:
            raise ExplorerError("Transfer list too large")
        list_file.write_bytes(z.read(transfer))
        restore_script = Path(__file__).with_name("restore_sdat_stream.py")
        if not restore_script.exists():
            raise ExplorerError("restore_sdat_stream.py is missing")
        error_log = tempfile.TemporaryFile()
        decoder_errors = tempfile.TemporaryFile()
        decoder, restorer = None, None
        try:
            with z.open(data) as stream:
                if data.filename.lower().endswith(".br"):
                    decoder = subprocess.Popen(
                        ["brotli", "-dc"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=decoder_errors,
                    )
                    restorer = subprocess.Popen(
                        [sys.executable, str(restore_script), str(list_file), str(image)],
                        stdin=decoder.stdout, stdout=subprocess.DEVNULL, stderr=error_log,
                    )
                    decoder.stdout.close()
                    sink = decoder.stdin
                else:
                    restorer = subprocess.Popen(
                        [sys.executable, str(restore_script), str(list_file), str(image)],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=error_log,
                    )
                    sink = restorer.stdin
                try:
                    shutil.copyfileobj(stream, sink, CHUNK)
                finally:
                    sink.close()
            return_code = restorer.wait()
            decoder_code = decoder.wait() if decoder else 0
            if return_code or decoder_code:
                error_log.seek(0)
                decoder_errors.seek(0)
                detail = (error_log.read(2048) + decoder_errors.read(1024)).decode("utf-8", errors="replace")
                raise ExplorerError("Cannot rebuild full OTA partition %s: %s" % (image.stem, detail.strip()))
        finally:
            if decoder and decoder.poll() is None:
                decoder.kill()
                decoder.wait()
            if restorer and restorer.poll() is None:
                restorer.kill()
                restorer.wait()
            error_log.close()
            decoder_errors.close()
            list_file.unlink(missing_ok=True)

    def walk_image(self, image, partition):
        mount = self.work / ("mount_" + partition)
        mount.mkdir(exist_ok=True)
        failures = []
        mounted = False
        for fstype, options in (("erofs", "ro,loop"), ("ext4", "ro,loop,noload")):
            attempt = subprocess.run(
                ["sudo", "mount", "-t", fstype, "-o", options, str(image), str(mount)],
                capture_output=True, text=True,
            )
            if attempt.returncode == 0:
                mounted = True
                break
            failures.append(fstype + ": " + attempt.stderr.strip()[:160])
        if not mounted:
            self.notes.append("Could not mount %s: %s" % (partition, "; ".join(failures)))
            return
        try:
            for directory, dirs, names in os.walk(mount, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
                for name in names:
                    full = Path(directory) / name
                    if full.is_symlink() or not full.is_file():
                        continue
                    relative = full.relative_to(mount).as_posix()
                    logical = partition + "/" + relative
                    self.consider("partitions", logical, full.stat().st_size, lambda p=full: p.open("rb"))
        finally:
            subprocess.run(["sudo", "umount", str(mount)], check=True)

    def finish(self, source, sha256, error=None):
        self.file.close()
        public_source = urllib.parse.urlsplit(source)
        stripped = urllib.parse.urlunsplit(public_source._replace(query="", fragment=""))
        report = {
            "source_url_without_query": stripped, "source_sha256": sha256,
            "mode": self.mode, "file_patterns": self.patterns, "partitions": self.partitions,
            "entries_examined": self.count, "matching_entries_listed": min(self.listed, MAX_LISTED),
            "extracted_files": self.results, "total_extracted_bytes": self.bytes,
            "notes": self.notes, "error": str(error) if error else None,
        }
        (self.out / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "matched": report["matching_entries_listed"],
            "extracted": len(self.results), "notes": self.notes, "error": report["error"],
        }, ensure_ascii=False), flush=True)

def parse_partitions(raw):
    if raw.strip().lower() in ("none", "off", "-"):
        return []
    if raw.strip().lower() == "all":
        return list(KNOWN_PARTITIONS)
    parsed = [x.strip().lower() for x in raw.split(",") if x.strip()]
    if any(x not in KNOWN_PARTITIONS for x in parsed):
        raise ExplorerError("Partitions must be system, system_ext, product, vendor, odm, all, or none")
    return list(dict.fromkeys(parsed))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--parts", type=int, default=1)
    parser.add_argument("--sha256", default="")
    parser.add_argument("--mode", choices=("list", "extract"), default="extract")
    parser.add_argument("--patterns", default="")
    parser.add_argument("--partitions", default="system")
    parser.add_argument("--max-files", type=int, default=20)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    ctx = None
    sha256 = ""
    error = None
    try:
        if not 1 <= args.max_files <= 30:
            raise ExplorerError("Max files must be between 1 and 30")
        patterns = patterns_from(args.patterns)
        if args.mode == "extract" and not patterns:
            raise ExplorerError("Enter a file name or wildcard pattern for extraction")
        partitions = parse_partitions(args.partitions)
        ctx = Explorer(args.out, args.work, args.mode, patterns, partitions, args.max_files)
        archive = args.work / "source.download"
        sha256 = download(args.url, args.parts, archive, args.sha256.strip())
        if zipfile.is_zipfile(archive):
            ctx.process_zip(archive)
        elif tarfile.is_tarfile(archive):
            ctx.process_tar(archive)
        elif urllib.parse.urlsplit(args.url).path.lower().endswith((".img", ".erofs")):
            ctx.walk_image(archive, "system")
        else:
            raise ExplorerError("Unsupported source format. Use ZIP, split ZIP, TAR/TAR.GZ or raw EROFS/ext4 .img")
        if args.mode == "extract" and not ctx.results:
            raise ExplorerError("No matching files extracted. Use list mode, check partitions and inspect REPORT.json")
    except (ExplorerError, OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        error = str(exc)
        print("ERROR: " + error, file=sys.stderr, flush=True)
    finally:
        if ctx is not None:
            ctx.finish(args.url, sha256, error)
        else:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "ERROR.txt").write_text(error or "Unknown error", encoding="utf-8")
    return 1 if error else 0

if __name__ == "__main__":
    sys.exit(main())
