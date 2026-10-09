"""Run against a real Tk display. No OAuth or real uploads."""
import os
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from migrator.gui import App
from migrator.core import album_date, Ledger


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
    app.table.selection_set(str(source.resolve()))
    with patch('migrator.gui.open_directory') as opened:
        app.open_copies()
        copies = app.data / 'copies' / app.albums[str(source.resolve())].key
        opened.assert_called_once_with(copies)
        assert copies.is_dir()
        assert list(copies.glob('*.png')), 'opened copy folder has no prepared photos'
    app.table.selection_remove(*app.table.selection())
    with patch('migrator.gui.messagebox.showinfo') as info, patch('migrator.gui.open_directory') as opened:
        app.open_copies()
        info.assert_called_once()
        opened.assert_not_called()
    with patch('migrator.gui.messagebox.askyesno', return_value=False) as confirmation:
        app.start(True)
        confirmation.assert_called_once()
        assert not app.busy(), 'cancelled confirmation started a worker'
    app.load_history()
    assert len(app.history.get_children()) == 1
    app.history.selection_set(app.history.get_children()[0])
    with patch('migrator.gui.messagebox.showinfo') as info:
        app.history_detail()
        info.assert_called_once()
        assert 'prepared' in info.call_args.args[1]
    ledger = Ledger(app.data / 'state.sqlite3')
    ledger.db.execute('INSERT INTO albums VALUES(?,?,?,?)', ('fixture-old', 'CCD ปี 2025', 'fixture-remote', 'ready'))
    ledger.db.commit()
    ledger.close()
    app.table.selection_set(str(source.resolve()))
    app.choose_destination()
    root.update()
    dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    apply_button = next(w for w in dialog.winfo_children() if w.winfo_class() == 'TButton')
    apply_button.invoke()
    assert app.albums[str(source.resolve())].destination_id == 'fixture-remote'
    assert app.table.set(str(source.resolve()), 'destination') == 'CCD ปี 2025'
    assert not app.dry_ready, 'destination changes must require a new dry run'
    album = app.albums[str(source.resolve())]
    ledger = Ledger(app.data / 'state.sqlite3')
    ledger.record(album.key, album.photos[0], 'uploaded', 'fixture-media')
    ledger.close()
    app.choose_destination()
    root.update()
    dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    radios = [w for w in dialog.winfo_children() if w.winfo_class() == 'TRadiobutton']
    radios[0].invoke()
    with patch('migrator.gui.messagebox.showwarning') as warning:
        next(w for w in dialog.winfo_children() if w.winfo_class() == 'TButton').invoke()
        warning.assert_called_once()
    assert album.destination_id == 'fixture-remote', 'uploaded job was silently retargeted'
    dialog.destroy()
    app.close()
    root = tk.Tk()
    restored = App(root)
    root.update()
    assert len(restored.albums) == 1, 'persisted albums were not restored'
    assert next(iter(restored.albums.values())).destination_id == 'fixture-remote'
    assert not restored.dry_ready, 'restart must require a fresh dry run'
    restored.close()
    print('GUI smoke passed: real Tk widgets, Dry Run, correct copy folder opening, cancelled upload, history, restart restore')
