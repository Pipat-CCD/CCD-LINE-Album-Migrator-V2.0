ตัวติดตั้ง Windows 64-bit สำหรับ CCD LINE Album Migrator V2.0

ดาวน์โหลด `CCDLineMigrator-Setup.exe` แล้วติดตั้ง เปิดโปรแกรมจาก Start Menu ได้โดยไม่ต้องติดตั้ง Python หรือ ExifTool เพิ่ม

ครั้งแรกเลือก OAuth Desktop client_secret.json ขององค์กรและเชื่อมต่อบัญชี ccdphoto@ccdthailand.org เท่านั้น ตัวติดตั้งไม่มีข้อมูลลับหรือภาพขององค์กร

ตัวติดตั้งเก็บโปรแกรมในโฟลเดอร์ผู้ใช้ ไม่ต้องใช้สิทธิ์ Administrator ข้อมูลบัญชี สำเนา และประวัติอยู่ที่ `%LOCALAPPDATA%\CCDLineMigrator` แยกจากโปรแกรมและไม่ถูกลบเมื่ออัปเดตหรือถอนติดตั้ง

ตรวจ checksum ด้วย SHA256SUMS.txt ตัวติดตั้งยังไม่มี Authenticode code signing

ตรวจผลการ build และ automated install smoke test ใน GitHub Actions รุ่นนี้ยังต้องตรวจบน Windows 11 ของผู้ใช้และบัญชี Google จริงก่อนใช้กับข้อมูลทั้งหมด
