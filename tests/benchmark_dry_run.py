"""Compare old per-command startup against a persistent real ExifTool process."""
import json
import os
import time
from datetime import date
from pathlib import Path
from PIL import Image

from migrator.core import digest, metadata, prepare, scan
from migrator.exiftool_session import ExifToolSession

root = Path('work/benchmark').resolve()
source = root / 'synthetic-source'
source.mkdir(parents=True, exist_ok=True)
for index in range(71):
    suffix = '.heic' if index == 70 else '.png' if index >= 60 else '.jpg'
    Image.new('RGB', (48, 32), (index * 3, index, 255 - index)).save(source / f'{index:03d}{suffix}')
photos = scan(source)
assert len(photos) == 71
before = {p.path: (digest(p.path), p.path.stat().st_mtime_ns) for p in photos}
tool = os.environ['CCD_TEST_EXIFTOOL']
start = time.perf_counter()
for photo in photos:
    prepare(photo, date(2025, 5, 9), root / 'baseline', tool)
baseline = time.perf_counter() - start
start = time.perf_counter()
with ExifToolSession(tool) as session:
    for photo in photos:
        target = prepare(photo, date(2025, 5, 9), root / 'persistent', session)
    # Metadata is already verified in prepare; no external timing-only shortcuts.
persistent = time.perf_counter() - start
assert before == {p.path: (digest(p.path), p.path.stat().st_mtime_ns) for p in photos}
assert len(list((root / 'persistent').iterdir())) == 71
result = {'synthetic_photos': 71, 'baseline_seconds': round(baseline, 3),
          'persistent_seconds': round(persistent, 3), 'speedup': round(baseline / persistent, 2),
          'originals_unchanged': True, 'platform': 'Linux, not a Windows performance guarantee'}
(root / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
