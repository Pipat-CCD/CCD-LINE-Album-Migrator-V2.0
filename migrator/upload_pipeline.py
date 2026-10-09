"""Parallel byte uploads; serial, durable media creation in bounded batches."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .core import LocalSetupError, prepare, reusable_copy
from .google_photos import AmbiguousResult, SafeAPIError


def upload_album(album, ledger, output, tool, control, notify, api, remote_id,
                 done, total, done_states, workers=3, batch_size=20):
    if not 1 <= workers <= 4 or not 1 <= batch_size <= 50:
        raise ValueError('invalid upload concurrency or batch size')
    pending = []
    for photo in album.photos:
        if photo.error or photo.duplicate:
            ledger.skip(album.key, photo)
            done += 1
            notify(f'ข้าม {photo.path.name}: ไฟล์เสียหรือซ้ำ', done, total)
        elif ledger.state(album.key, photo.sha256) in done_states:
            done += 1
            notify(f'อัปโหลดแล้ว ข้าม {photo.path.name}', done, total)
        else:
            pending.append(photo)
    clients = []
    clients_lock = threading.Lock()
    local = threading.local()

    def send_bytes(target):
        if not control.checkpoint():
            return None
        if not hasattr(local, 'client'):
            local.client = api.upload_client()
            with clients_lock:
                clients.append(local.client)
        start = time.monotonic()
        token = local.client.upload(target)
        return token, target.stat().st_size, time.monotonic() - start

    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='photo-bytes') as pool:
            for offset in range(0, len(pending), batch_size):
                chunk = pending[offset:offset + batch_size]
                prepared = []
                for photo in chunk:
                    if not control.checkpoint():
                        return done
                    try:
                        notify(f'ตรวจสำเนาก่อนส่ง: {photo.path.name}', done, total)
                        target = reusable_copy(ledger, album.key, photo, album.when, output / album.key, tool)
                        if target is None:
                            target = prepare(photo, album.when, output / album.key, tool)
                            ledger.cache_copy(album.key, photo, target)
                        ledger.record(album.key, photo, 'prepared')
                        prepared.append((photo, target))
                    except Exception as exc:
                        message = str(exc) if isinstance(exc, LocalSetupError) else type(exc).__name__
                        ledger.record(album.key, photo, 'failed', message=message)
                        raise
                notify(f'ส่งไฟล์ {len(prepared)} ภาพพร้อมกันสูงสุด {workers} ไฟล์', done, total)
                futures = {pool.submit(send_bytes, target): index for index, (_, target) in enumerate(prepared)}
                uploaded = {}
                first_error = None
                chunk_start = time.monotonic()
                for future in as_completed(futures):
                    index = futures[future]
                    photo, target = prepared[index]
                    try:
                        result = future.result()
                        if result is not None:
                            uploaded[index] = result[0]
                            size = sum(prepared[i][1].stat().st_size for i in uploaded)
                            seconds = max(time.monotonic() - chunk_start, 0.001)
                            notify(f'ส่ง bytes แล้ว {len(uploaded)}/{len(prepared)} ภาพ '
                                   f'({size / 1048576 / seconds:.2f} MB/s) ยังรอยืนยัน Google', done, total)
                    except Exception as exc:
                        ledger.record(album.key, photo, 'failed', message='ส่ง bytes ไม่สำเร็จ')
                        if first_error is None:
                            first_error = exc
                if first_error:
                    # No media creation for this chunk; raw bytes alone create no photos.
                    raise first_error
                if not control.checkpoint() or len(uploaded) != len(prepared):
                    return done
                items = [(uploaded[i], photo.path.stem + target.suffix)
                         for i, (photo, target) in enumerate(prepared)]
                # Commit the entire potentially ambiguous mutation BEFORE sending it.
                ledger.mark_creating(album.key, [photo for photo, _ in prepared])
                notify(f'Google กำลังสร้างรายการในอัลบั้ม {len(items)} ภาพ', done, total)
                try:
                    results = api.create_media_batch(items, remote_id)
                    if not isinstance(results, list) or len(results) != len(prepared):
                        raise AmbiguousResult('ผลชุดอัปโหลดไม่ครบ ต้องตรวจสอบก่อน Resume')
                except AmbiguousResult:
                    for photo, _ in prepared:
                        ledger.record(album.key, photo, 'uncertain', message='ผลสร้างชุดภาพไม่แน่ชัด')
                    raise
                except SafeAPIError:
                    for photo, _ in prepared:
                        ledger.record(album.key, photo, 'failed', message='Google ปฏิเสธสร้างชุดภาพ')
                    raise
                uncertain = failed = False
                for (photo, _), result in zip(prepared, results):
                    state = result.get('state', 'uncertain')
                    if state == 'uploaded' and result.get('media_id'):
                        ledger.record(album.key, photo, 'uploaded', result['media_id'])
                        done += 1
                        notify(f'อัปโหลดสำเร็จ: {photo.path.name}', done, total)
                    elif state == 'failed':
                        failed = True
                        ledger.record(album.key, photo, 'failed', message='Google ปฏิเสธไฟล์นี้')
                    else:
                        uncertain = True
                        ledger.record(album.key, photo, 'uncertain', message='ผลไฟล์นี้ไม่แน่ชัด')
                if uncertain:
                    raise AmbiguousResult('บางภาพมีผลไม่แน่ชัด ตรวจประวัติก่อน Resume')
                if failed:
                    raise SafeAPIError('บางภาพสร้างไม่สำเร็จ ผลสำเร็จอื่นบันทึกแล้ว ตรวจประวัติและ Resume ได้')
    finally:
        for client in clients:
            client.close()
    return done
