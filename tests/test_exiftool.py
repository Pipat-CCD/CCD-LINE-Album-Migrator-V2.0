import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from migrator.core import LocalSetupError, find_exiftool, run_exiftool, validate_exiftool


class ExifToolTests(unittest.TestCase):
    def test_frozen_package_uses_bundled_tool_over_stale_user_path(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / 'tools' / 'exiftool.exe'
            tool.parent.mkdir()
            tool.touch()
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', directory, create=True):
                self.assertEqual(find_exiftool('old-missing-tool.exe'), str(tool))

    def test_pause_executable_is_rejected_before_start(self):
        with patch('migrator.core.subprocess.run') as execute:
            with self.assertRaisesRegex(LocalSetupError, 'เปลี่ยนชื่อเป็น exiftool.exe'):
                validate_exiftool('exiftool(-k).exe')
            execute.assert_not_called()

    def test_noninteractive_invocation(self):
        with patch('migrator.core.subprocess.run', return_value=Mock(stdout=b'13.59\n')) as execute:
            self.assertEqual(validate_exiftool('exiftool.exe'), '13.59')
            self.assertIs(execute.call_args.kwargs['stdin'], subprocess.DEVNULL)
            self.assertEqual(execute.call_args.kwargs['timeout'], 15)

    def test_timeout_has_safe_actionable_message(self):
        with patch('migrator.core.subprocess.run', side_effect=subprocess.TimeoutExpired(
                ['tool'], 180, output=b'SENSITIVE-CONTENT')):
            with self.assertRaises(LocalSetupError) as caught:
                run_exiftool('exiftool.exe', ['-j', 'photo.jpg'], 'อ่าน metadata')
        self.assertIn('180', str(caught.exception))
        self.assertIn('อ่าน metadata', str(caught.exception))
        self.assertNotIn('SENSITIVE', str(caught.exception))

    def test_error_output_is_not_exposed(self):
        with patch('migrator.core.subprocess.run', side_effect=subprocess.CalledProcessError(
                1, ['tool'], stderr=b'SENSITIVE-CONTENT')):
            with self.assertRaises(LocalSetupError) as caught:
                validate_exiftool('exiftool.exe')
        self.assertNotIn('SENSITIVE', str(caught.exception))

    def test_wrong_program_is_rejected(self):
        with patch('migrator.core.subprocess.run', return_value=Mock(stdout=b'not-exiftool')):
            with self.assertRaises(LocalSetupError):
                validate_exiftool('other.exe')

    def test_real_hung_process_is_terminated_and_reported(self):
        with self.assertRaisesRegex(LocalSetupError, 'งานหยุด'):
            run_exiftool(sys.executable, ['-c', 'import time; time.sleep(5)'],
                         'ทดสอบ timeout', timeout=0.05)
