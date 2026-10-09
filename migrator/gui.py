from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from .core import Ledger, album_date, find_exiftool, metadata, scan
from .engine import Album, Control, run
from .google_photos import PhotosAPI, SafeAPIError, authenticate
from .lock import InstanceLock


def data_directory():
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share'))
    path = root / 'CCDLineMigrator'
    path.mkdir(parents=True, exist_ok=True)
    return path


class App:
    def __init__(self, root):
        self.root = root
        self.root.title('CCD LINE Album Migrator V2.0')
        self.root.geometry('1100x750')
        self.data = data_directory()
        self.instance_lock = InstanceLock(self.data / 'instance.lock')
        self.config_path = self.data / 'settings.json'
        self.config = {}
        if self.config_path.exists():
            try:
                self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
                if not isinstance(self.config, dict):
                    self.config = {}
            except (ValueError, OSError):
                pass
        self.albums = {}
        self.events = queue.Queue()
        self.worker = None
        self.control = Control()
        self.dry_ready = False
        self.photo_image = None
        notebook = ttk.Notebook(root)
        notebook.pack(fill='both', expand=True)
        dashboard = ttk.Frame(notebook, padding=12)
        settings = ttk.Frame(notebook, padding=12)
        history = ttk.Frame(notebook, padding=12)
        notebook.add(dashboard, text='อัลบั้มและประวัติ')
        notebook.add(settings, text='ตั้งค่าบัญชี Google')
        notebook.add(history, text='ประวัติ / กู้คืน')
        ttk.Label(history, text='uncertain / creating: ระบบยืนยันผลจาก Google ไม่ได้ จึงไม่ retry อัตโนมัติ\n'
                  'ตรวจใน Google Photos ด้วยตัวเองก่อนตัดสินใจ การยืนยันผิดอาจทำให้รูปซ้ำ').pack(anchor='w')
        self.history = ttk.Treeview(history, columns=('state', 'source'), height=18)
        self.history.heading('#0', text='ประเภท')
        self.history.heading('state', text='สถานะ')
        self.history.heading('source', text='ชื่อ / ต้นทาง')
        self.history.column('source', width=650)
        self.history.pack(fill='both', expand=True, pady=8)
        toolbar = ttk.Frame(history)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='โหลดประวัติ', command=self.load_history).pack(side='left')
        ttk.Button(toolbar, text='ยืนยันภาพมีอยู่แล้ว', command=lambda: self.reconcile(True)).pack(side='left')
        ttk.Button(toolbar, text='ยืนยันไม่มี / อนุญาต retry', command=lambda: self.reconcile(False)).pack(side='left')
        self.status = tk.StringVar(value='เลือกโฟลเดอร์ แล้วตรวจสอบวันที่ก่อน Dry Run')
        ttk.Label(dashboard, textvariable=self.status).pack(anchor='w')
        buttons = ttk.Frame(dashboard)
        buttons.pack(fill='x', pady=8)
        self.edit_buttons = []
        for label, command in [('เพิ่มอัลบั้ม', self.add_one), ('เพิ่มหลายอัลบั้ม', self.add_batch),
                               ('แก้วันที่', self.edit_date), ('ลบจากรายการ', self.remove),
                               ('Preview / metadata', self.preview)]:
            button = ttk.Button(buttons, text=label, command=command)
            button.pack(side='left', padx=3)
            self.edit_buttons.append(button)
        self.table = ttk.Treeview(dashboard, columns=('date', 'count', 'bad', 'dup'), height=9)
        self.table.heading('#0', text='อัลบั้ม / โฟลเดอร์')
        for key, title in [('date', 'วันที่ ค.ศ. (ยืนยันแล้ว)'), ('count', 'จำนวนรูป'),
                           ('bad', 'ไฟล์เสีย'), ('dup', 'ซ้ำในอัลบั้ม')]:
            self.table.heading(key, text=title)
            self.table.column(key, width=140)
        self.table.pack(fill='x')
        self.actions = ttk.Frame(dashboard)
        self.actions.pack(fill='x', pady=8)
        self.dry_button = ttk.Button(self.actions, text='Dry Run (สร้างสำเนา + ตรวจวันที่)', command=lambda: self.start(False))
        self.dry_button.pack(side='left', padx=3)
        self.upload_button = ttk.Button(self.actions, text='เริ่มอัปโหลด / Resume', command=lambda: self.start(True))
        self.upload_button.pack(side='left', padx=3)
        ttk.Button(self.actions, text='Pause / ทำต่อ', command=self.pause).pack(side='left', padx=3)
        ttk.Button(self.actions, text='หยุดหลังไฟล์ปัจจุบัน', command=self.cancel).pack(side='left', padx=3)
        ttk.Button(self.actions, text='ส่งออกรายงาน CSV', command=self.report).pack(side='left', padx=3)
        self.progress = ttk.Progressbar(dashboard, mode='determinate')
        self.progress.pack(fill='x')
        self.log = tk.Text(dashboard, height=13, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True, pady=8)
        ttk.Label(settings, text='ปลายทางบังคับ: ccdphoto@ccdthailand.org\n'
                  'ขอสิทธิ์ appendonly + openid/email เพื่อตรวจสอบบัญชี\n'
                  'token เก็บในโฟลเดอร์ข้อมูลผู้ใช้ ห้ามส่งให้ผู้อื่น').pack(anchor='w', pady=10)
        self.client = tk.StringVar(value=self.config.get('client', ''))
        self.tool = tk.StringVar(value=self.config.get('tool', ''))
        for label, var in [('OAuth Desktop client_secret.json', self.client), ('ExifTool executable', self.tool)]:
            ttk.Label(settings, text=label).pack(anchor='w')
            frame = ttk.Frame(settings)
            frame.pack(fill='x', pady=6)
            ttk.Entry(frame, textvariable=var).pack(side='left', fill='x', expand=True)
            ttk.Button(frame, text='เลือกไฟล์', command=lambda v=var: self.choose_file(v)).pack(side='left')
        ttk.Button(settings, text='บันทึกการตั้งค่า', command=self.save_settings).pack(anchor='w', pady=8)
        self.auth_button = ttk.Button(settings, text='เชื่อมต่อ / ตรวจบัญชี Google', command=self.connect)
        self.auth_button.pack(anchor='w', pady=8)
        ttk.Label(settings, text=f'ข้อมูลและประวัติ: {self.data}\n'
                  'อย่าลบ state.sqlite3: ใช้ป้องกันอัปโหลดซ้ำ\n'
                  'การ Pause รอคำขอที่กำลังทำอยู่จบก่อน ไม่ยกเลิก HTTP กลางคัน').pack(anchor='w', pady=10)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.restore_albums()
        self.load_history()
        self.root.after(100, self.poll)

    def save_albums(self):
        values = [{'folder': str(a.folder.resolve()), 'date': a.when.isoformat()} for a in self.albums.values()]
        path = self.data / 'albums.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)

    def restore_albums(self):
        path = self.data / 'albums.json'
        if not path.exists():
            return
        try:
            for item in json.loads(path.read_text(encoding='utf-8')):
                folder = Path(item['folder'])
                if folder.is_dir():
                    self.insert_album(folder, album_date(item['date']))
        except (OSError, ValueError, KeyError, TypeError):
            self.status.set('อ่านรายการเดิมไม่ครบ กรุณาเลือกโฟลเดอร์ใหม่')

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def load_history(self):
        if self.busy():
            return
        self.history.delete(*self.history.get_children())
        self.history_rows = {}
        ledger = Ledger(self.data / 'state.sqlite3')
        try:
            for key, title, remote_id, state in ledger.db.execute('SELECT * FROM albums'):
                iid = self.history.insert('', 'end', text='อัลบั้ม', values=(state, title))
                self.history_rows[iid] = ('album', key, None, state)
            for key, sha, source, state in ledger.db.execute('SELECT album,sha,source,state FROM photos'):
                iid = self.history.insert('', 'end', text='ภาพ', values=(state, source))
                self.history_rows[iid] = ('photo', key, sha, state)
        finally:
            ledger.close()

    def reconcile(self, exists):
        if self.busy() or len(self.history.selection()) != 1:
            return
        kind, key, sha, state = self.history_rows[self.history.selection()[0]]
        if state not in ('uncertain', 'creating'):
            messagebox.showinfo('กู้คืน', 'เลือกเฉพาะรายการ uncertain หรือ creating')
            return
        if kind == 'album' and exists:
            messagebox.showinfo('กู้คืนอัลบั้ม', 'ต้องมี album ID ที่แอปบันทึกไว้เพื่อใช้ต่อ\n'
                                'รายการนี้ไม่มี ID ที่ยืนยันแล้ว จึงไม่เปลี่ยนสถานะ')
            return
        action = 'ยืนยันภาพมีอยู่แล้ว (ข้ามในการ Resume)' if exists else 'ยืนยันไม่มีรายการ และอนุญาตลองสร้างใหม่'
        if not messagebox.askyesno('ยืนยันการกู้คืนด้วยตนเอง', action + '\n'
                                  'คุณได้ตรวจสอบในบัญชี ccdphoto@ccdthailand.org แล้วใช่หรือไม่?\n'
                                  'ถ้าตรวจผิด อาจเกิดรายการซ้ำ ระบบตรวจคลังรูปแทนคุณไม่ได้'):
            return
        ledger = Ledger(self.data / 'state.sqlite3')
        try:
            if kind == 'photo':
                ledger.db.execute('UPDATE photos SET state=?,message=? WHERE album=? AND sha=?',
                    ('confirmed_manual' if exists else 'failed', 'ผู้ใช้ยืนยันผลด้วยตนเอง', key, sha))
            else:
                ledger.db.execute('UPDATE albums SET state=? WHERE key=?', ('failed', key))
            ledger.db.commit()
        finally:
            ledger.close()
        self.dry_ready = False
        self.load_history()

    def choose_file(self, variable):
        if self.busy():
            return
        value = filedialog.askopenfilename()
        if value:
            variable.set(value)

    def save_settings(self):
        self.config_path.write_text(json.dumps({'client': self.client.get(), 'tool': self.tool.get()}), encoding='utf-8')

    def choose_date(self, folder, initial=None):
        suggestion = initial or ''
        if not suggestion:
            try:
                suggestion = album_date(folder.name).isoformat()
            except ValueError:
                pass
        text = simpledialog.askstring('ยืนยันวันที่อัลบั้ม',
            f'{folder.name}\nใช้ YYYY-MM-DD หรือชื่อแบบ 9-5-68\n'
            'ปี 68 ตีความเป็น พ.ศ. 2568 = ค.ศ. 2025 โปรดยืนยันความหมาย', initialvalue=suggestion)
        if text is None:
            return None
        try:
            when = album_date(text)
        except ValueError:
            messagebox.showerror('วันที่ไม่ถูกต้อง', 'กรุณาระบุวันที่ที่มีอยู่จริง')
            return None
        if messagebox.askyesno('ยืนยันวันที่', f'อัลบั้ม {folder.name}\nวันที่ {when.isoformat()}\n'
                               'เวลา 00:00:00 Asia/Bangkok (+07:00) ถูกต้องหรือไม่?'):
            return when

    def add_folder(self, folder):
        key = str(folder.resolve())
        if key in self.albums:
            return
        when = self.choose_date(folder)
        if when:
            self.insert_album(folder, when)
            self.save_albums()

    def insert_album(self, folder, when):
        key = str(folder.resolve())
        photos = scan(folder)
        self.albums[key] = Album(folder, when, photos)
        self.table.insert('', 'end', iid=key, text=folder.name,
                          values=(when.isoformat(), len(photos), sum(bool(p.error) for p in photos),
                                  sum(p.duplicate for p in photos)))
        self.dry_ready = False
        self.status.set(f'{len(self.albums)} อัลบั้ม / {sum(len(a.photos) for a in self.albums.values())} รูป')

    def add_one(self):
        value = filedialog.askdirectory()
        if value:
            self.add_folder(Path(value))

    def add_batch(self):
        value = filedialog.askdirectory(title='เลือกโฟลเดอร์แม่ที่มีโฟลเดอร์อัลบั้มอยู่ภายใน')
        if value:
            for folder in sorted(Path(value).iterdir()):
                if folder.is_dir():
                    self.add_folder(folder)

    def edit_date(self):
        for key in self.table.selection():
            album = self.albums[key]
            when = self.choose_date(album.folder, album.when.isoformat())
            if when:
                album.when = when
                self.table.set(key, 'date', when.isoformat())
                self.dry_ready = False
        self.save_albums()

    def remove(self):
        for key in self.table.selection():
            del self.albums[key]
            self.table.delete(key)
        self.dry_ready = False
        self.save_albums()

    def preview(self):
        selected = self.table.selection()
        if not selected:
            return
        album = self.albums[selected[0]]
        filename = filedialog.askopenfilename(initialdir=album.folder, title='เลือกภาพเพื่อดู Preview')
        if not filename:
            return
        try:
            window = tk.Toplevel(self.root)
            with Image.open(filename) as image:
                image.thumbnail((700, 450))
                preview = ImageTk.PhotoImage(image.copy())
            label = ttk.Label(window, image=preview)
            label.image = preview
            label.pack()
            current = metadata(Path(filename), find_exiftool(self.tool.get()))
            ttk.Label(window, text=json.dumps(current, ensure_ascii=False, indent=2) +
                      f'\nวันที่สำเนาที่จะเขียน: {album.when.isoformat()} 00:00:00 +07:00').pack()
        except Exception as exc:
            messagebox.showerror('Preview ไม่สำเร็จ', type(exc).__name__)

    def notify(self, message, done=0, total=1):
        self.events.put(('progress', message, done, total))

    def launch(self, job):
        if self.busy():
            return
        self.control = Control()
        for button in self.edit_buttons + [self.dry_button, self.upload_button, self.auth_button]:
            button.configure(state='disabled')
        def wrapper():
            try:
                job()
            except Exception as exc:
                # Never log arbitrary exception messages from OAuth/HTTP libraries.
                message = str(exc) if isinstance(exc, SafeAPIError) else type(exc).__name__
                self.events.put(('error', message))
            finally:
                self.events.put(('finished',))
        self.worker = threading.Thread(target=wrapper, daemon=True)
        self.worker.start()

    def connect(self):
        self.save_settings()
        client = Path(self.client.get())
        def job():
            credentials = authenticate(client, self.data / 'token.json', interactive=True)
            account = PhotosAPI(credentials).verify_account()
            self.notify(f'ยืนยันบัญชีสำเร็จ: {account}')
        self.launch(job)

    def start(self, upload):
        if self.busy() or not self.albums:
            return
        if upload and not self.dry_ready:
            messagebox.showwarning('ต้อง Dry Run ก่อน', 'กรุณาตรวจสำเนาและ metadata ให้ผ่านก่อนอัปโหลด')
            return
        if upload and not messagebox.askyesno('ยืนยันอัปโหลดจริง',
            f'จะอัปโหลด {len(self.albums)} อัลบั้ม ไป ccdphoto@ccdthailand.org\n'
            'Google Photos อาจคิดพื้นที่จัดเก็บ ต้องการดำเนินการหรือไม่?'):
            return
        try:
            tool = find_exiftool(self.tool.get())
        except RuntimeError as exc:
            messagebox.showerror('ExifTool', str(exc))
            return
        client = Path(self.client.get())
        albums = list(self.albums.values())
        if not upload:
            self.dry_ready = False
        def job():
            ledger = Ledger(self.data / 'state.sqlite3')
            try:
                api = PhotosAPI(authenticate(client, self.data / 'token.json')) if upload else None
                run(albums, ledger, self.data / 'copies', tool, self.control, self.notify, api)
                if not upload and not self.control.cancelled.is_set():
                    self.events.put(('dry_ready',))
            finally:
                ledger.close()
        self.launch(job)

    def pause(self):
        if self.busy():
            if self.control.running.is_set():
                self.control.running.clear()
                self.status.set('กำลังพัก: รอไฟล์ปัจจุบันเสร็จ แล้วหยุดก่อนไฟล์ถัดไป')
            else:
                self.control.running.set()
                self.status.set('ทำต่อ')

    def cancel(self):
        self.control.cancelled.set()
        self.control.running.set()

    def report(self):
        if self.busy():
            messagebox.showinfo('รายงาน', 'รอจบงานหรือหยุดก่อนส่งออกรายงาน')
            return
        filename = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='ccd-report.csv')
        if filename:
            ledger = Ledger(self.data / 'state.sqlite3')
            try:
                ledger.export(Path(filename))
            finally:
                ledger.close()

    def poll(self):
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == 'progress':
                _, text, done, total = event
                self.status.set(text)
                self.progress.configure(maximum=max(total, 1), value=done)
                self.log.configure(state='normal')
                self.log.insert('end', text + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
            elif event[0] == 'error':
                self.status.set('งานหยุด: ' + event[1])
                messagebox.showerror('งานหยุด', event[1])
            elif event[0] == 'dry_ready':
                self.dry_ready = True
            elif event[0] == 'finished':
                for button in self.edit_buttons + [self.dry_button, self.upload_button, self.auth_button]:
                    button.configure(state='normal')
        self.root.after(100, self.poll)

    def close(self):
        if self.busy():
            self.cancel()
            messagebox.showinfo('กำลังหยุด', 'รอคำขอปัจจุบันเสร็จ แล้วปิดอีกครั้ง เพื่อบันทึกผลให้ครบ')
            return
        self.root.destroy()
        self.instance_lock.close()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
