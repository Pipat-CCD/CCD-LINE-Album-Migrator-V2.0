from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .core import Ledger, LocalSetupError, Photo, prepare, reusable_copy
from .google_photos import AmbiguousResult, SafeAPIError, EXPECTED_ACCOUNT
from .upload_pipeline import upload_album

DONE_STATES = ('uploaded', 'confirmed_manual')


@dataclass
class Album:
    folder: Path
    when: date
    photos: list[Photo]
    destination_title: str = ''
    destination_id: str = ''

    @property
    def title(self):
        return self.destination_title or self.folder.name

    @property
    def destination_key(self):
        if not self.destination_title:
            return self.key
        identity = self.destination_id or self.destination_title
        return 'destination:' + hashlib.sha256((EXPECTED_ACCOUNT + '|' + identity).encode()).hexdigest()

    @property
    def key(self):
        text = EXPECTED_ACCOUNT + '|' + str(self.folder.resolve()) + '|' + self.when.isoformat()
        if self.destination_title:
            text += '|destination:' + (self.destination_id or self.destination_title)
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
            destination_key = album.destination_key
            row = ledger.db.execute('SELECT remote_id,state FROM albums WHERE key=?', (destination_key,)).fetchone()
            if row and row[1] not in ('ready', 'failed'):
                raise AmbiguousResult('ผลสร้างอัลบั้มไม่แน่ชัด ต้องตรวจสอบก่อนทำต่อ')
            if row and row[1] == 'ready':
                remote_id = row[0]
            else:
                ledger.db.execute('INSERT OR REPLACE INTO albums VALUES(?,?,NULL,?)', (destination_key, album.title, 'creating'))
                ledger.db.commit()
                # Keep "creating" on any failure: safest after crash or lost response.
                try:
                    if album.destination_id:
                        # Only accept an ID previously recorded by this application.
                        known = ledger.db.execute('SELECT 1 FROM albums WHERE remote_id=? AND state=?',
                                                  (album.destination_id, 'ready')).fetchone()
                        if not known:
                            raise SafeAPIError('อัลบั้มปลายทางนี้ไม่อยู่ในประวัติที่แอปสร้าง')
                        remote_id = album.destination_id
                    else:
                        remote_id = api.create_album(album.title)
                except AmbiguousResult:
                    raise
                except SafeAPIError:
                    ledger.db.execute('UPDATE albums SET state=? WHERE key=?', ('failed', destination_key))
                    ledger.db.commit()
                    raise
                ledger.db.execute('UPDATE albums SET remote_id=?,state=? WHERE key=?', (remote_id, 'ready', destination_key))
                ledger.db.commit()
            if destination_key != album.key:
                ledger.db.execute('INSERT OR REPLACE INTO albums VALUES(?,?,?,?)',
                                  (album.key, album.title, remote_id, 'ready'))
                ledger.db.commit()
        if api and getattr(api, 'supports_batch_upload', False) is True:
            done = upload_album(album, ledger, output, tool, control, notify, api,
                                remote_id, done, total, DONE_STATES)
            if control.cancelled.is_set():
                notify('ยกเลิกงานแล้ว สามารถ Resume ภายหลังได้', done, total)
                return
            continue
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
                notify(f'กำลังเขียนและตรวจวันที่: {photo.path.name}', done - 1, total)
                target = reusable_copy(ledger, album.key, photo, album.when, output / album.key, tool) if api else None
                if target is None:
                    target = prepare(photo, album.when, output / album.key, tool)
                    ledger.cache_copy(album.key, photo, target)
                if api:
                    token = api.upload(target)
                    ledger.record(album.key, photo, 'creating')
                    media_id = api.create_media(token, remote_id, photo.path.stem + target.suffix)
                    ledger.record(album.key, photo, 'uploaded', media_id)
                else:
                    ledger.record(album.key, photo, 'prepared')
                notify(f'{"อัปโหลด" if api else "ตรวจสำเนา"} สำเร็จ: {photo.path.name}', done, total)
            except AmbiguousResult as exc:
                ledger.record(album.key, photo, 'uncertain', message=str(exc))
                raise
            except SafeAPIError as exc:
                ledger.record(album.key, photo, 'failed', message=str(exc))
                raise
            except LocalSetupError as exc:
                ledger.record(album.key, photo, 'failed', message=str(exc))
                raise
            except Exception as exc:
                ledger.record(album.key, photo, 'failed', message=type(exc).__name__)
                raise
    notify('เสร็จสิ้น', done, total)
