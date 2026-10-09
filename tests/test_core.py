import os
import tempfile
import threading
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from migrator.core import Ledger, album_date, digest, metadata, prepare, scan
from migrator.engine import Album, Control, run
from migrator.google_photos import AmbiguousResult, PhotosAPI, SafeAPIError
from migrator.lock import InstanceLock


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / '9-5-68'
        self.source.mkdir()
        Image.new('RGB', (32, 24), 'red').save(self.source / 'a.jpg')
        self.ledger = Ledger(self.root / 'state.sqlite3')

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def album(self):
        return Album(self.source, date(2025, 5, 9), scan(self.source))

    def test_thai_and_iso_dates(self):
        self.assertEqual(album_date('9-5-68'), date(2025, 5, 9))
        self.assertEqual(album_date('9-5-2568'), date(2025, 5, 9))
        self.assertEqual(album_date('2025-05-09'), date(2025, 5, 9))
        with self.assertRaises(ValueError):
            album_date('31-2-68')

    def test_corruption_and_duplicates(self):
        (self.source / 'b.jpg').write_bytes((self.source / 'a.jpg').read_bytes())
        (self.source / 'broken.png').write_bytes(b'broken')
        photos = scan(self.source)
        self.assertEqual(len(photos), 3)
        self.assertEqual(sum(p.duplicate for p in photos), 1)
        self.assertEqual(sum(bool(p.error) for p in photos), 1)

    def test_changed_source_rejected(self):
        photo = scan(self.source)[0]
        photo.path.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'เปลี่ยน'):
            prepare(photo, date(2025, 5, 9), self.root / 'out', 'unused')

    def test_resume_never_creates_uploaded_file_again(self):
        album = self.album()
        photo = album.photos[0]
        self.ledger.record(album.key, photo, 'uploaded', 'media-1')
        api = Mock()
        with patch('migrator.engine.prepare') as prepared:
            run([album], self.ledger, self.root / 'out', 'tool', Control(), Mock(), api)
        api.create_album.assert_not_called()
        api.upload.assert_not_called()
        prepared.assert_not_called()

    def test_ambiguous_create_is_not_retried_on_resume(self):
        album = self.album()
        api = Mock()
        api.create_album.return_value = 'album-1'
        api.create_media.side_effect = AmbiguousResult('lost response')
        with patch('migrator.engine.prepare', return_value=self.source / 'a.jpg'):
            with self.assertRaises(AmbiguousResult):
                run([album], self.ledger, self.root / 'out', 'tool', Control(), Mock(), api)
        self.assertEqual(self.ledger.state(album.key, album.photos[0].sha256), 'uncertain')
        with self.assertRaises(AmbiguousResult):
            run([album], self.ledger, self.root / 'out', 'tool', Control(), Mock(), api)
        self.assertEqual(api.create_media.call_count, 1)

    def test_dry_run_preserves_ambiguous_state(self):
        album = self.album()
        photo = album.photos[0]
        self.ledger.record(album.key, photo, 'uncertain')
        with patch('migrator.engine.prepare') as prepared:
            run([album], self.ledger, self.root / 'out', 'tool', Control(), Mock())
        prepared.assert_not_called()
        self.assertEqual(self.ledger.state(album.key, photo.sha256), 'uncertain')

    def test_pause_and_cancel(self):
        control = Control()
        control.running.clear()
        completed = threading.Event()
        worker = threading.Thread(target=lambda: (control.checkpoint(), completed.set()))
        worker.start()
        self.assertFalse(completed.wait(0.05))
        control.running.set()
        self.assertTrue(completed.wait(1))
        worker.join()
        control.cancelled.set()
        self.assertFalse(control.checkpoint())

    def test_failed_album_can_resume_after_access_is_fixed(self):
        album = self.album()
        api = Mock()
        api.create_album.side_effect = SafeAPIError('HTTP 403')
        with self.assertRaises(SafeAPIError):
            run([album], self.ledger, self.root / 'out', 'tool', Control(), Mock(), api)
        state = self.ledger.db.execute('SELECT state FROM albums WHERE key=?', (album.key,)).fetchone()[0]
        self.assertEqual(state, 'failed')
        api.create_album.side_effect = None
        api.create_album.return_value = 'album-1'
        api.create_media.return_value = 'media-1'
        with patch('migrator.engine.prepare', return_value=self.source / 'a.jpg'):
            run([album], self.ledger, self.root / 'out', 'tool', Control(), Mock(), api)
        self.assertEqual(self.ledger.state(album.key, album.photos[0].sha256), 'uploaded')

    def test_csv_includes_skipped_files(self):
        (self.source / 'b.jpg').write_bytes((self.source / 'a.jpg').read_bytes())
        album = self.album()
        with patch('migrator.engine.prepare', return_value=self.source / 'a.jpg'):
            run([album], self.ledger, self.root / 'out', 'tool', Control(), Mock())
        path = self.root / 'report.csv'
        self.ledger.export(path)
        report = path.read_text(encoding='utf-8-sig')
        self.assertIn('duplicate', report)
        self.assertIn('prepared', report)

    def test_exclusive_instance(self):
        lock = InstanceLock(self.root / 'instance.lock')
        try:
            with self.assertRaises(RuntimeError):
                InstanceLock(self.root / 'instance.lock')
        finally:
            lock.close()

    @unittest.skipUnless(os.environ.get('CCD_TEST_EXIFTOOL'), 'requires real ExifTool')
    def test_actual_metadata_jpeg_png_and_heic(self):
        from pillow_heif import register_heif_opener
        register_heif_opener()
        Image.new('RGB', (16, 16), 'blue').save(self.source / 'b.png')
        Image.new('RGB', (16, 16), 'green').save(self.source / 'c.heic')
        for photo in scan(self.source):
            with self.subTest(path=photo.path):
                before = digest(photo.path)
                original_mtime = photo.path.stat().st_mtime_ns
                target = prepare(photo, date(2025, 5, 9), self.root / 'out', os.environ['CCD_TEST_EXIFTOOL'])
                actual = metadata(target, os.environ['CCD_TEST_EXIFTOOL'])
                self.assertEqual(actual['DateTimeOriginal'], '2025:05:09 00:00:00')
                self.assertEqual(actual['OffsetTimeOriginal'], '+07:00')
                self.assertEqual(digest(photo.path), before)
                self.assertEqual(photo.path.stat().st_mtime_ns, original_mtime)
                expected = datetime(2025, 5, 9, tzinfo=ZoneInfo('Asia/Bangkok')).timestamp()
                self.assertAlmostEqual(target.stat().st_mtime, expected, delta=2)
                modified = datetime.fromtimestamp(target.stat().st_mtime, ZoneInfo('Asia/Bangkok'))
                self.assertEqual(modified.isoformat(), '2025-05-09T00:00:00+07:00')


class APITests(unittest.TestCase):
    def api(self):
        credentials = Mock(valid=True, token='test-only')
        api = PhotosAPI(credentials, sleeper=Mock())
        api.session = Mock()
        return api

    def response(self, status, body):
        result = Mock(status_code=status, ok=status < 400, headers={})
        result.json.return_value = body
        return result

    def test_wrong_account_is_blocked(self):
        api = self.api()
        api.session.request.return_value = self.response(200, {'email': 'other@example.com', 'email_verified': True})
        with self.assertRaises(SafeAPIError):
            api.verify_account()
        with self.assertRaises(SafeAPIError):
            api.create_album('album')
        self.assertEqual(api.session.request.call_count, 1)

    def test_unverified_account_is_blocked(self):
        api = self.api()
        api.session.request.return_value = self.response(200, {'email': 'ccdphoto@ccdthailand.org', 'email_verified': False})
        with self.assertRaises(SafeAPIError):
            api.verify_account()

    def test_correct_ccd_account_is_accepted(self):
        api = self.api()
        api.session.request.return_value = self.response(200, {
            'email': 'ccdphoto@ccdthailand.org', 'email_verified': True})
        self.assertEqual(api.verify_account(), 'ccdphoto@ccdthailand.org')

    def test_previous_destination_account_is_blocked(self):
        api = self.api()
        api.session.request.return_value = self.response(200, {
            'email': 'photos@ccdthailand.org', 'email_verified': True})
        with self.assertRaises(SafeAPIError):
            api.verify_account()

    def test_create_server_error_is_ambiguous_no_retry(self):
        api = self.api()
        api.account = 'ccdphoto@ccdthailand.org'
        api.session.request.return_value = self.response(500, {})
        with self.assertRaises(AmbiguousResult):
            api.create_album('album')
        self.assertEqual(api.session.request.call_count, 1)

    def test_rate_limit_and_membership_request(self):
        api = self.api()
        api.account = 'ccdphoto@ccdthailand.org'
        api.session.request.side_effect = [self.response(429, {}), self.response(200,
            {'newMediaItemResults': [{'mediaItem': {'id': 'media-1'}, 'status': {}}]})]
        self.assertEqual(api.create_media('upload-token', 'album-1', 'photo.jpg'), 'media-1')
        request = api.session.request.call_args.kwargs['json']
        self.assertEqual(request['albumId'], 'album-1')
        self.assertEqual(len(request['newMediaItems']), 1)
        api.sleep.assert_called_once()


if __name__ == '__main__':
    unittest.main()
