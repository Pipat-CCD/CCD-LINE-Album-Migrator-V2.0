"""OS lock released automatically after a process crash."""
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, path: Path):
        self.stream = path.open('a+b')
        if path.stat().st_size == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('โปรแกรมกำลังทำงานอยู่แล้ว กรุณาปิดหน้าต่างเดิมก่อน') from None

    def close(self):
        self.stream.close()
