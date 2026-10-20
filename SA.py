import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

AUTH_DIR = Path(__file__).resolve().parent / "authentication"
TOKEN_PATH = AUTH_DIR / "token.json"
CREDENTIALS_PATH = AUTH_DIR / "credentials.json"

USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _current_account():
    """Return the current user as DOMAIN\\user where that is known."""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    domain = os.environ.get("USERDOMAIN")

    if domain and user:
        return f"{domain}\\{user}"
    return user


def _restrict_to_current_user(path, directory=False):
    """
    Make `path` accessible only to the user running this program.

    On POSIX that is a chmod to 0600/0700. On Windows, chmod cannot express
    this, so the file ACL is rewritten with icacls instead. Failures are
    reported but never stop the program from running.
    """
    try:
        if os.name == "nt":
            account = _current_account()
            if not account:
                return
            grant = "(OI)(CI)(F)" if directory else "(F)"
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:{grant}"],
                check=True,
                capture_output=True,
            )
        else:
            os.chmod(path, 0o700 if directory else 0o600)
    except (OSError, subprocess.SubprocessError) as err:
        print(f"Warning: could not restrict permissions on {path}: {err}", file=sys.stderr)


class ServiceAuth:
    """
    OAuth wrapper for the Gmail API.

    The scopes below are deliberately narrow:
      * gmail.settings.basic -> create / list / delete filters (blocking)
      * gmail.modify        -> move messages to the trash
      * userinfo.email      -> read our own address (to stop self-blocking)

    "https://mail.google.com/" would hand out full read/write/send access to
    the entire mailbox, which this project never needs.
    """

    # If modifying these scopes, delete the file token.json.
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/userinfo.email",
    ]

    def get_credentials(self):
        """Return valid credentials, running the OAuth flow when needed."""
        creds = None

        if TOKEN_PATH.exists():
            if self._grant_is_current():
                try:
                    creds = Credentials.from_authorized_user_file(TOKEN_PATH, self.SCOPES)
                except ValueError:
                    # Corrupt or unreadable token file, fall through to a
                    # fresh consent.
                    creds = None
            else:
                # The stored token was granted for a different set of scopes
                # (usually a wider one). It can no longer be used, so drop it
                # and ask the user to consent again with the current scopes.
                print("Stored token has outdated scopes, requesting new consent...")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, self.SCOPES)
                creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

            self.save_token(creds)

        return creds

    def _grant_is_current(self):
        """
        Check that the stored token was granted exactly the scopes we want.

        google-auth happily loads a token regardless of the scopes it was
        granted, so without this check an old, wider grant (for example
        "https://mail.google.com/") would keep being used.
        """
        granted = self._stored_grant()
        if granted is None:
            # Nothing usable to compare against, let google-auth decide.
            return True

        wanted = {scope.rstrip("/") for scope in self.SCOPES}
        return granted == wanted

    @staticmethod
    def _stored_grant():
        """Return the scopes the stored token was granted, or None if unknown."""
        try:
            with TOKEN_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        scopes = data.get("scopes")
        if isinstance(scopes, str):
            scopes = scopes.split()
        if not isinstance(scopes, list):
            return None

        return {scope.rstrip("/") for scope in scopes if isinstance(scope, str)}

    @staticmethod
    def save_token(creds):
        """
        Write the token atomically and restrict it to the current user.

        The token grants access to the mailbox, so it must never end up
        readable by anyone else, and a crash halfway through must not leave a
        half-written file behind.
        """
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        _restrict_to_current_user(AUTH_DIR, directory=True)

        fd, tmp_path = tempfile.mkstemp(dir=str(AUTH_DIR), prefix=".token-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
            _restrict_to_current_user(tmp_path)
            os.replace(tmp_path, TOKEN_PATH)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def check_credentials(self):
        """Return an authorised Gmail API client."""
        return build("gmail", "v1", credentials=self.get_credentials())

    def get_user_email(self):
        """Best effort lookup of the signed-in account's own address."""
        try:
            creds = self.get_credentials()
            session = AuthorizedSession(creds)
            response = session.get(USERINFO_URL, timeout=10)
            response.raise_for_status()
            return response.json().get("email")
        except Exception:
            return None
