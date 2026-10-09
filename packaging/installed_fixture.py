"""Non-secret synthetic fixtures for installed Windows package validation."""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from migrator.core import digest, metadata

phase, directory = sys.argv[1:3]
root = Path(directory)
source = root / 'photos'
manifest = root / 'fixture-originals.json'
if phase == 'create':
    source.mkdir(parents=True, exist_ok=True)
    for name, color in [('photo.jpg', 'red'), ('photo.png', 'blue'), ('photo.heic', 'green')]:
        Image.new('RGB', (32, 24), color).save(source / name)
    originals = {p.name: [digest(p), p.stat().st_mtime_ns] for p in source.iterdir()}
    manifest.write_text(json.dumps(originals), encoding='utf-8')
else:
    tool = sys.argv[3]
    originals = json.loads(manifest.read_text(encoding='utf-8'))
    assert originals == {p.name: [digest(p), p.stat().st_mtime_ns] for p in source.iterdir()}
    copies = list((root / 'output' / 'copies').rglob('*.jpg')) + list((root / 'output' / 'copies').rglob('*.png'))
    assert len(copies) == 3, len(copies)
    for photo in copies:
        tags = metadata(photo, tool)
        assert tags['DateTimeOriginal'] == '2025:05:09 00:00:00'
        assert tags['OffsetTimeOriginal'] == '+07:00'
        assert datetime.fromtimestamp(photo.stat().st_mtime, ZoneInfo('Asia/Bangkok')).isoformat() == '2025-05-09T00:00:00+07:00'
    print('Installed package validated 3 synthetic formats; originals and dates preserved')
