"""Run against a real Tk display. No OAuth or real uploads."""
import os
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from migrator.gui import App
from migrator.core import album_date


with tempfile.TemporaryDirectory() as temporary:
    os.environ['LOCALAPPDATA'] = str(Path(temporary) / 'appdata')
    source = Path(temporary) / '9-5-68'
    source.mkdir()
    Image.new('RGB', (32, 24), 'red').save(source / 'photo.png')
    root = tk.Tk()
    app = App(root)
    app.tool.set(os.environ['CCD_TEST_EXIFTOOL'])
    app.insert_album(source, album_date('9-5-68'))
    app.save_albums()
    root.update()
    assert len(app.table.get_children()) == 1
    app.start(False)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and (app.busy() or not app.dry_ready):
        root.update()
        time.sleep(0.02)
    assert app.dry_ready, app.status.get()
    with patch('migrator.gui.messagebox.askyesno', return_value=False) as confirmation:
        app.start(True)
        confirmation.assert_called_once()
        assert not app.busy(), 'cancelled confirmation started a worker'
    app.load_history()
    assert len(app.history.get_children()) == 1
    app.close()
    root = tk.Tk()
    restored = App(root)
    root.update()
    assert len(restored.albums) == 1, 'persisted albums were not restored'
    assert not restored.dry_ready, 'restart must require a fresh dry run'
    restored.close()
    print('GUI smoke passed: real Tk widgets, Dry Run, cancelled upload, history, restart restore')
