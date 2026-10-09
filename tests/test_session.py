import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

from migrator.core import LocalSetupError, digest, metadata, prepare, scan, validate_exiftool
from migrator.exiftool_session import ExifToolSession


class SessionTests(unittest.TestCase):
    def test_timeout_terminates_the_process(self):
        session = ExifToolSession('test-only')
        session.process = Mock()
        session.process.poll.return_value = None
        with self.assertRaisesRegex(LocalSetupError, 'งานหยุด'):
            session.execute(['-ver'], 'ทดสอบ', timeout=0.01)
        session.process.kill.assert_called_once()
        session.process.wait.assert_called_once()

    def test_argument_file_injection_is_rejected(self):
        session = ExifToolSession('test-only')
        session.process = Mock()
        session.process.poll.return_value = None
        with self.assertRaises(LocalSetupError):
            session.execute(['photo.jpg\n-execute'], 'ทดสอบ')
        session.process.stdin.write.assert_not_called()

    @unittest.skipUnless(os.environ.get('CCD_TEST_EXIFTOOL'), 'requires real ExifTool')
    def test_real_process_reused_and_each_command_status_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'อัลบั้มทดสอบ'
            source.mkdir()
            Image.new('RGB', (32, 24), 'blue').save(source / 'ภาพ ถ่าย.jpg')
            Image.new('RGB', (32, 24), 'red').save(source / 'ภาพ.png')
            photos = scan(source)
            originals = {p.path: (digest(p.path), p.path.stat().st_mtime_ns) for p in photos}
            session = ExifToolSession(os.environ['CCD_TEST_EXIFTOOL'])
            with session:
                pid = session.process.pid
                self.assertEqual(validate_exiftool(session), '13.59')
                for photo in photos:
                    result = prepare(photo, date(2025, 5, 9), root / 'สำเนา', session)
                    self.assertEqual(metadata(result, session)['DateTimeOriginal'], '2025:05:09 00:00:00')
                    self.assertEqual(session.process.pid, pid)
                with self.assertRaises(LocalSetupError):
                    metadata(root / 'missing.jpg', session)
                self.assertEqual(validate_exiftool(session), '13.59')
            self.assertIsNotNone(session.process.poll(), 'ExifTool process leaked after close')
            self.assertEqual(originals, {p.path: (digest(p.path), p.path.stat().st_mtime_ns) for p in photos})
