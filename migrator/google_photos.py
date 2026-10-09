from __future__ import annotations

import json
import time
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from . import token_store

SCOPES = ['https://www.googleapis.com/auth/photoslibrary.appendonly', 'openid',
          'https://www.googleapis.com/auth/userinfo.email']
BASE = 'https://photoslibrary.googleapis.com/v1'
EXPECTED_ACCOUNT = 'photos@ccdthailand.org'


class SafeAPIError(RuntimeError):
    pass


class AmbiguousResult(SafeAPIError):
    """A mutating request may have succeeded; automatic retry is unsafe."""


def authenticate(client: Path, token: Path, interactive=False) -> Credentials:
    credentials = None
    if token.exists():
        try:
            saved = token_store.load(token)
            # Do not assign requested scopes to an old token with unknown grants.
            if not set(SCOPES).issubset(set(saved.get('scopes', []))):
                raise ValueError('missing scopes')
            credentials = Credentials.from_authorized_user_info(saved)
        except Exception:
            raise SafeAPIError('อ่าน token ไม่ได้ กรุณาเชื่อมต่อบัญชีใหม่') from None
    if interactive:
        try:
            config = json.loads(client.read_text(encoding='utf-8'))
            if 'installed' not in config:
                raise ValueError('Desktop OAuth client required')
            flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
            credentials = flow.run_local_server(port=0, open_browser=True,
                                               prompt='consent select_account', access_type='offline')
        except Exception:
            raise SafeAPIError('OAuth ไม่สำเร็จ ตรวจสอบ Desktop Client และการตั้งค่า Google Cloud') from None
    elif credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except Exception:
            raise SafeAPIError('refresh token ไม่สำเร็จ กรุณาเชื่อมต่อบัญชีใหม่') from None
    if not credentials or not credentials.valid or not credentials.has_scopes(SCOPES):
        raise SafeAPIError('ต้องเชื่อมต่อ Google และอนุญาตสิทธิ์อัปโหลดกับตรวจสอบอีเมล')
    token_store.save(token, credentials.to_json())
    return credentials


class PhotosAPI:
    def __init__(self, credentials, sleeper=time.sleep):
        self.credentials = credentials
        self.session = requests.Session()
        self.sleep = sleeper
        self.account = None

    def _headers(self):
        if not self.credentials.valid:
            try:
                self.credentials.refresh(Request())
            except Exception:
                raise SafeAPIError('refresh token ไม่สำเร็จ') from None
        return {'Authorization': 'Bearer ' + self.credentials.token}

    def request(self, method, url, *, retry=False, mutating=False, **kwargs):
        custom = kwargs.pop('headers', {})
        for attempt in range(5):
            try:
                payload = kwargs.get('data')
                if hasattr(payload, 'seek'):
                    payload.seek(0)
                response = self.session.request(method, url, headers={**self._headers(), **custom},
                                                timeout=(15, 180), **kwargs)
            except requests.RequestException:
                if mutating:
                    raise AmbiguousResult('การเชื่อมต่อขาดระหว่างสร้างรายการ ต้องตรวจสอบก่อนทำต่อ') from None
                if retry and attempt < 4:
                    self.sleep(min(2 ** attempt, 30))
                    continue
                raise SafeAPIError('เชื่อมต่อ Google ไม่สำเร็จ') from None
            if response.status_code == 429 and attempt < 4:
                delay = response.headers.get('Retry-After', '')
                self.sleep(min(float(delay), 60) if delay.isdigit() else 2 ** attempt)
                continue
            if response.status_code == 408 and mutating:
                raise AmbiguousResult('คำขอสร้างรายการ timeout ต้องตรวจสอบก่อนทำต่อ')
            if response.status_code >= 500:
                if mutating:
                    raise AmbiguousResult('Google ตอบข้อผิดพลาด ผลการสร้างอาจสำเร็จ หยุดเพื่อป้องกันซ้ำ')
                if retry and attempt < 4:
                    self.sleep(2 ** attempt)
                    continue
            if not response.ok:
                raise SafeAPIError(f'Google HTTP {response.status_code} (ไม่บันทึก response เพื่อป้องกันข้อมูลลับ)')
            return response
        raise SafeAPIError('เกินจำนวน retry')

    def verify_account(self):
        response = self.request('GET', 'https://openidconnect.googleapis.com/v1/userinfo', retry=True)
        try:
            info = response.json()
        except ValueError:
            raise SafeAPIError('อ่านข้อมูลบัญชีไม่ได้') from None
        email = info.get('email', '').lower()
        if email != EXPECTED_ACCOUNT or info.get('email_verified') is not True:
            raise SafeAPIError('บัญชีไม่ตรงกับ photos@ccdthailand.org หรืออีเมลยังไม่ยืนยัน')
        self.account = email
        return email

    def _require_account(self):
        if self.account != EXPECTED_ACCOUNT:
            raise SafeAPIError('ยังไม่ได้ตรวจสอบบัญชีปลายทาง')

    def create_album(self, title):
        self._require_account()
        response = self.request('POST', BASE + '/albums', mutating=True, json={'album': {'title': title}})
        try:
            album_id = response.json()['id']
            if not isinstance(album_id, str) or not album_id:
                raise ValueError('invalid album ID')
            return album_id
        except (ValueError, KeyError):
            raise AmbiguousResult('ไม่พบ album ID ในผลตอบกลับ') from None

    def upload(self, path: Path):
        self._require_account()
        # Byte upload does not create a media item; retry opens a fresh stream.
        for attempt in range(5):
            try:
                with path.open('rb') as stream:
                    response = self.request('POST', BASE + '/uploads', data=stream,
                        headers={'Content-Type': 'application/octet-stream', 'X-Goog-Upload-Protocol': 'raw',
                                 'X-Goog-Upload-File-Name': path.name})
                token = response.text.strip()
                if not token:
                    raise SafeAPIError('ไม่ได้รับ upload token')
                return token
            except SafeAPIError:
                if attempt == 4:
                    raise
                self.sleep(2 ** attempt)

    def create_media(self, upload_token, album_id, filename):
        self._require_account()
        response = self.request('POST', BASE + '/mediaItems:batchCreate', mutating=True,
            json={'albumId': album_id, 'newMediaItems': [
                {'simpleMediaItem': {'uploadToken': upload_token, 'fileName': filename}}]})
        try:
            result = response.json()['newMediaItemResults'][0]
            code = result.get('status', {}).get('code', 0)
            if not isinstance(code, int):
                raise ValueError('invalid status')
            if code:
                raise SafeAPIError(f'สร้าง media item ไม่สำเร็จ รหัส {code}')
            return result['mediaItem']['id']
        except (ValueError, KeyError, IndexError):
            raise AmbiguousResult('ไม่สามารถยืนยันผลสร้าง media item') from None
