"""One noninteractive ExifTool process, with per-command status and deadlines."""
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from .core import LocalSetupError


class ExifToolSession:
    def __init__(self, tool):
        self.tool = tool
        self.process = None
        self.lines = queue.Queue()
        self.lock = threading.Lock()
        self.sequence = 0
        self.readers = []

    def __enter__(self):
        if '(-k)' in Path(self.tool).name.lower():
            raise LocalSetupError('กรุณาเปลี่ยนชื่อ exiftool(-k).exe เป็น exiftool.exe')
        try:
            self.process = subprocess.Popen([self.tool, '-stay_open', 'True', '-@', '-'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError:
            raise LocalSetupError('เปิด ExifTool ไม่ได้ ตรวจ executable และไฟล์ประกอบ') from None
        def read_output():
            try:
                for line in iter(self.process.stdout.readline, b''):
                    self.lines.put(line)
            finally:
                self.lines.put(None)
        def drain_errors():
            # Drain stderr to avoid deadlock; never expose arbitrary tool output.
            for _ in iter(self.process.stderr.readline, b''):
                pass
        for target in (read_output, drain_errors):
            reader = threading.Thread(target=target, daemon=True)
            reader.start()
            self.readers.append(reader)
        return self

    def execute(self, arguments, operation, timeout=180):
        with self.lock:
            if not self.process or self.process.poll() is not None:
                raise LocalSetupError('ExifTool ปิดก่อนจบงาน กรุณาตรวจ executable และเริ่ม Dry Run ใหม่')
            if any(any(c in arg for c in ('\r', '\n', '\x00')) for arg in arguments):
                raise LocalSetupError('ชื่อไฟล์มีอักขระขึ้นบรรทัดใหม่ที่ ExifTool แบบ batch ไม่รองรับ')
            self.sequence += 1
            marker = f'{{ccd-status{self.sequence}}}:'
            ready = f'{{ready{self.sequence}}}'
            payload = ['-charset', 'filename=UTF8', *arguments, '-echo3',
                       marker + '${status}', f'-execute{self.sequence}']
            try:
                self.process.stdin.write(('\n'.join(payload) + '\n').encode('utf-8'))
                self.process.stdin.flush()
            except (OSError, ValueError):
                self.close(force=True)
                raise LocalSetupError('ส่งคำสั่งไป ExifTool ไม่สำเร็จ งานหยุดและยังไม่ผ่านการตรวจวันที่') from None
            deadline = time.monotonic() + timeout
            output = []
            status = None
            while True:
                try:
                    line = self.lines.get(timeout=max(0, deadline - time.monotonic()))
                except queue.Empty:
                    self.close(force=True)
                    raise LocalSetupError(f'ExifTool เกิน {timeout} วินาทีขณะ{operation} งานหยุด '
                                          'ตรวจไฟล์และดิสก์ แล้ว Dry Run ใหม่') from None
                if line is None:
                    self.close(force=True)
                    raise LocalSetupError(f'ExifTool ปิดก่อนจบขั้นตอน{operation} งานยังไม่ผ่านการตรวจวันที่')
                text = line.decode('utf-8', errors='replace').strip()
                if text == ready:
                    break
                if text.startswith(marker):
                    status = text[len(marker):]
                else:
                    output.append(line)
            if status != '0':
                raise LocalSetupError(f'ExifTool ไม่สำเร็จขณะ{operation} ตรวจสิทธิ์/ไฟล์ประกอบและไฟล์ภาพ')
            return subprocess.CompletedProcess([self.tool], 0, stdout=b''.join(output), stderr=b'')

    def close(self, force=False):
        process = self.process
        if not process:
            return
        if process.poll() is None:
            if not force:
                try:
                    process.stdin.write(b'-stay_open\nFalse\n')
                    process.stdin.flush()
                    process.wait(timeout=2)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    force = True
            if force and process.poll() is None:
                process.kill()
                process.wait()
        for reader in self.readers:
            reader.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

    def __exit__(self, *args):
        self.close()
