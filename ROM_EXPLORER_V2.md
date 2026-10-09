# ROM Explorer v2 - cloud ROM file selector

Open **Actions > ROM Explorer v2 - Selective Extraction > Run workflow**.

Enter the fields:
1. **source_url**: Public direct HTTPS download URL to a ZIP, split ZIP (.zip.00), TAR, TAR.GZ, or raw ext4/EROFS image. GitHub downloads the source to its cloud runner, not to your computer.
2. **target_files**: One or more comma-separated file names or wildcard patterns, e.g. GameAssist*.apk,libgame*.so. Matches are case-insensitive. In list mode, leave blank for all files.
3. **action_mode**: extract to return matching files, or list to create the FILE_LIST.csv inventory without copying the selected files.
4. **zip_parts**: 1 for normal files; for archive pieces .zip.00 to .zip.03, provide the .zip.00 link (or base .zip URL) and enter 4.
5. **partitions**: system (default), all, none, or a comma-separated subset of system,system_ext,product,vendor,odm. none scans only files in the outer archive.
6. **source_sha256**: Optional full-archive digest. Strongly recommended.
7. **max_files**: 1-30, default 20.

After completion go to the run's **Artifacts > ROM-Explorer-v2-Results**. Download the result ZIP. It contains REPORT.json, FILE_LIST.csv and files under selected/ if extracted. On failure, the report is still uploaded when possible.

## Supported archives

- ZIP and consecutive split ZIP parts; TAR, TAR.GZ/TGZ.
- Full Android block OTA partition pairs partition.transfer.list + partition.new.dat.br (or .new.dat) nested in ZIP, rebuilding the image and attempting read-only EROFS/ext4 mount.
- Full embedded partition.img in ZIP and standalone mountable .img/.erofs image.
- Search by case-insensitive exact name or wildcards for files in archives and selected reconstructed partitions.

## Limits

- Not supported: payload.bin OTA, incremental OTAs, sparse Android images, encrypted archive contents, OEM-specific containers, downloads that require browser login.
- The GitHub runner still downloads the entire source, and listing Android partitions may require rebuilding them. It does **not** work without a cloud download.
- Limit: 14 GiB source, 500 MiB each result, 750 MiB total output, 30 extracted files, 200k inventory rows. GitHub Actions storage/time quotas also apply.
- Use trusted direct HTTPS links only, and do not include private access tokens in workflow inputs.

Example: from the existing LtiRom release, use its direct .zip.00 URL, zip_parts=4, target_files=GameAssist15_5.apk, partitions=system, action_mode=extract.
