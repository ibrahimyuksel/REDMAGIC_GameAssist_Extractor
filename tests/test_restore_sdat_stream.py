#!/usr/bin/env python3
"""Cheap local sanity test; no ROM download required."""
import io
import subprocess
import sys
import tempfile
from pathlib import Path

script = Path(__file__).resolve().parents[1] / 'scripts' / 'restore_sdat_stream.py'
with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    transfer = folder / 'system.transfer.list'
    transfer.write_text('4\n3\n0\n0\nnew 4,0,2,4,5\nzero 2,2,4\n')
    a = b'A' * 4096
    b = b'B' * 4096
    c = b'C' * 4096
    image = folder / 'system.img'
    result = subprocess.run([sys.executable, str(script), str(transfer), str(image)], input=a+b+c, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    data = image.read_bytes()
    assert data == a+b+(b'\x00'*8192)+c
    # Bad byte count must be rejected.
    failed = subprocess.run([sys.executable, str(script), str(transfer), str(folder/'bad.img')], input=a, capture_output=True)
    assert failed.returncode != 0
print('PASS - restored sparse blocks and detected truncated streams')
