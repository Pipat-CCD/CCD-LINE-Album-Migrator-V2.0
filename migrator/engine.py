from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .core import Ledger, Photo, prepare
from .google_photos import AmbiguousResult, SafeAPIError

DONE_STATES = ('uploaded', 'confirmed_manual')


@dataclass
class Album:
    folder: Path
    when: date
    photos: list[Photo]

    @property
    def key(self):
        text = str(self.folder.resolve()) + '|' + self.when.isoformat()
        return hashlib.sha256(text.encode()).hexdigest()


class Control:
    def __init__(self):
        self.running = threading.Event()
        self.running.set()
        self.cancelled = threading.Event()

    def checkpoint(self):
        while not self.running.wait(0.2):
            if self.cancelled.is_set():
                return False
        return not self.cancelled.is_set()


def run(albums, ledger: Ledger, output: Path, tool: str, control: Control, notify,
        api=None):
    total = sum(len(a.photos) for a in albums)
    done = 0
    if api:
        api.verify_account()
    for album in albums:
        if not control.checkpoint():
            return
        remote_id = None
        valid = [p for p in album.photos if not p.error and not p.duplicate]
        if api and any(ledger.state(album.key, p.sha256) in ('creating', 'uncertain') for p in valid):
            raise AmbiguousResult('มีไฟล์ที่ผลอัปโหลดไม่แน่ชัด ห้าม Resume จนกว่าจะตรวจสอบกับ Google Photos')
        if api and any(ledger.state(album.key, p.sha256) not in DONE_STATES for p in valid):
            row = ledger.db.execute('SELECT remote_id,state FROM albums WHERE key=?', (album.key,)).fetchone()
            if row and row[1] not in ('ready', 'failed'):
                raise AmbiguousResult('ผลสร้างอัลบั้มไม่แน่ชัด ต้องตรวจสอบก่อนทำต่อ')
            if row and row[1] == 'ready':
                remote_id = row[0]
            else:
                ledger.db.execute('INSERT OR REPLACE INTO albums VALUES(?,?,NULL,?)', (album.key, album.folder.name, 'creating'))
                ledger.db.commit()
                # Keep "creating" on any failure: safest after crash or lost response.
                try:
                    remote_id = api.create_album(album.folder.name)
                except AmbiguousResult:
                    raise
                except SafeAPIError:
                    ledger.db.execute('UPDATE albums SET state=? WHERE key=?', ('failed', album.key))
                    ledger.db.commit()
                    raise
                ledger.db.execute('UPDATE albums SET remote_id=?,state=? WHERE key=?', (remote_id, 'ready', album.key))
                ledger.db.commit()
        for photo in album.photos:
            if not control.checkpoint():
                notify('ยกเลิกงานแล้ว สามารถ Resume ภายหลังได้', done, total)
                return
            done += 1
            if photo.error or photo.duplicate:
                ledger.skip(album.key, photo)
                notify(f'ข้าม {photo.path.name}: ไฟล์เสียหรือซ้ำ', done, total)
                continue
            if ledger.state(album.key, photo.sha256) in ('creating', 'uncertain'):
                if api:
                    raise AmbiguousResult('ผลอัปโหลดไม่แน่ชัด ต้องตรวจสอบก่อนทำต่อ')
                notify(f'ไม่เปลี่ยนประวัติที่ต้องตรวจสอบ: {photo.path.name}', done, total)
                continue
            if ledger.state(album.key, photo.sha256) in DONE_STATES:
                notify(f'อัปโหลดแล้ว ข้าม {photo.path.name}', done, total)
                continue
            try:
                target = prepare(photo, album.when, output / album.key, tool)
                if api:
                    token = api.upload(target)
                    ledger.record(album.key, photo, 'creating')
                    media_id = api.create_media(token, remote_id, photo.path.stem + target.suffix)
                    ledger.record(album.key, photo, 'uploaded', media_id)
                else:
                    ledger.record(album.key, photo, 'prepared')
                notify(f'{"อัปโหลด" if api else "ตรวจสำเนา"} สำเร็จ: {photo.path.name}', done, total)
            except AmbiguousResult:
                ledger.record(album.key, photo, 'uncertain', message='ต้องตรวจสอบผลจริงก่อน retry')
                raise
            except SafeAPIError:
                ledger.record(album.key, photo, 'failed', message='Google ปฏิเสธคำขอ')
                raise
            except Exception as exc:
                ledger.record(album.key, photo, 'failed', message=type(exc).__name__)
                raise
    notify('เสร็จสิ้น', done, total)
