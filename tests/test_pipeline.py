import os
import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from migrator.core import Ledger, digest, scan, reusable_copy
from migrator.engine import Album, Control, run
from migrator.exiftool_session import ExifToolSession
from migrator.google_photos import AmbiguousResult, SafeAPIError


class FakeAPI:
    supports_batch_upload = True

    def __init__(self, ledger, album, control=None):
        self.ledger, self.album, self.control = ledger, album, control
        self.lock = threading.Lock()
        self.active = self.maximum = self.uploaded_bytes = self.created = 0
        self.batches = []
        self.mode = 'ok'

    def verify_account(self):
        return 'ccdphoto@ccdthailand.org'

    def create_album(self, title):
        return 'album-1'

    def upload_client(self):
        return self

    def close(self):
        pass

    def upload(self, target):
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        time.sleep(0.01)
        with self.lock:
            self.active -= 1
            self.uploaded_bytes += 1
        if self.control:
            self.control.cancelled.set()
            self.control.running.set()
        return target.name

    def create_media_batch(self, items, album_id):
        assert self.active == 0, 'media creation overlaps byte uploads'
        assert 1 <= len(items) <= 20
        states = self.ledger.db.execute("SELECT count(*) FROM photos WHERE state='creating'").fetchone()[0]
        assert states == len(items), 'batch mutation was not durably recorded'
        self.batches.append(len(items))
        if self.mode == 'ambiguous':
            raise AmbiguousResult('lost response')
        results = []
        for index, _ in enumerate(items):
            self.created += 1
            results.append({'state': 'failed', 'code': 3} if self.mode == 'partial' and index == 0 else
                           {'state': 'uploaded', 'media_id': f'media-{self.created}'})
        return results


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'album'
        self.source.mkdir()
        self.ledger = Ledger(self.root / 'state.sqlite3')

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def album(self, count):
        for index in range(count):
            Image.new('RGB', (16, 16), (index, 0, 0)).save(self.source / f'{index:03d}.png')
        return Album(self.source, date(2025, 5, 9), scan(self.source))

    def execute(self, album, api, control=None):
        # These tests isolate the network/ledger pipeline; metadata has separate real tests.
        with patch('migrator.upload_pipeline.reusable_copy', side_effect=lambda *args: args[2].path):
            run([album], self.ledger, self.root / 'out', 'unused', control or Control(), lambda *args: None, api)

    def test_71_photos_parallel_bytes_serial_four_batches_resume_no_duplicates(self):
        album = self.album(71)
        api = FakeAPI(self.ledger, album)
        self.execute(album, api)
        self.assertEqual(api.batches, [20, 20, 20, 11])
        self.assertGreater(api.maximum, 1)
        self.assertLessEqual(api.maximum, 3)
        self.assertEqual(api.uploaded_bytes, 71)
        self.execute(album, api)
        self.assertEqual(api.uploaded_bytes, 71)
        self.assertEqual(api.created, 71)

    def test_ambiguous_batch_blocks_all_retries(self):
        album = self.album(5)
        api = FakeAPI(self.ledger, album)
        api.mode = 'ambiguous'
        with self.assertRaises(AmbiguousResult):
            self.execute(album, api)
        self.assertTrue(all(self.ledger.state(album.key, p.sha256) == 'uncertain' for p in album.photos))
        with self.assertRaises(AmbiguousResult):
            self.execute(album, api)
        self.assertEqual(api.uploaded_bytes, 5)

    def test_partial_results_record_success_before_resume(self):
        album = self.album(5)
        api = FakeAPI(self.ledger, album)
        api.mode = 'partial'
        with self.assertRaises(SafeAPIError):
            self.execute(album, api)
        self.assertEqual(sum(self.ledger.state(album.key, p.sha256) == 'uploaded' for p in album.photos), 4)
        api.mode = 'ok'
        self.execute(album, api)
        self.assertEqual(api.batches, [5, 1])
        self.assertEqual(api.uploaded_bytes, 6)

    def test_cancel_after_bytes_creates_no_media(self):
        album = self.album(5)
        control = Control()
        api = FakeAPI(self.ledger, album, control)
        self.execute(album, api, control)
        self.assertEqual(api.created, 0)
        self.assertTrue(all(self.ledger.state(album.key, p.sha256) == 'prepared' for p in album.photos))

    @unittest.skipUnless(os.environ.get('CCD_TEST_EXIFTOOL'), 'requires real ExifTool')
    def test_real_dry_run_cache_reused_without_rewriting_or_losing_dates(self):
        album = self.album(3)
        api = FakeAPI(self.ledger, album)
        output = self.root / 'out'
        before = {p.path: (digest(p.path), p.path.stat().st_mtime_ns) for p in album.photos}
        with ExifToolSession(os.environ['CCD_TEST_EXIFTOOL']) as session:
            run([album], self.ledger, output, session, Control(), lambda *args: None)
            with patch('migrator.upload_pipeline.prepare', side_effect=AssertionError('unnecessary rewrite')):
                run([album], self.ledger, output, session, Control(), lambda *args: None, api)
        self.assertEqual(api.created, 3)
        self.assertEqual(before, {p.path: (digest(p.path), p.path.stat().st_mtime_ns) for p in album.photos})

    @unittest.skipUnless(os.environ.get('CCD_TEST_EXIFTOOL'), 'requires real ExifTool')
    def test_tampered_copy_is_not_reused(self):
        album = self.album(1)
        with ExifToolSession(os.environ['CCD_TEST_EXIFTOOL']) as session:
            output = self.root / 'out'
            run([album], self.ledger, output, session, Control(), lambda *args: None)
            target = next((output / album.key).glob('*.png'))
            target.write_bytes(b'corrupt')
            self.assertIsNone(reusable_copy(self.ledger, album.key, album.photos[0], album.when, output / album.key, session))
