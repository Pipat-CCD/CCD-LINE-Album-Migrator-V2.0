import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from migrator.core import Ledger, scan
from migrator.engine import Album, Control, run
from migrator.google_photos import SafeAPIError, AmbiguousResult


class DestinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / 'state.sqlite3')
        self.albums = []
        for i in range(2):
            folder = self.root / str(i)
            folder.mkdir()
            Image.new('RGB', (8, 8), (i, 0, 0)).save(folder / 'photo.png')
            self.albums.append(Album(folder, date(2025, 5, 9 + i), scan(folder), 'CCD 2025'))
        self.api = Mock()
        self.api.create_album.return_value = 'new-remote-id'
        self.api.create_media.return_value = 'media'

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def execute(self):
        with patch('migrator.engine.prepare', return_value=self.root / 'copy.jpg') as prepare:
            run(self.albums, self.ledger, self.root / 'out', 'tool', Control(), Mock(), self.api)
            return prepare.call_args_list

    def test_two_sources_share_one_destination_keep_dates_and_resume(self):
        calls = self.execute()
        self.assertEqual([c.args[1] for c in calls], [a.when for a in self.albums])
        self.api.create_album.assert_called_once_with('CCD 2025')
        self.assertEqual({c.args[1] for c in self.api.create_media.call_args_list}, {'new-remote-id'})
        self.execute()
        self.assertEqual(self.api.upload.call_count, 2)
        self.assertEqual(self.api.create_album.call_count, 1)

    def test_existing_app_created_destination_does_not_create_album(self):
        self.ledger.db.execute('INSERT INTO albums VALUES(?,?,?,?)', ('old-job', 'Existing', 'known-id', 'ready'))
        self.ledger.db.commit()
        for album in self.albums:
            album.destination_id = 'known-id'
            album.destination_title = 'Existing'
        self.execute()
        self.api.create_album.assert_not_called()
        self.assertEqual({c.args[1] for c in self.api.create_media.call_args_list}, {'known-id'})

    def test_unknown_destination_is_rejected_before_upload(self):
        self.albums[0].destination_id = 'unknown'
        with self.assertRaises(SafeAPIError):
            self.execute()
        self.api.upload.assert_not_called()
        self.api.create_album.assert_not_called()

    def test_shared_destination_ambiguous_creation_blocks_other_sources(self):
        self.api.create_album.side_effect = AmbiguousResult('uncertain')
        with self.assertRaises(AmbiguousResult):
            self.execute()
        self.albums = self.albums[1:]
        with self.assertRaises(AmbiguousResult):
            self.execute()
        self.assertEqual(self.api.create_album.call_count, 1)

    def test_default_keys_unchanged_and_destination_changes_job_identity(self):
        album = self.albums[0]
        default = Album(album.folder, album.when, album.photos)
        self.assertEqual(default.key, default.destination_key)
        self.assertNotEqual(default.key, album.key)
        self.assertEqual(self.albums[0].destination_key, self.albums[1].destination_key)
