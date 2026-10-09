import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from migrator.google_photos import AmbiguousResult, GoogleHTTPError, PhotosAPI


class HTTPErrorTests(unittest.TestCase):
    def api(self):
        api = PhotosAPI(Mock(valid=True, token='synthetic-test-only'), sleeper=Mock())
        api.account = 'ccdphoto@ccdthailand.org'
        api.session = Mock()
        return api

    def response(self, code, body=None, text='upload-token'):
        response = Mock(status_code=code, ok=code < 400, headers={}, text=text)
        response.json.return_value = body or {}
        return response

    def test_upload_409_no_retry_and_diagnostic_does_not_leak_message(self):
        api = self.api()
        api.session.request.return_value = self.response(409, {'error': {
            'status': 'ABORTED', 'message': 'SENSITIVE-TOKEN-DO-NOT-LOG'}})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'photo.jpg'
            path.write_bytes(b'test')
            with self.assertRaises(GoogleHTTPError) as caught:
                api.upload(path)
        self.assertEqual(api.session.request.call_count, 1)
        api.sleep.assert_not_called()
        self.assertIn('ส่งไฟล์ (bytes)', str(caught.exception))
        self.assertIn('ABORTED', str(caught.exception))
        self.assertNotIn('SENSITIVE', str(caught.exception))

    def test_upload_403_no_retry(self):
        api = self.api()
        api.session.request.return_value = self.response(403)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'photo.jpg'
            path.write_bytes(b'test')
            with self.assertRaises(GoogleHTTPError):
                api.upload(path)
        self.assertEqual(api.session.request.call_count, 1)
        api.sleep.assert_not_called()

    def test_transient_upload_retry_rewinds_entire_stream(self):
        api = self.api()
        data = []
        def send(*args, **kwargs):
            data.append(kwargs['data'].read())
            return self.response(503 if len(data) == 1 else 200)
        api.session.request.side_effect = send
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'photo.jpg'
            path.write_bytes(b'complete-image-bytes')
            self.assertEqual(api.upload(path), 'upload-token')
        self.assertEqual(data, [b'complete-image-bytes', b'complete-image-bytes'])
        api.sleep.assert_called_once()

    def test_rate_limit_has_one_bounded_retry_loop(self):
        api = self.api()
        api.session.request.return_value = self.response(429)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'photo.jpg'
            path.write_bytes(b'test')
            with self.assertRaises(GoogleHTTPError):
                api.upload(path)
        self.assertEqual(api.session.request.call_count, 5)
        self.assertEqual(api.sleep.call_count, 4)

    def test_mutating_409_is_ambiguous_never_automatic_retry(self):
        api = self.api()
        api.session.request.return_value = self.response(409, {'error': {'status': 'ABORTED'}})
        with self.assertRaises(AmbiguousResult) as caught:
            api.create_media_batch([('token', 'photo.jpg')], 'album')
        self.assertIn('สร้างรูปในอัลบั้ม', str(caught.exception))
        self.assertEqual(api.session.request.call_count, 1)
        api.sleep.assert_not_called()
