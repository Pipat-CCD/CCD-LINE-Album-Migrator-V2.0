# CCD LINE Album Migrator V2.0

โปรแกรมภาษาไทยสำหรับ Windows 11 เพื่อย้ายภาพจากโฟลเดอร์อัลบั้ม LINE ไปยัง Google Photos ของ `ccdphoto@ccdthailand.org` พร้อมปรับวันที่บน **ไฟล์สำเนา** เท่านั้น

สร้างใหม่ตามคำอนุญาตของผู้ใช้ เนื่องจากรีโพซิทอรีเดิมมีเพียงไฟล์ว่าง `LineCCDPics` ไม่มีโค้ด V1 ให้ตรวจสอบหรือใช้ต่อ ไม่ได้แก้ไฟล์ V1 บนไดรฟ์ D: และไม่ได้ย้าย token เดิมโดยอัตโนมัติ

## สถานะการส่งมอบ

มี Source Code, GUI, OAuth, เครื่องมือ Dry Run, SQLite Resume, รายงาน CSV และสคริปต์ build Windows ผลตรวจจริงดู [VALIDATION.md](VALIDATION.md) **ยังไม่ใช่ EXE ที่ผ่านการรับรองบน Windows และยังไม่ยืนยันการอัปโหลด Google Photos จริง** อย่าเริ่มทั้ง 100 อัลบั้มจนกว่าทดสอบอัลบั้มเล็กบนบัญชีองค์กรสำเร็จ

## ติดตั้งบน Windows 11

1. ติดตั้ง Python 3.12 แบบ 64-bit รวม Tcl/Tk และ Python Launcher
2. แตกโค้ดในโฟลเดอร์ใหม่ เช่น `D:\CCD_LINE_Migrator_V2` แยกจาก V1 และรูปต้นฉบับ
3. ดาวน์โหลด ExifTool Windows 13.59 จาก [เว็บไซต์ผู้พัฒนา](https://exiftool.org/) เก็บ **ทั้งโฟลเดอร์** รวม `exiftool_files` เปลี่ยนชื่อ `exiftool(-k).exe` เป็น `exiftool.exe` ตรวจ checksum ตามที่ผู้พัฒนาเผยแพร่ อย่าปิดการตรวจ TLS หรือ antivirus
4. เปิด PowerShell ในโฟลเดอร์โค้ด แล้วรัน:

```powershell
.\setup.ps1
.\run.ps1
```

หรือดับเบิลคลิก **Setup.cmd** เพื่อติดตั้ง แล้วเปิด **Start.cmd** เพื่อเข้าโปรแกรม โดยไม่ต้องรัน PowerShell scripts

หากนโยบายองค์กรห้ามรัน PowerShell scripts ให้ติดต่อผู้ดูแล หรือรันคำสั่ง Python โดยตรง ไม่ต้องเปลี่ยนนโยบายระบบ:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe main.py
```

## ตั้งค่า Google Cloud และบัญชี

- ในโครงการ `CCD-LINE-Photos` เปิด Google Photos Library API ตั้ง OAuth consent และตรวจว่าองค์กรอนุญาตให้บัญชี `ccdphoto@ccdthailand.org` ใช้แอป
- ดาวน์โหลด OAuth **Desktop** Client `CCD LINE Migrator Windows` เก็บ `client_secret.json` นอกรีโพซิทอรี เช่นในโฟลเดอร์ผู้ใช้ส่วนตัว
- เลือกไฟล์ดังกล่าวและ ExifTool ในแท็บ **ตั้งค่าบัญชี Google** แล้วกดเชื่อมต่อ เลือกบัญชีองค์กร
- ขอ `photoslibrary.appendonly` เพื่อสร้างรายการใหม่ พร้อม `openid` และ `userinfo.email` เพื่อยืนยันบัญชี ไม่ขออ่านคลังรูปทั้งหมด
- token เดิมที่มีเฉพาะ appendonly ต้องขอ consent เพิ่มสิทธิ์อีเมล โปรแกรมไม่ถือว่าข้อความ “authentication flow completed” ยืนยันบัญชีหรือการอัปโหลดแล้ว
- โปรแกรมบล็อกทุกการอัปโหลดจนกว่าข้อมูลอีเมลที่ยืนยันแล้วตรงกับบัญชีปลายทาง
- บน Windows token เก็บแบบเข้ารหัส DPAPI ของผู้ใช้ใน `%LOCALAPPDATA%\CCDLineMigrator\token.json`; บน Linux ใช้ไฟล์สิทธิ์ 0600 ห้ามส่ง token/client secret ในแชทหรือ commit
- ถ้า OAuth app อยู่สถานะ Testing อายุ refresh token อาจจำกัดตามนโยบาย Google ต้องเชื่อมต่อใหม่เมื่อ refresh ไม่สำเร็จ

## ขั้นตอนใช้งาน

1. กด **เพิ่มอัลบั้ม** หรือ **เพิ่มหลายอัลบั้ม** แล้วเลือกโฟลเดอร์แม่ที่มีอัลบั้มเป็นโฟลเดอร์ย่อย โปรแกรมอ่านเฉพาะรูปในแต่ละโฟลเดอร์ ไม่ไล่ recursive เพื่อป้องกันรวมอัลบั้มผิด
2. ตรวจและยืนยันวันที่แต่ละอัลบั้ม `9-5-68` เสนอวันที่ `2025-05-09` โดยตีความปี 68 เป็น พ.ศ. 2568 ต้องยืนยันในหน้าต่างก่อนใช้ ไม่ใช้วันที่สร้างโฟลเดอร์เป็นหลักฐานวันที่อัลบั้ม LINE
3. ตรวจตารางรูปเสียและซ้ำ กด **Preview / metadata** เพื่อดูรูปและ metadata เดิม วันที่สำเนาใช้เวลา 00:00:00 Bangkok `+07:00`
4. กด **Dry Run** จะสร้างสำเนาในโฟลเดอร์ข้อมูลผู้ใช้ เขียน EXIF/XMP ด้วย ExifTool ตรวจ DateTimeOriginal, CreateDate, ModifyDate และ offset หลังเขียน แล้วตรวจ SHA-256 ว่าต้นฉบับไม่เปลี่ยน ขั้นตอนนี้ไม่เชื่อมต่อ Google Photos
5. หลังผ่าน Dry Run กด **เริ่มอัปโหลด / Resume** และยืนยันในหน้าต่าง โปรแกรมตรวจบัญชีอีกครั้ง สร้างอัลบั้มชื่อเดิม และสร้าง media item เข้าอัลบั้มที่แอปสร้าง
6. **Pause** จะรอไฟล์ปัจจุบันเสร็จแล้วหยุดก่อนรายการถัดไป กดอีกครั้งเพื่อทำต่อ ปุ่มหยุดรอคำขอปัจจุบันเสร็จเพื่อบันทึกผล ปิดแล้วเปิดใหม่ได้: รายการอัลบั้มและสถานะจะถูกโหลดกลับ ต้อง Dry Run อีกครั้งก่อน Resume
7. ส่งออกรายงาน CSV และตรวจใน Google Photos ว่าจำนวนรูป ชื่ออัลบั้ม และวันที่แสดงถูกต้องก่อนเพิ่มงาน Batch

## รูปแบบไฟล์และสำเนา

นำเข้า JPG/JPEG, PNG, HEIC/HEIF, AVIF, BMP, GIF, ICO, TIFF และ WEBP ตามความสามารถของ Pillow/HEIF decoder หาก decode ไม่ได้จะถูกระบุเป็นไฟล์เสีย/ไม่รองรับ ไม่รองรับ RAW หรือวิดีโอในรุ่นนี้ แม้ Google อาจรับบางรูปแบบดังกล่าว

JPG/PNG คัดลอกก่อนเขียน metadata รูปแบบอื่นแปลงเป็น JPEG quality 95 พร้อมปรับ orientation ก่อนเขียน: การแปลงอาจสูญเสีย transparency, animation, multi-page, HDR และคุณภาพบางส่วน **GIF/TIFF ใช้เฟรมแรกเท่านั้น** ตรวจ Preview และสำเนาก่อนอัปโหลด หากต้องเก็บคุณสมบัติเหล่านี้อย่าใช้การแปลงอัตโนมัติ มีการตรวจขนาดสำเนาไม่เกิน 200 MB

ตรวจซ้ำด้วย SHA-256 ภายในอัลบั้ม ไม่ deduplicate ข้ามอัลบั้ม เพราะรูปเดียวกันอาจตั้งใจอยู่หลายอัลบั้ม ขนาด storage ต้องพอสำหรับต้นฉบับและสำเนาทั้งหมด รูปขนาดใหญ่ decode อาจใช้ RAM สูง

## Resume และข้อจำกัดการป้องกันซ้ำ

SQLite บันทึกผลหลังแต่ละไฟล์ งาน `uploaded` จะถูกข้ามเมื่อ Resume คีย์งานอ้างอิง **บัญชีปลายทาง + เส้นทางโฟลเดอร์เต็ม + วันที่ + hash ต้นฉบับ** แยกสถานะระหว่างบัญชี อย่าย้ายโฟลเดอร์ เปลี่ยนวันที่ ลบฐานข้อมูล หรือสลับไปใช้ OAuth client อื่นระหว่างงาน เพราะอาจกลายเป็นงานใหม่ โปรแกรมกันเปิดสองหน้าต่างด้วย OS file lock

Google Photos ไม่มี transaction ร่วมกับ SQLite และ API ที่ใช้ไม่มี idempotency key รับรองการสร้างเพียงครั้งเดียว หากโปรแกรมปิด/เครือข่ายขาดหลัง Google รับคำขอแต่ก่อนบันทึกผล จะเก็บ `creating`/`uncertain` และ **หยุด ไม่ retry อัตโนมัติ** จึงไม่อ้างว่ารับรอง exactly-once ทุกกรณี Retry อัตโนมัติใช้กับ byte upload, คำขออ่านบัญชี และ rate limit ที่ตอบชัดเจน; 5xx/timeout ของคำขอสร้างรายการต้องตรวจสอบ

แท็บ **ประวัติ / กู้คืน** แสดงงานเดิม:

- หากตรวจในบัญชีองค์กรแล้วพบภาพจริง สามารถเลือก **ยืนยันภาพมีอยู่แล้ว** เพื่อบันทึก `confirmed_manual` และข้ามใน Resume สถานะนี้เป็นคำยืนยันของผู้ใช้ ไม่ใช่ผล API
- หากตรวจแล้วไม่มีรายการ สามารถเลือก **ยืนยันไม่มี / อนุญาต retry** การตรวจผิดอาจทำให้ซ้ำ ต้องตัดสินใจอย่างระมัดระวัง
- อัลบั้มที่ผลสร้างไม่แน่ชัดและไม่มี remote ID ยังไม่สามารถใช้ต่ออัตโนมัติด้วย appendonly อย่าอนุญาตสร้างใหม่ถ้ายังมีอัลบั้มเดิม ต้องตรวจและจัดการใน Google Photos ด้วยตนเองก่อน
- งาน `failed` ที่ Google ปฏิเสธชัดเจนสามารถแก้สิทธิ์/เครือข่ายแล้ว Resume ได้

ข้อมูลทั้งหมดอยู่ `%LOCALAPPDATA%\CCDLineMigrator`: `state.sqlite3`, `albums.json`, `settings.json`, `copies`, `token.json` สำรองทั้งโฟลเดอร์เมื่อโปรแกรมหยุดแล้ว โดยเฉพาะฐานข้อมูล ห้ามลบรูปต้นฉบับ ไม่มีปุ่มลบรูปบน Google Photos

## สร้าง EXE บน Windows

```powershell
.\build.ps1 -ExifToolDirectory 'D:\Tools\ExifTool-13.59'
```

ใช้ PyInstaller แบบ `onedir`, รวม HEIF decoder, tzdata และโฟลเดอร์ ExifTool ทั้งชุด ตรวจเวอร์ชันและเรียก self-check จาก EXE หลัง build ส่งมอบ **ทั้งโฟลเดอร์** `dist\CCDLineMigrator` เปิด `CCDLineMigrator.exe` ได้โดยไม่ต้องติดตั้ง Python Build ไม่รวม OAuth secret, token หรือข้อมูลอัลบั้ม ไม่ใช่ MSI installer และยังไม่มี code signing ต้องทดสอบ Windows 11 เครื่องสะอาดก่อนใช้งานจริง

## ทดสอบโดยไม่อัปโหลด

```powershell
$env:CCD_TEST_EXIFTOOL = 'D:\Tools\ExifTool-13.59\exiftool.exe'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py --self-check --exiftool $env:CCD_TEST_EXIFTOOL
.\.venv\Scripts\python.exe main.py --dry-run 'D:\Albums\9-5-68' --date 2025-05-09 --output 'D:\CCD-DryRun' --exiftool $env:CCD_TEST_EXIFTOOL
.\.venv\Scripts\python.exe -m tests.integration_dry_run '.\work\integration-71'
```

ภาพใน integration test เป็นภาพจำลอง ไม่ใช่ภาพ LINE 71 ภาพขององค์กร ชุดทดสอบ API ใช้ mock และไม่ยืนยันว่า Google รับการอัปโหลดจริง หากไม่ตั้งตัวแปร ExifTool เทสต์ metadata จริงจะถูก skip

## API ที่ตรวจเอกสาร

ตรวจเอกสาร Google เมื่อ 9 ตุลาคม 2026: หลัง 31 มีนาคม 2025 Library API เน้นเนื้อหาที่แอปสร้าง `appendonly` ใช้อัปโหลด/สร้างอัลบั้มใหม่ได้ แต่ไม่ได้อ่านรูปทั้งหมดในบัญชี `batchCreate` ไม่เกิน 50 รายการ/คำขอ รุ่นนี้ส่งทีละรายการอย่าง serial เพื่อบันทึกผลทันที

- [API updates](https://developers.google.com/photos/support/updates)
- [Authorization](https://developers.google.com/photos/library/guides/authorization)
- [Upload media](https://developers.google.com/photos/library/guides/upload-media)

การเปลี่ยน EXIF ก่อนอัปโหลดไม่ใช่หลักฐานว่า Google จะแสดงวันที่ตามต้องการ ต้องตรวจภาพจริงหลังอัปโหลดด้วยบัญชีองค์กร โควตา พื้นที่จัดเก็บ และนโยบายผู้ดูแลเป็นข้อกำหนดภายนอก โปรแกรมไม่สามารถอ่านข้อความวันที่สร้างอัลบั้มจาก LINE API ในรุ่นนี้
