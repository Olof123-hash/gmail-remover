import contextlib
import json
import os
import tempfile
from pathlib import Path

from email_validator import validate_email, EmailNotValidError
from googleapiclient.errors import HttpError

from SA import MissingCredentialsError, ServiceAuth, describe_api_error

BLOCKED_PATH = Path(__file__).resolve().parent.parent / "blocked.json"


def is_valid_email(email):
    """Return True when `email` is a syntactically valid address."""
    if not isinstance(email, str):
        return False

    try:
        validate_email(email.strip(), check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def _read_store():
    """Load the blocked address store, tolerating a missing or damaged file."""
    if not BLOCKED_PATH.exists():
        return {"blockedAddresses": []}

    try:
        with BLOCKED_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"Warning: {BLOCKED_PATH.name} could not be read, starting a new list.")
        return {"blockedAddresses": []}

    if not isinstance(data, dict):
        return {"blockedAddresses": []}

    entries = data.get("blockedAddresses")
    if not isinstance(entries, list):
        entries = []

    data["blockedAddresses"] = [
        entry for entry in entries if isinstance(entry, dict) and entry.get("email")
    ]
    return data


def _write_store(data):
    """Write the store atomically so a crash cannot truncate it."""
    BLOCKED_PATH.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(BLOCKED_PATH.parent), prefix=".blocked-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, BLOCKED_PATH)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def show_blocked():
    """Return the list of currently blocked addresses."""
    data = _read_store()
    return [entry["email"] for entry in data["blockedAddresses"]]


def write_data(email, filter_id=None):
    """Record a blocked address together with the Gmail filter backing it."""
    data = _read_store()
    wanted = email.strip().lower()

    for entry in data["blockedAddresses"]:
        if entry["email"].strip().lower() == wanted:
            if filter_id:
                entry["filterId"] = filter_id
            break
    else:
        entry = {"email": email}
        if filter_id:
            entry["filterId"] = filter_id
        data["blockedAddresses"].append(entry)

    _write_store(data)


def find_filters(service, wanted):
    """
    Return {address: [filter id, ...]} for the given addresses.

    settings.filters.list returns every filter at once, it has no pageToken
    parameter. The response uses the key "filter" (singular), not "filters".
    """
    response = service.users().settings().filters().list(userId="me").execute()

    entries = response.get("filter")
    if entries is None:
        entries = response.get("filters", [])

    found = {}
    for entry in entries:
        source = (entry.get("criteria", {}).get("from") or "").strip().lower()
        if source in wanted:
            # There can be several filters for the same address, for example
            # after blocking the same sender twice.
            found.setdefault(source, []).append(entry.get("id"))
    return found


def block_user(email):
    """Create a Gmail filter that trashes every message from `email`."""
    email = (email or "").strip()

    if not is_valid_email(email):
        print("Not a valid email address")
        return None

    auth = ServiceAuth()

    try:
        auth.check_credentials()
    except MissingCredentialsError as err:
        print(err)
        return None
    except Exception as err:
        print(f"Could not authenticate with Gmail: {err}")
        return None

    own_address = auth.get_user_email()
    if own_address and email.lower() == own_address.lower():
        print(f"{email} is your own address - blocking it would trash all of your own mail.")
        return None

    # Do not pile up duplicate filters for an address that is already blocked.
    try:
        existing = auth.run(lambda service: find_filters(service, {email.lower()}))
    except Exception:
        existing = {}

    already = existing.get(email.lower())
    if already:
        print(f"{email} is already blocked.")
        return already[0]

    filter_content = {
        "criteria": {
            "from": email
        },
        "action": {
            'addLabelIds': ['TRASH'],
            'removeLabelIds': ['INBOX', 'UNREAD'],
        },
    }

    try:
        created = auth.run(
            lambda service: service.users().settings().filters()
            .create(userId="me", body=filter_content).execute()
        )
    except HttpError as error:
        print(f"An error occurred: {describe_api_error(error)}")
        return None
    except Exception as err:
        print(f"You have the following error {err}, {type(err)=} : Please try again")
        return None

    filter_id = created.get("id")

    try:
        write_data(email, filter_id)
    except OSError as err:
        print(f"Blocked {email}, but the local list could not be updated: {err}")
        return filter_id

    print(f"Successfully blocked {email}")
    return filter_id


def unblock_user(emails=None):
    """
    Remove the Gmail filters for the given addresses and forget them locally.

    emails: the addresses to unblock, or None to unblock everything that is
            currently recorded as blocked.
    """
    auth = ServiceAuth()

    try:
        auth.check_credentials()
    except MissingCredentialsError as err:
        print(err)
        return []
    except Exception as err:
        print(f"Could not authenticate with Gmail: {err}")
        return []

    store = _read_store()
    known = [entry["email"] for entry in store["blockedAddresses"]]

    targets = [email.strip() for email in emails] if emails else list(known)
    targets = [target for target in targets if target]
    if not targets:
        print("There is nothing to unblock")
        return []

    wanted = {target.lower() for target in targets}

    # Find the filters that belong to the addresses we want to unblock.
    filter_ids = {}

    def find_filters_for_targets(service):
        return find_filters(service, wanted)

    try:
        filter_ids = auth.run(find_filters_for_targets)
    except HttpError as error:
        print(f"Could not read the Gmail filters: {error}")
        return []
    except Exception as err:
        print(f"Could not authenticate with Gmail: {err}")
        return []

    removed = []
    for address in targets:
        ids = filter_ids.get(address.lower())
        if not ids:
            continue

        failed = False
        for filter_id in ids:
            try:
                auth.run(
                    lambda service, fid=filter_id: service.users().settings().filters()
                    .delete(userId="me", id=fid).execute()
                )
            except HttpError as error:
                print(f"Could not remove the filter for {address}: {describe_api_error(error)}")
                failed = True

        if not failed:
            removed.append(address)

    removed_keys = {address.lower() for address in removed}
    store["blockedAddresses"] = [
        entry for entry in store["blockedAddresses"]
        if entry["email"].strip().lower() not in removed_keys
    ]
    _write_store(store)

    print(f"Successfully unblocked {len(removed)} account(s)")
    return removed
