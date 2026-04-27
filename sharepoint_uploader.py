"""
sharepoint_uploader.py
Uploads an Excel file to a SharePoint document library using the
Microsoft Graph API with app-only (client_credentials) authentication.

Required Azure AD app permissions:
  - Sites.ReadWrite.All   (Application)
"""
import io
import requests


class SharePointUploader:
    GRAPH = "https://graph.microsoft.com/v1.0"
    LOGIN = "https://login.microsoftonline.com"

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        site_url: str,
        folder_path: str = "Shared Documents/Events",
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.site_url = site_url.rstrip("/")
        self.folder_path = folder_path.strip("/")

    # ── Auth ───────────────────────────────────────────────────────────────────
    def _token(self) -> str:
        resp = requests.post(
            f"{self.LOGIN}/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # ── Site / Drive discovery ─────────────────────────────────────────────────
    def _site_id(self, token: str) -> str:
        # e.g. https://company.sharepoint.com/sites/MySite
        without_scheme = self.site_url.replace("https://", "")
        host, *path_parts = without_scheme.split("/")
        rel_path = "/".join(path_parts)
        resp = requests.get(
            f"{self.GRAPH}/sites/{host}:/{rel_path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _drive_id(self, token: str, site_id: str) -> str:
        resp = requests.get(
            f"{self.GRAPH}/sites/{site_id}/drives",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        drives = resp.json()["value"]
        # Prefer the Documents / Shared Documents library
        for d in drives:
            if d["name"] in ("Documents", "Shared Documents"):
                return d["id"]
        return drives[0]["id"]

    # ── Upload ─────────────────────────────────────────────────────────────────
    def upload(self, file_buf: io.BytesIO, filename: str) -> str:
        """
        Upload file_buf as filename into folder_path.
        Returns the SharePoint web URL of the uploaded file.
        """
        token = self._token()
        site_id = self._site_id(token)
        drive_id = self._drive_id(token, site_id)

        # URL-encode spaces
        dest = f"{self.folder_path}/{filename}".replace(" ", "%20")
        upload_url = f"{self.GRAPH}/drives/{drive_id}/root:/{dest}:/content"

        file_buf.seek(0)
        resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": (
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                ),
            },
            data=file_buf.read(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("webUrl", "")
