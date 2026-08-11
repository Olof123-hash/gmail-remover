import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pathlib import Path

AUTH_DIR = Path(__file__).parent / "authentication"
TOKEN_PATH = AUTH_DIR / "token.json"
CREDENTIALS_PATH = AUTH_DIR / "credentials.json"

class ServiceAuth:

    # If modifying these scopes, delete the file token.json.
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://mail.google.com/"
    ]

    def check_credentials(self):
        creds = None

        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, self.SCOPES)
                creds = flow.run_local_server(port=0)

            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)
        return service



