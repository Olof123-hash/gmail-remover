import base64
import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

AUTH_DIR = Path(__file__).resolve().parent / "authentication"
CREDENTIALS_PATH = AUTH_DIR / "credentials.json"

# Google adds the "openid" scope on its own whenever a userinfo scope is
# requested, so the granted scope set never matches the requested one
# exactly. oauthlib treats that as a fatal error, which would abort the flow
# right after the consent succeeded and lose the token. This is oauthlib's
# own switch for exactly that case.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _token_dir():
    """
    Return the directory the token is stored in.

    The token deliberately does not live in the project folder. The project
    usually sits in a cloud synced folder (OneDrive, Dropbox, ...) and a
    synced token is a token in somebody else's cloud. It also keeps the
    token out of the way of the sync client, which fights with the
    permission changes made to it.

    Set GMAIL_REMOVER_TOKEN_DIR to override the location.
    """
    override = os.environ.get("GMAIL_REMOVER_TOKEN_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")

    return Path(base) / "gmail-remover"


TOKEN_PATH = _token_dir() / "token.json"

CREDENTIALS_HELP = """Could not find {path}

This project talks to Gmail through your own Google Cloud OAuth client, so
one has to be created before the app can run:

  1. Open https://console.cloud.google.com/apis/credentials
  2. Create a project (or pick an existing one)
  3. Enable the Gmail API for that project
  4. Create an OAuth client ID -> Application type: "Desktop app"
  5. Download the JSON and save it as:

     {path}

Then run the app again and complete the consent in your browser."""


class MissingCredentialsError(FileNotFoundError):
    """Raised when the user has not supplied their own OAuth client file."""


class InvalidCredentialsError(ValueError):
    """Raised when the supplied OAuth client file cannot be used."""


def _is_auth_failure(err):
    """True when the error means the stored grant is no longer usable."""
    if isinstance(err, RefreshError):
        return True

    status = getattr(getattr(err, "resp", None), "status", None)
    return status in (401, 403)


def describe_api_error(err):
    """Pull the human readable part out of a Gmail API error."""
    try:
        body = json.loads(err.content.decode("utf-8", "replace"))
        return body.get("error", {}).get("message") or str(err)
    except Exception:
        return str(err)


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

    def __init__(self):
        # Counts how many consent flows have run, so we never ask twice for
        # the same problem.
        self.consent_count = 0

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
                print("The stored grant has outdated scopes, asking for consent again...")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    # Silent refresh. The browser is not needed here, the
                    # long lived refresh token is exchanged for a new access
                    # token over a plain request.
                    creds.refresh(Request())
                except RefreshError:
                    # The refresh token was revoked or has expired, so the
                    # only way forward is a new consent.
                    print("The stored grant is no longer valid, asking for consent again...")
                    creds = self._run_consent_flow()
            else:
                if creds is None and TOKEN_PATH.exists():
                    print("The stored grant could not be used, asking for consent again...")
                else:
                    print("No stored grant found, asking for consent...")
                creds = self._run_consent_flow()

            try:
                self.save_token(creds)
                print(f"Grant saved to {TOKEN_PATH}")
            except OSError as err:
                # Not fatal for this run, but the next one will have to ask
                # for consent again, so make the reason visible.
                print(f"Warning: could not save the grant to {TOKEN_PATH}: {err}")

        return creds

    def _run_consent_flow(self):
        """Run the interactive OAuth flow and return fresh credentials."""
        if not CREDENTIALS_PATH.exists():
            raise MissingCredentialsError(
                CREDENTIALS_HELP.format(path=CREDENTIALS_PATH)
            )

        try:
            # "utf-8-sig" reads the file whether or not it carries a byte
            # order mark. Windows editors add one by default, and the
            # stock loader would choke on it.
            with CREDENTIALS_PATH.open("r", encoding="utf-8-sig") as f:
                client_config = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as err:
            raise InvalidCredentialsError(
                f"{CREDENTIALS_PATH} could not be read as JSON ({err}).\n"
                "It has to be the JSON downloaded for a Desktop app OAuth client."
            ) from err

        if "installed" not in client_config:
            raise InvalidCredentialsError(
                f"{CREDENTIALS_PATH} is not a Desktop app OAuth client.\n"
                'The file needs an "installed" section, which is what you get '
                'when the OAuth client is created with the application type '
                '"Desktop app".'
            )

        try:
            flow = InstalledAppFlow.from_client_config(client_config, self.SCOPES)
        except ValueError as err:
            raise InvalidCredentialsError(
                f"{CREDENTIALS_PATH} does not look like a usable OAuth client file ({err}).\n"
                "It has to be the JSON downloaded for a Desktop app OAuth client."
            ) from err

        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        self.consent_count += 1
        return creds
    def _grant_is_current(self):
        """
        Check that the stored token was granted exactly the scopes we want.

        google-auth happily loads a token regardless of the scopes it was
        granted, so without this check an old, wider grant (for example
        "https://mail.google.com/") would keep being used.

        The grant has to cover every scope we ask for, and it must not be
        wider than that. The one exception is "openid", which Google adds by
        itself when a userinfo scope is requested.
        """
        granted = self._stored_grant()
        if granted is None:
            # Nothing usable to compare against, let google-auth decide.
            return True

        wanted = {scope.rstrip("/") for scope in self.SCOPES}
        allowed = wanted | {"openid"}

        return wanted.issubset(granted) and granted.issubset(allowed)

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
        token_dir = TOKEN_PATH.parent
        token_dir.mkdir(parents=True, exist_ok=True)
        _restrict_to_current_user(token_dir, directory=True)

        fd, tmp_path = tempfile.mkstemp(dir=str(token_dir), prefix=".token-", suffix=".tmp")
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

    def invalidate_token(self):
        """Forget the stored grant."""
        with contextlib.suppress(OSError):
            TOKEN_PATH.unlink()

    def run(self, action):
        """
        Run an API action, asking for a new consent if the grant went stale.

        A stored access token can stop working between runs (the grant was
        revoked, the password changed, the scopes no longer line up). Rather
        than dying with a raw "invalid_grant", the stale grant is dropped and
        a fresh consent is requested, then the action is retried once.
        """
        before = self.consent_count

        try:
            return action(self.check_credentials())
        except (RefreshError, HttpError) as err:
            if not _is_auth_failure(err) or self.consent_count > before:
                # Either a genuine failure, or the grant was just renewed and
                # this is a second, unrelated problem. Do not ask again.
                raise

            print("The Gmail grant is no longer valid, asking for consent again...")
            self.invalidate_token()
            return action(self.check_credentials())
    def get_user_email(self):
        """Best effort lookup of the signed-in account's own address."""
        try:
            creds = self.get_credentials()
        except Exception:
            return None

        # The id_token that comes with the grant already carries the address,
        # so this usually needs no request at all.
        address = self._email_from_id_token(creds)
        if address:
            return address

        try:
            session = AuthorizedSession(creds)
            response = session.get(USERINFO_URL, timeout=10)
            response.raise_for_status()
            return response.json().get("email")
        except Exception:
            return None

    @staticmethod
    def _email_from_id_token(creds):
        """Pull the email claim out of the id_token, if there is one."""
        id_token = getattr(creds, "id_token", None)
        if not id_token:
            return None

        try:
            payload = id_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return claims.get("email")
        except Exception:
            return None
