# ผลการตรวจสอบ — 9 ตุลาคม 2026

## สิ่งที่ทดสอบแล้ว

สภาพแวดล้อม Linux, Python 3.12.14, ExifTool 13.59 จาก official Git tag `13.59`, commit `2200871d9cef988051d2a99d67df3bda6cbb30a8` ใช้ TLS และไม่ปิดการตรวจสอบความถูกต้อง

- `unittest discover`: 19 tests ผ่าน ไม่มี skip เมื่อกำหนด `CCD_TEST_EXIFTOOL`
- เขียน metadata ด้วย ExifTool จริงใน JPEG, PNG ที่ไม่มี EXIF และ HEIC ที่แปลงเป็น JPEG: ตรวจอ่าน DateTimeOriginal, CreateDate, ModifyDate, OffsetTimeOriginal และตรวจ hash ต้นฉบับ
- Dry Run 71 ภาพจำลอง: JPEG 60, PNG 10, HEIC 1 วันที่ `2025-05-09 00:00:00 +07:00` ตรวจ metadata ครบ 71 และ hash ต้นฉบับคงเดิม รันซ้ำผ่านและจำนวนสำเนายังเป็น 71
- Batch 100 อัลบั้มพร้อม Resume โดย API mock: สร้างรายการ 100 ครั้ง รวมหลัง Resume ยัง 100 ครั้ง ไม่เรียกอัปโหลดไฟล์สำเร็จซ้ำ
- Mock tests สำหรับบัญชีผิด, อีเมลไม่ยืนยัน, 429 retry, 5xx/timeout ที่ผลไม่แน่ชัด, การปกปิดข้อมูลลับใน exception, pause/cancel และล็อกหลาย instance
- GUI smoke บน Tk 9.0 และ Xvfb จริง: สร้าง widgets, เพิ่มอัลบั้ม, Dry Run จริง, ปฏิเสธหน้าต่างอัปโหลดแล้วไม่มี worker เริ่ม, โหลดประวัติ, ปิดและเปิดกลับแล้วคืนรายการอัลบั้ม
- `pip check`: ไม่มี dependency conflict
- CLI `--self-check`: ExifTool 13.59, parser `9-5-68` เป็น `2025-05-09`

## สิ่งที่ยังไม่ทดสอบ

- ภาพ LINE จริง 71 ภาพขององค์กรยังไม่ได้รับมา ภาพทดสอบทั้งหมดเป็นภาพสร้างขึ้น
- OAuth จริง, token refresh จริง, ยืนยันบัญชี `photos@ccdthailand.org` ผ่าน Google จริง, อัปโหลดจริง, การสร้างอัลบั้มจริง และวันที่ที่ Google Photos แสดงหลังอัปโหลด
- GUI บน Windows 11, DPAPI และ Windows file lock บน Windows จริง: Linux tests ไม่ใช่หลักฐานรับรองส่วนนี้
- `setup.ps1`, `build.ps1`, Setup.cmd และ Start.cmd บน Windows จริง และ EXE ที่สร้างด้วย PyInstaller
- ติดตั้งบนเครื่อง Windows สะอาด, นโยบายองค์กร, code signing และความจุ storage ของบัญชี

จึงส่งมอบเป็น **Source Code ที่ผ่านการทดสอบส่วน local และ API mock** ไม่ใช่โปรแกรม Windows ที่ผ่านการทดสอบ end-to-end แล้ว สคริปต์ build จะตรวจ ExifTool และเรียก self-check จาก EXE ที่แพ็กบน Windows แต่ยังไม่ได้รันบนเครื่องนี้

## การรับรองก่อนใช้จริง

1. Windows 11: Setup.cmd / Start.cmd เปิดได้ เลือก ExifTool 13.59 และผ่านเทสต์ metadata จริง
2. ตรวจ DPAPI round-trip ในชุดทดสอบและสิทธิ์โฟลเดอร์ข้อมูลผู้ใช้
3. เชื่อมต่อ Desktop OAuth และยืนยันอีเมลองค์กรในแอป
4. Dry Run ภาพตัวอย่างจริง ตรวจสำเนาและ SHA-256 ต้นฉบับ
5. ผู้ใช้ยืนยันอัปโหลดอัลบั้มทดสอบเล็ก ตรวจจำนวนรูป วันที่ และชื่ออัลบั้มที่ Google Photos จริง
6. ทดสอบ Pause / Resume และปิดเปิดใหม่ ไม่มีรายการซ้ำ สำหรับเครือข่ายขาดที่ผลไม่แน่ชัดต้องตรวจด้วยตนเอง
7. Build บน Windows และทดสอบ EXE พร้อม ExifTool ทั้งโฟลเดอร์บน Windows อีกเครื่อง

ไม่มีการอัปโหลดภาพจริงหรือใช้ข้อมูลลับของผู้ใช้ระหว่างพัฒนา
