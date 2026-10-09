"""Synthetic 71-photo integration validation, with actual ExifTool, never Google."""
import json
import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener
from migrator.core import digest, metadata

register_heif_opener()
root = Path(sys.argv[1]).resolve()
tool = os.environ['CCD_TEST_EXIFTOOL']
source = root / '9-5-68'
source.mkdir(parents=True, exist_ok=True)
for index in range(71):
    suffix = '.heic' if index == 70 else '.png' if index >= 60 else '.jpg'
    Image.new('RGB', (48, 32), (index * 3, index, 255 - index)).save(source / f'{index:03d}{suffix}')
before = {p.name: digest(p) for p in source.iterdir()}
before_mtime = {p.name: p.stat().st_mtime_ns for p in source.iterdir()}
command = [sys.executable, 'main.py', '--dry-run', str(source), '--date', '2025-05-09',
           '--output', str(root / 'output'), '--exiftool', tool]
subprocess.run(command, check=True)
copies = list((root / 'output' / 'copies').rglob('*.jpg')) + list((root / 'output' / 'copies').rglob('*.png'))
assert len(copies) == 71, len(copies)
for photo in copies:
    tags = metadata(photo, tool)
    assert tags['DateTimeOriginal'] == '2025:05:09 00:00:00', photo
    assert tags['OffsetTimeOriginal'] == '+07:00', photo
    assert datetime.fromtimestamp(photo.stat().st_mtime, ZoneInfo('Asia/Bangkok')).isoformat() == '2025-05-09T00:00:00+07:00', photo
assert before == {p.name: digest(p) for p in source.iterdir()}, 'originals changed'
assert before_mtime == {p.name: p.stat().st_mtime_ns for p in source.iterdir()}, 'original modified times changed'
subprocess.run(command, check=True)
assert len(list((root / 'output' / 'copies').rglob('*.jpg'))) + len(list((root / 'output' / 'copies').rglob('*.png'))) == 71
result = {'synthetic_photos': 71, 'metadata_verified': 71, 'original_hashes_unchanged': True,
          'copy_modified_dates_verified': 71, 'original_modified_dates_unchanged': True,
          'repeat_run': 'passed', 'real_google_upload': 'not_run'}
(root / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
