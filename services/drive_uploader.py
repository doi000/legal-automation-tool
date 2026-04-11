"""Google Drive連携モジュール"""
import os
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveUploader:
    def __init__(self):
        self._dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
        if not self._dev_mode:
            creds_path = os.path.join(os.path.dirname(__file__), "..", "google_credentials.json")
            creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
            self._service = build("drive", "v3", credentials=creds)

    def upload(self, file_path: str, folder_name: str) -> str:
        """
        ファイルを指定フォルダにアップロードし共有URLを返す。
        フォルダが存在しなければ自動作成する。
        """
        if self._dev_mode:
            return f"https://drive.google.com/file/d/mock-file-id/view (DEV_MODE)"

        folder_id = self._get_or_create_folder(folder_name)
        mime_type = self._guess_mime(file_path)

        file_metadata = {
            "name": os.path.basename(file_path),
            "parents": [folder_id],
        }
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        uploaded = self._service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        ).execute()

        # 共有設定（リンクを知っている全員が閲覧可能）
        self._service.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return uploaded.get("webViewLink", "")

    def download_to_path(self, file_id: str, dest_path: str):
        """Drive上のファイルをローカルにダウンロードする"""
        if self._dev_mode:
            return
        request = self._service.files().get_media(fileId=file_id)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(request.execute())

    def _get_or_create_folder(self, folder_name: str) -> str:
        query = (
            f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        )
        results = self._service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = self._service.files().create(
            body=folder_metadata, fields="id"
        ).execute()
        return folder["id"]

    @staticmethod
    def _guess_mime(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        mapping = {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pdf": "application/pdf",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return mapping.get(ext, "application/octet-stream")

    @staticmethod
    def extract_file_id(drive_url: str) -> Optional[str]:
        """Drive URLからファイルIDを抽出する"""
        if "/d/" in drive_url:
            parts = drive_url.split("/d/")
            if len(parts) > 1:
                return parts[1].split("/")[0]
        return None
