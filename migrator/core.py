from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()
SUPPORTED = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.bmp', '.gif', '.tif', '.tiff', '.ico', '.avif'}


class LocalSetupError(RuntimeError):
    """A deliberately safe local error that may be displayed in the GUI."""


def run_exiftool(tool: str, arguments: list[str], operation: str, timeout=180):
    if hasattr(tool, 'execute'):
        return tool.execute(arguments, operation, timeout)
    if '(-k)' in Path(tool).name.lower():
        raise LocalSetupError('เลือก exiftool(-k).exe ซึ่งรอกดปุ่มเมื่อจบงาน '
                              'กรุณาเปลี่ยนชื่อเป็น exiftool.exe แล้วเลือกไฟล์ใหม่ในหน้าตั้งค่า')
    try:
        return subprocess.run([tool, *arguments], stdin=subprocess.DEVNULL,
                              capture_output=True, check=True, timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired:
        raise LocalSetupError(f'ExifTool ใช้เวลาเกิน {timeout} วินาทีขณะ{operation} '
                              'งานหยุดและยังไม่ผ่านการตรวจวันที่ '
                              'ตรวจว่าเลือก exiftool.exe พร้อมโฟลเดอร์ exiftool_files ครบ '
                              'และลองคัดลอกอัลบั้มจากเครือข่าย/OneDrive มายังดิสก์ในเครื่องก่อน') from None
    except subprocess.CalledProcessError as exc:
        raise LocalSetupError(f'ExifTool ไม่สำเร็จขณะ{operation} (exit code {exc.returncode}) '
                              'ตรวจสิทธิ์ไฟล์และโฟลเดอร์ exiftool_files') from None
    except OSError:
        raise LocalSetupError('เปิด ExifTool ไม่ได้ ตรวจเส้นทาง executable และไฟล์ประกอบ') from None


def validate_exiftool(tool: str) -> str:
    result = run_exiftool(tool, ['-ver'], 'ตรวจการเริ่มทำงาน', timeout=15)
    version = result.stdout.decode('utf-8', errors='replace').strip()
    if not re.fullmatch(r'\d+\.\d+', version):
        raise LocalSetupError('ไฟล์ที่เลือกไม่ตอบเวอร์ชัน ExifTool กรุณาเลือก exiftool.exe')
    return version


def album_date(value: str) -> date:
    """ISO CE date or explicitly confirmed Thai album label."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        day, month, year = map(int, value.split('-'))
        if year < 100:
            year += 2500
        if year >= 2400:
            year -= 543
        return date(year, month, day)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Photo:
    path: Path
    sha256: str
    width: int
    height: int
    error: str = ''
    duplicate: bool = False


def scan(folder: Path) -> list[Photo]:
    result = []
    seen = set()
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        try:
            sha = digest(path)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                width, height = image.size
            result.append(Photo(path, sha, width, height, duplicate=sha in seen))
            seen.add(sha)
        except Exception as exc:
            result.append(Photo(path, '', 0, 0, type(exc).__name__))
    return result


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS albums (
            key TEXT PRIMARY KEY, title TEXT NOT NULL, remote_id TEXT, state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS photos (
            album TEXT NOT NULL, sha TEXT NOT NULL, source TEXT NOT NULL,
            state TEXT NOT NULL, media_id TEXT, message TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(album, sha));
          CREATE TABLE IF NOT EXISTS skipped (
            album TEXT NOT NULL, source TEXT NOT NULL, sha TEXT, reason TEXT,
            PRIMARY KEY(album,source));
        ''')

    def state(self, album, sha):
        row = self.db.execute('SELECT state FROM photos WHERE album=? AND sha=?', (album, sha)).fetchone()
        return row[0] if row else None

    def record(self, album, photo, state, media_id=None, message=''):
        self.db.execute('''INSERT INTO photos VALUES(?,?,?,?,?,?)
            ON CONFLICT(album,sha) DO UPDATE SET state=excluded.state,
            media_id=excluded.media_id,message=excluded.message''',
            (album, photo.sha256, str(photo.path), state, media_id, message))
        self.db.commit()

    def skip(self, album, photo):
        self.db.execute('INSERT OR REPLACE INTO skipped VALUES(?,?,?,?)',
                        (album, str(photo.path), photo.sha256, 'corrupt' if photo.error else 'duplicate'))
        self.db.commit()

    def export(self, path: Path):
        import csv
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['album', 'sha256', 'source', 'state', 'media_id', 'message'])
            for row in self.db.execute('SELECT * FROM photos ORDER BY album,source'):
                # Spreadsheet formula injection protection for user-controlled paths.
                writer.writerow(["'" + cell if isinstance(cell, str) and cell.startswith(('=', '+', '-', '@'))
                                 else cell for cell in row])
            for album, source, sha, reason in self.db.execute('SELECT * FROM skipped ORDER BY album,source'):
                if source.startswith(('=', '+', '-', '@')):
                    source = "'" + source
                writer.writerow([album, sha, source, 'skipped', '', reason])

    def close(self):
        self.db.close()


def find_exiftool(configured: str = '') -> str:
    if configured:
        if not Path(configured).is_file():
            raise LocalSetupError('ไม่พบ ExifTool ตามเส้นทางที่ตั้งไว้ กรุณาเลือกไฟล์ใหม่')
        return str(Path(configured).resolve())
    import sys
    bundled = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent)) / 'tools' / 'exiftool.exe'
    if bundled.is_file():
        return str(bundled)
    found = shutil.which('exiftool') or shutil.which('exiftool.exe')
    if not found:
        raise LocalSetupError('ไม่พบ ExifTool: เลือก exiftool.exe ในหน้าตั้งค่า')
    return found


def metadata(path: Path, tool: str) -> dict:
    output = run_exiftool(tool, ['-j', '-DateTimeOriginal', '-CreateDate', '-ModifyDate',
                                 '-OffsetTimeOriginal', '-XMP:DateCreated', str(path.resolve())],
                          'อ่าน metadata')
    try:
        values = json.loads(output.stdout)
        if not isinstance(values, list) or not values or not isinstance(values[0], dict):
            raise ValueError('invalid metadata response')
        return values[0]
    except (ValueError, TypeError):
        raise LocalSetupError('ExifTool ไม่คืน metadata ที่อ่านได้ งานนี้ยังไม่ผ่านการตรวจวันที่') from None


def prepare(photo: Photo, when: date, output: Path, tool: str) -> Path:
    if photo.error or photo.duplicate:
        raise ValueError('ไฟล์เสียหรือซ้ำ')
    if digest(photo.path) != photo.sha256:
        raise RuntimeError('ไฟล์ต้นฉบับเปลี่ยนหลังตรวจสอบ กรุณา Dry Run ใหม่')
    output.mkdir(parents=True, exist_ok=True)
    # HEIC and other formats normalize to JPEG; PNG remains lossless.
    suffix = '.png' if photo.path.suffix.lower() == '.png' else '.jpg'
    target = output / (photo.sha256 + suffix)
    if target.resolve() == photo.path.resolve():
        raise ValueError('โฟลเดอร์สำเนาต้องแยกจากต้นฉบับ')
    if photo.path.suffix.lower() in {'.jpg', '.jpeg', '.png'}:
        shutil.copy2(photo.path, target)
    else:
        from PIL import ImageOps
        with Image.open(photo.path) as image:
            ImageOps.exif_transpose(image).convert('RGB').save(target, 'JPEG', quality=95)
    local = datetime.combine(when, datetime.min.time(), ZoneInfo('Asia/Bangkok'))
    stamp = local.strftime('%Y:%m:%d %H:%M:%S')
    args = ['-overwrite_original', f'-DateTimeOriginal={stamp}',
            f'-CreateDate={stamp}', f'-ModifyDate={stamp}', '-OffsetTimeOriginal=+07:00',
            f'-XMP:DateCreated={local.isoformat()}', str(target)]
    run_exiftool(tool, args, 'เขียนวันที่ลงสำเนา')
    actual = metadata(target, tool)
    if any(actual.get(tag) != stamp for tag in ('DateTimeOriginal', 'CreateDate', 'ModifyDate')) or actual.get('OffsetTimeOriginal') != '+07:00':
        raise RuntimeError('ตรวจสอบ metadata หลังเขียนไม่ผ่าน')
    if digest(photo.path) != photo.sha256:
        raise RuntimeError('ต้นฉบับเปลี่ยนระหว่างทำงาน')
    if target.stat().st_size > 200 * 1024 * 1024:
        raise RuntimeError('สำเนาเกินขนาดรูป 200 MB ของ Google Photos')
    # Set the filesystem timestamp last: ExifTool replaces the copy when writing.
    # Windows Date modified is filesystem mtime, not the EXIF ModifyDate tag.
    expected_ns = int(local.timestamp()) * 1_000_000_000
    try:
        os.utime(target, ns=(target.stat().st_atime_ns, expected_ns))
    except OSError:
        raise LocalSetupError('ตั้ง Date modified ของสำเนาไม่ได้ ตรวจสิทธิ์และระบบไฟล์ของโฟลเดอร์สำเนา') from None
    if abs(target.stat().st_mtime_ns - expected_ns) > 2_000_000_000:
        raise LocalSetupError('ตรวจ Date modified ของสำเนาไม่ผ่าน ยังไม่อนุญาตอัปโหลดไฟล์นี้')
    return target
