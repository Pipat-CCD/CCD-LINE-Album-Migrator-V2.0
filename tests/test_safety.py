import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import date

import requests
from PIL import Image

from migrator.core import Ledger, scan
from migrator.engine import Album, Control, run
from migrator.google_photos import AmbiguousResult, PhotosAPI, authenticate, SafeAPIError
from migrator import token_store


class SafetyTests(unittest.TestCase):
    def test_token_storage_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'token.json'
            token_store.save(path, json.dumps({'refresh_token': 'synthetic-test-value'}))
            self.assertEqual(token_store.load(path)['refresh_token'], 'synthetic-test-value')

    def test_old_appendonly_token_requires_new_email_consent(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'token.json'
            token_store.save(path, json.dumps({'scopes': ['https://www.googleapis.com/auth/photoslibrary.appendonly']}))
            with self.assertRaises(SafeAPIError):
                authenticate(Path(temporary) / 'absent.json', path)

    def test_network_exception_does_not_leak_credentials(self):
        api = PhotosAPI(Mock(valid=True, token='SENSITIVE-TEST-TOKEN'), sleeper=Mock())
        api.account = 'ccdphoto@ccdthailand.org'
        api.session = Mock()
        api.session.request.side_effect = requests.Timeout('SENSITIVE-TEST-TOKEN')
        with self.assertRaises(AmbiguousResult) as caught:
            api.create_album('test')
        self.assertNotIn('SENSITIVE', str(caught.exception))
        self.assertEqual(api.session.request.call_count, 1)

    def test_100_album_batch_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            albums = []
            for index in range(100):
                folder = root / f'album-{index}'
                folder.mkdir()
                Image.new('RGB', (8, 8), (index, 0, 0)).save(folder / 'photo.png')
                albums.append(Album(folder, date(2025, 5, 9), scan(folder)))
            api = Mock()
            api.create_album.side_effect = [f'album-{i}' for i in range(100)]
            api.create_media.side_effect = [f'media-{i}' for i in range(100)]
            ledger = Ledger(root / 'state.sqlite3')
            try:
                with patch('migrator.engine.prepare', return_value=root / 'copy.jpg'):
                    run(albums, ledger, root / 'out', 'tool', Control(), Mock(), api)
                    run(albums, ledger, root / 'out', 'tool', Control(), Mock(), api)
                self.assertEqual(api.create_album.call_count, 100)
                self.assertEqual(api.upload.call_count, 100)
                self.assertEqual(api.create_media.call_count, 100)
                self.assertEqual(ledger.db.execute("SELECT count(*) FROM photos WHERE state='uploaded'").fetchone()[0], 100)
            finally:
                ledger.close()
