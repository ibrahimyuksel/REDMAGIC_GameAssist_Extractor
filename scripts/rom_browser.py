#!/usr/bin/env python3
"""Offline, read-only Android partition indexer and bounded file extractor."""

import argparse
import csv
import fnmatch
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

MAX_FILES = 30
MAX_BYTES = 768 * 1024 * 1024
PREVIEW_LIMIT = 100

HTML = r'''<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>REDMAGIC ROM Dosya Gezgini</title><style>
:root{color-scheme:dark;font:15px system-ui,Arial,sans-serif}body{margin:0;background:#111522;color:#e9ecf6}
main{max-width:1100px;margin:auto;padding:28px 20px}h1{margin:0 0 8px;font-size:28px}p{color:#abb5ca}
.bar{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}input,select,textarea,button{font:inherit;background:#202839;color:white;border:1px solid #3b4963;border-radius:8px;padding:10px}
input{flex:1;min-width:240px}button{cursor:pointer;background:#4564cb;border-color:#4564cb}
button.secondary{background:#202839;border-color:#3b4963}table{width:100%;border-collapse:collapse;table-layout:fixed}
tr{border-bottom:1px solid #293248}th{text-align:left;color:#aeb8cf}td,th{padding:10px 6px}td.path{overflow-wrap:anywhere}th:first-child{width:34px}th:last-child{width:112px}
small{color:#9faac2}textarea{width:100%;min-height:90px;box-sizing:border-box} .hint{padding:12px 16px;border:1px solid #3b4963;border-radius:10px;background:#192234}
</style></head><body><main><h1>REDMAGIC ROM Dosya Gezgini</h1>
<p>System bolumundeki dosyalar. Arama yapin, dosya secin ve GitHub Actions <b>selected_paths</b> alanina yapistirin.</p>
<div class="bar"><input id="q" placeholder="Dosya adi veya klasor ara: GameAssist, .so, Hunt"><select id="ext"><option value="">Tum turler</option></select></div>
<p id="count"></p><div class="bar"><button id="select">Gorunenleri sec</button><button id="clear" class="secondary">Secimi temizle</button></div>
<table><thead><tr><th></th><th>ROM icindeki tam yol</th><th>Boyut</th></tr></thead><tbody id="rows"></tbody></table>
<p><small>Performans icin ilk 200 eslesen dosya gosterilir. Secimler arama degisse de korunur.</small></p>
<h2>Secilen dosyalar (<span id="n">0</span>)</h2>
<textarea id="chosen" readonly placeholder="Secilen dosyalar burada gorunecek"></textarea>
<div class="bar"><button id="copy">Secili yollari kopyala</button></div>
<p class="hint">GitHub Actions &gt; Extract REDMAGIC GameAssist 15.5 &gt; Run workflow: <b>mode=extract</b>, <b>selected_paths</b> kutusuna kopyalanan yollari yapistirin. Dosyalar bilgisayariniza degil, once GitHub bulutuna cikarilir.</p>
</main><script>
const files=__ROWS__;
const q=document.getElementById('q'),ext=document.getElementById('ext'),rows=document.getElementById('rows');
const selected=new Set();let visible=[];
function bytes(n){if(n<1024)return n+' B';let a=['KB','MB','GB'],i=-1;do{n/=1024;i++}while(n>=1024&&i<2);return n.toFixed(1)+' '+a[i];}
function sync(){document.getElementById('n').textContent=selected.size;document.getElementById('chosen').value=[...selected].sort().join(', ');}
function render(){const needle=q.value.toLocaleLowerCase(),kind=ext.value;const matches=files.filter(f=>f.path.toLocaleLowerCase().includes(needle)&&(!kind||f.extension===kind));
visible=matches.slice(0,200);document.getElementById('count').textContent=matches.length+' eslesme / '+files.length+' dosya';rows.replaceChildren();
for(const f of visible){const tr=document.createElement('tr'),c0=document.createElement('td'),c1=document.createElement('td'),c2=document.createElement('td'),cb=document.createElement('input');
cb.type='checkbox';cb.checked=selected.has(f.path);cb.addEventListener('change',()=>{cb.checked?selected.add(f.path):selected.delete(f.path);sync();});c0.appendChild(cb);
c1.className='path';c1.textContent=f.path;c2.textContent=bytes(f.size_bytes);tr.append(c0,c1,c2);rows.appendChild(tr);}}
for(const kind of [...new Set(files.map(f=>f.extension))].sort()){const o=document.createElement('option');o.value=kind;o.textContent=kind;ext.appendChild(o);}
q.addEventListener('input',render);ext.addEventListener('change',render);
document.getElementById('select').addEventListener('click',()=>{for(const f of visible)selected.add(f.path);render();sync();});
document.getElementById('clear').addEventListener('click',()=>{selected.clear();render();sync();});
document.getElementById('copy').addEventListener('click',async()=>{const t=document.getElementById('chosen');if(!t.value)return;
try{if(!navigator.clipboard)throw Error('clipboard unavailable');await navigator.clipboard.writeText(t.value);}catch(e){t.focus();t.select();document.execCommand('copy');}});
render();
</script></body></html>'''


def inventory(root):
    """Only regular files under root; never follow symlinks."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Partition mount path is not a directory')
    found = []
    for parent, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(parent) / name).is_symlink()]
        for name in names:
            src = Path(parent) / name
            if src.is_symlink() or not src.is_file():
                continue
            rel = src.relative_to(root).as_posix()
            found.append({'path': rel, 'size_bytes': src.stat().st_size,
                          'extension': src.suffix.lower() or '(none)'})
    found.sort(key=lambda e: e['path'].casefold())
    return found


def summary(text):
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(text + '\n')


def browse(root, output, query):
    entries = inventory(root)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'rom-index.json').write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding='utf-8')
    with (output / 'rom-index.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['path', 'size_bytes', 'extension'])
        writer.writeheader()
        writer.writerows(entries)
    # Paths must not escape into the surrounding script, even if the ROM is untrusted.
    data = json.dumps(entries, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (output / 'rom-file-browser.html').write_text(HTML.replace('__ROWS__', data), encoding='utf-8')
    terms = [t.strip().casefold() for t in re.split(r'[,;\n]+', query) if t.strip()]
    matches = [e for e in entries if not terms or any(t in e['path'].casefold() for t in terms)]
    md = ['## REDMAGIC ROM Dosya Gezgini - system', '',
          f'**{len(entries)} dosya** kataloglandi; filtreye uyan: **{len(matches)}**.',
          '', 'Tum liste ve arama yapilabilen rom-file-browser.html dosyasi Artifacts > REDMAGIC-ROM-File-Index altindadir.',
          '', 'Secili dosyalari almak icin yeniden Run workflow: mode=extract, selected_paths=app/GameAssist15_5/GameAssist15_5.apk (ornek).',
          '', '| Dosya yolu (system bolumu) | Boyut (bayt) |', '| --- | ---: |']
    for entry in matches[:PREVIEW_LIMIT]:
        safe_path = entry['path'].replace('|', '\\|').replace('\n', ' ')
        md.append(f"| {safe_path} | {entry['size_bytes']:,} |")
    if len(matches) > PREVIEW_LIMIT:
        md.append(f'\nIlk {PREVIEW_LIMIT} sonuc gosteriliyor. Tum sonuclar HTML/CSV/JSON katalogunda.')
    (output / 'INDEX_PREVIEW.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    summary('\n'.join(md))
    print(f'Indexed {len(entries)} files; matched {len(matches)} search results')


def parse_patterns(raw):
    patterns = [p.strip() for p in re.split(r'[,;\n]+', raw) if p.strip()]
    if not patterns:
        raise ValueError('selected_paths is empty. Use mode=browse to find file paths first.')
    for pattern in patterns:
        parts = PurePosixPath(pattern).parts
        if pattern.startswith(('/', '\\')) or '\\' in pattern or '..' in parts or '.' in parts or not parts:
            raise ValueError(f'Invalid ROM path: {pattern!r}')
    return list(dict.fromkeys(patterns))


def matches_pattern(path, pattern):
    p = path.casefold()
    pat = pattern.casefold()
    return fnmatch.fnmatchcase(p if '/' in pat else p.rsplit('/', 1)[-1], pat)


def extract(root, output, raw_patterns):
    patterns = parse_patterns(raw_patterns)
    entries = inventory(root)
    selected = [e for e in entries if any(matches_pattern(e['path'], p) for p in patterns)]
    missing = [p for p in patterns if not any(matches_pattern(e['path'], p) for e in selected)]
    if missing:
        raise ValueError('These selections did not match a file: ' + ', '.join(missing))
    total = sum(e['size_bytes'] for e in selected)
    if len(selected) > MAX_FILES or total > MAX_BYTES:
        raise ValueError(f'Selection exceeds limits: {len(selected)} files / {total} bytes; maximum {MAX_FILES} files / {MAX_BYTES} bytes')
    # Validate paths before copying anything. Output keeps original relative paths.
    root = root.resolve(strict=True)
    destinations = []
    for entry in selected:
        src = root / entry['path']
        if src.is_symlink() or not src.is_file() or not src.resolve(strict=True).is_relative_to(root):
            raise ValueError(f'Unsafe source file: {entry["path"]}')
        destinations.append((src, output / 'selected' / entry['path'], entry))
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'SHA256SUMS.txt').open('w', encoding='utf-8') as sums:
        for src, dst, entry in destinations:
            dst.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with src.open('rb') as reader, dst.open('wb') as writer:
                while chunk := reader.read(4 * 1024 * 1024):
                    digest.update(chunk)
                    writer.write(chunk)
            sums.write(f'{digest.hexdigest()}  selected/{entry["path"]}\n')
    with (output / 'selected-files.json').open('w', encoding='utf-8') as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)
    md = ['## REDMAGIC secilen ROM dosyalari', '', f'{len(selected)} dosya cikarildi; toplam **{total:,} bayt**.', '',
          'Indirmek icin bu run altindaki Artifacts > REDMAGIC-Selected-Files dosyasini acin.', '',
          '| System icindeki yol | Boyut (bayt) |', '| --- | ---: |']
    for e in selected:
        safe_path = e['path'].replace('|', '\\|').replace('\n', ' ')
        md.append(f"| {safe_path} | {e['size_bytes']:,} |")
    summary('\n'.join(md))
    print(f'Extracted {len(selected)} files ({total} bytes)')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='action', required=True)
    for name in ('browse', 'extract'):
        s = subs.add_parser(name)
        s.add_argument('--root', type=Path, required=True)
        s.add_argument('--output', type=Path, required=True)
        if name == 'browse':
            s.add_argument('--search', default='GameAssist,GameSpace,Hunt')
        else:
            s.add_argument('--paths', required=True)
    args = p.parse_args()
    try:
        if args.action == 'browse':
            browse(args.root, args.output, args.search)
        else:
            extract(args.root, args.output, args.paths)
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
