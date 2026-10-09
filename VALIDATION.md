# ผลการตรวจสอบ — 9 ตุลาคม 2026

## สิ่งที่ทดสอบแล้ว

สภาพแวดล้อม Linux, Python 3.12.14, ExifTool 13.59 จาก official Git tag `13.59`, commit `2200871d9cef988051d2a99d67df3bda6cbb30a8` ใช้ TLS และไม่ปิดการตรวจสอบความถูกต้อง

- `unittest discover`: 51 tests ผ่าน ไม่มี skip เมื่อกำหนด `CCD_TEST_EXIFTOOL` รวมการรับบัญชี `ccdphoto@ccdthailand.org` และปฏิเสธบัญชีปลายทางเดิมด้วย API mock
- การแก้ TimeoutExpired: ตรวจชื่อ `exiftool(-k).exe` ก่อนเรียก, ปิด stdin, ตรวจ startup version, แสดงข้อความ timeout ที่ปลอดภัย และทดสอบ process ที่ค้างจริงแล้วถูกยุติเมื่อครบ timeout ไม่ใช่การทดสอบ ExifTool Windows launcher บน Windows จริง
- เขียน metadata ด้วย ExifTool จริงใน JPEG, PNG ที่ไม่มี EXIF และ HEIC ที่แปลงเป็น JPEG: ตรวจอ่าน DateTimeOriginal, CreateDate, ModifyDate, OffsetTimeOriginal และตรวจ hash ต้นฉบับ
- ตรวจ filesystem Date modified ของสำเนาให้เป็น `2025-05-09 00:00:00 Asia/Bangkok` และตรวจ Date modified ของต้นฉบับไม่เปลี่ยนบน Linux; การแสดงผล Windows Explorer ยังต้องทดสอบบน Windows
- Dry Run 71 ภาพจำลอง: JPEG 60, PNG 10, HEIC 1 วันที่ `2025-05-09 00:00:00 +07:00` ตรวจ metadata ครบ 71 และ hash ต้นฉบับคงเดิม รันซ้ำผ่านและจำนวนสำเนายังเป็น 71
- Batch 100 อัลบั้มพร้อม Resume โดย API mock: สร้างรายการ 100 ครั้ง รวมหลัง Resume ยัง 100 ครั้ง ไม่เรียกอัปโหลดไฟล์สำเร็จซ้ำ
- Mock tests สำหรับบัญชีผิด, อีเมลไม่ยืนยัน, 429 retry, 5xx/timeout ที่ผลไม่แน่ชัด, การปกปิดข้อมูลลับใน exception, pause/cancel และล็อกหลาย instance
- GUI smoke บน Tk 9.0 และ Xvfb จริง: สร้าง widgets, เพิ่มอัลบั้ม, Dry Run จริง, ปฏิเสธหน้าต่างอัปโหลดแล้วไม่มี worker เริ่ม, โหลดประวัติ, ปิดและเปิดกลับแล้วคืนรายการอัลบั้ม
- ตรวจปุ่มเปิดสำเนาเลือกเส้นทางโฟลเดอร์ที่ engine สร้างจริง โดย mock เฉพาะการเปิดตัวจัดการไฟล์; ยังไม่ได้ทดสอบการเปิด Windows Explorer บน Windows
- `pip check`: ไม่มี dependency conflict
- CLI `--self-check`: ExifTool 13.59, parser `9-5-68` เป็น `2025-05-09`
- Persistent ExifTool: ใช้ process ID เดิมสำหรับหลายภาพและหลายคำสั่ง ตรวจ status ของทุกคำสั่ง รวมชื่อไฟล์/โฟลเดอร์ภาษาไทย คำสั่งผิดไม่ถูกนับเป็นผ่าน timeout ยุติ process และ context ปิด process หลังงาน
- Upload pipeline ด้วย API จำลอง 71 ภาพ: ส่ง bytes พร้อมกันจริงใน threads สูงสุด 3, เรียก batchCreate แบบ serial 4 ชุด (20/20/20/11), บันทึก creating ทั้งชุดก่อนส่ง, Resume ไม่ส่งสำเร็จซ้ำ, แยกผล partial, หยุดผล ambiguous, ยกเลิกหลังส่ง bytes แล้วไม่สร้าง media
- Cache สำเนา: Dry Run จริงกับ ExifTool แล้วใช้สำเนาเดิมโดยไม่เรียก prepare ซ้ำใน pipeline API mock; ตรวจ hash/metadata/mtime ก่อนใช้ และปฏิเสธสำเนาที่ถูกแก้หรือเสียหาย การทดสอบนี้ไม่ยืนยันความเร็ว Google Photos จริง
- HTTP diagnostics/retry tests: raw upload 409/403 ไม่ retry, transient retry rewind ส่งข้อมูลครบ, 429 จำกัด 5 ครั้งโดยไม่มี loop ซ้อน, 409 ของ batchCreate บันทึกเป็นผลไม่แน่ชัดและไม่ retry อัตโนมัติ ไม่เปิดเผยข้อความ/token จาก response การทดสอบใช้ API mock และไม่ยืนยันสาเหตุ 409 บนเครื่องผู้ใช้
- วัดเวลา prepare 71 ภาพจำลอง (JPEG 60, PNG 10, HEIC 1): แบบเปิด process ต่อคำสั่ง 21.916 วินาที; แบบ persistent 0.799 วินาที (~27.43 เท่า) บน Linux เดียวกัน รัน baseline ก่อน persistent โดยไม่รวม scan, GUI หรือ network ตัวเลขนี้ไม่รับประกันความเร็วบน Windows/รูปจริง และไม่ใช่ benchmark หลายรอบ

## สิ่งที่ยังไม่ทดสอบ

- ภาพ LINE จริง 71 ภาพขององค์กรยังไม่ได้รับมา ภาพทดสอบทั้งหมดเป็นภาพสร้างขึ้น
- OAuth จริง, token refresh จริง, ยืนยันบัญชี `ccdphoto@ccdthailand.org` ผ่าน Google จริง, อัปโหลดจริง, การสร้างอัลบั้มจริง และวันที่ที่ Google Photos แสดงหลังอัปโหลด
- GUI บน Windows 11, DPAPI และ Windows file lock บน Windows จริง: Linux tests ไม่ใช่หลักฐานรับรองส่วนนี้
- `setup.ps1`, `build.ps1`, Setup.cmd และ Start.cmd บน Windows จริง และ EXE ที่สร้างด้วย PyInstaller
- ติดตั้งบนเครื่อง Windows สะอาด, นโยบายองค์กร, code signing และความจุ storage ของบัญชี

จึงส่งมอบเป็น **Source Code ที่ผ่านการทดสอบส่วน local และ API mock** ไม่ใช่โปรแกรม Windows ที่ผ่านการทดสอบ end-to-end แล้ว สคริปต์ build จะตรวจ ExifTool และเรียก self-check จาก EXE ที่แพ็กบน Windows แต่ยังไม่ได้รันบนเครื่องนี้

## การรับรองก่อนใช้จริง

มี Windows installer workflow เพิ่มแล้ว ตรวจผล Windows ล่าสุดจาก GitHub Actions และไฟล์ `installed-validation.json` ที่เผยแพร่คู่กับตัวติดตั้ง การเพิ่มสคริปต์เองไม่ใช่หลักฐานว่า Windows build/install ผ่าน สคริปต์ทดสอบติดตั้งจริง ตรวจโปรแกรมที่ติดตั้งเมื่อไม่มี Python/ExifTool ใน PATH, Dry Run 3 รูปแบบ, shortcut และการเก็บข้อมูลเมื่ออัปเดต/ถอนติดตั้ง และเผยแพร่ release เฉพาะเมื่อ job ทั้งหมดผ่าน

1. Windows 11: Setup.cmd / Start.cmd เปิดได้ เลือก ExifTool 13.59 และผ่านเทสต์ metadata จริง
2. ตรวจ DPAPI round-trip ในชุดทดสอบและสิทธิ์โฟลเดอร์ข้อมูลผู้ใช้
3. เชื่อมต่อ Desktop OAuth และยืนยันอีเมลองค์กรในแอป
4. Dry Run ภาพตัวอย่างจริง ตรวจสำเนาและ SHA-256 ต้นฉบับ
5. ผู้ใช้ยืนยันอัปโหลดอัลบั้มทดสอบเล็ก ตรวจจำนวนรูป วันที่ และชื่ออัลบั้มที่ Google Photos จริง
6. ทดสอบ Pause / Resume และปิดเปิดใหม่ ไม่มีรายการซ้ำ สำหรับเครือข่ายขาดที่ผลไม่แน่ชัดต้องตรวจด้วยตนเอง
7. Build บน Windows และทดสอบ EXE พร้อม ExifTool ทั้งโฟลเดอร์บน Windows อีกเครื่อง

ไม่มีการอัปโหลดภาพจริงหรือใช้ข้อมูลลับของผู้ใช้ระหว่างพัฒนา

## เลือกอัลบั้มปลายทาง — build 2.0.2

- API mock: สองต้นทางคนละวันที่แชร์อัลบั้มใหม่เพียงหนึ่งอัลบั้ม และ Resume ไม่ส่งภาพสำเร็จซ้ำ
- API mock: เลือก ID ที่แอปเคยบันทึกแล้ว ไม่เรียกสร้างอัลบั้มอีก; ปฏิเสธ ID ที่ไม่มีประวัติก่อนส่งรูป
- API mock: ผลสร้างอัลบั้มร่วมไม่แน่ชัดหยุดทั้งสองต้นทาง ไม่มี retry อัตโนมัติ
- GUI จริงบน Linux/Xvfb: เปิดหน้าต่างเลือกอัลบั้มเดิม เลือกจากประวัติ ใช้กับแถวต้นทาง แสดงชื่อปลายทาง บังคับ Dry Run ใหม่ และคืนปลายทางหลังเปิดโปรแกรมใหม่
- ยังไม่ได้ตรวจฟีเจอร์ปลายทางนี้กับบัญชี Google จริงหรือ Windows จริง

## Windows installer — ผลรันจริงที่ยังไม่ผ่าน

GitHub Actions run `37904921173` บน Windows 2022 หยุดที่การดาวน์โหลด ExifTool 13.59: แหล่ง SourceForge ตอบ HTTP 403 และไม่มีไฟล์ที่ผ่าน SHA-256 ที่ผู้พัฒนาเผยแพร่ ระบบไม่ใช้ไฟล์ที่ checksum ผิด ไม่ลดการตรวจ TLS และยังไม่ได้เริ่ม PyInstaller/Inno Setup หรือ automated install test ใน run นี้ ไม่มี Setup EXE หรือ release ที่ยืนยันว่าผ่านแล้ว

ใช้ `build-installer.ps1 -ExifToolDirectory <โฟลเดอร์ทางการที่แตก ZIP ครบชุด>` บนเครื่องที่เข้าถึงแพ็กเกจได้เพื่อข้ามขั้นดาวน์โหลด ส่วนการแพ็กและติดตั้งจริงยังต้องตรวจผล ไม่ใช่ขั้นตอนที่ทดสอบผ่านในคลาวด์นี้
