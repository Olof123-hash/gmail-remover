import time

from googleapiclient.errors import HttpError

from SA import TOKEN_PATH, MissingCredentialsError, ServiceAuth

BATCH_SIZE = 1000        # messages.batchModify accepts at most 1000 ids per call
MAX_ATTEMPTS = 5
RETRY_BASE_DELAY = 1.0
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def escape_gmail_term(term):
    """
    Turn a user supplied term into a literal Gmail query term.

    Wrapping the value in quotes stops Gmail from treating operators such as
    OR, -, {} or () inside it as query syntax, so a crafted sender can never
    widen the query beyond the address that was actually typed.
    """
    escaped = term.strip().replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_query(senders):
    """Build a query that matches only the given senders."""
    terms = [escape_gmail_term(sender) for sender in senders if sender and sender.strip()]

    if not terms:
        # An empty query matches every message in the mailbox, so refuse it.
        raise ValueError("At least one sender is required")

    return " OR ".join(f"from:{term}" for term in terms)


def _execute_with_retry(make_request, description):
    """Execute a request, retrying on rate limits and transient server errors."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return make_request().execute()
        except HttpError as err:
            status = getattr(err.resp, "status", None)
            if status not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                raise
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            print(f"{description} failed with {status}, retrying in {delay:.0f}s...")
            time.sleep(delay)

    return None


def collect_message_ids(service, query, amount=None):
    """Return the ids of the matching messages, at most `amount` of them."""
    if amount is not None and amount <= 0:
        return []

    ids = []
    page_size = 500 if amount is None else max(1, min(500, amount))
    page_token = None

    while True:
        def make_request(token=page_token):
            return service.users().messages().list(
                userId="me", q=query, maxResults=page_size, pageToken=token
            )

        response = _execute_with_retry(make_request, "Listing messages")

        for message in response.get("messages", []):
            ids.append(message["id"])
            if amount is not None and len(ids) >= amount:
                return ids

        page_token = response.get("nextPageToken")
        if not page_token:
            return ids


def _trash_batch(service, ids):
    """Move a batch of messages to the trash, exactly like the Gmail UI does."""
    body = {
        "ids": ids,
        "addLabelIds": ["TRASH"],
        "removeLabelIds": ["INBOX", "UNREAD"],
    }

    _execute_with_retry(
        lambda: service.users().messages().batchModify(userId="me", body=body),
        "Trashing messages",
    )


def delete_mail(senders, amount=None):
    """
    Move every message from the given senders to the trash.

    amount: the maximum number of messages to trash, or None to trash all of
            the matching messages.
    """
    if amount is not None and (not isinstance(amount, int) or amount < 0):
        raise ValueError("amount must be a non-negative integer")

    query = build_query(senders)

    try:
        service = ServiceAuth().check_credentials()
    except MissingCredentialsError as err:
        print(err)
        return 0
    except Exception as err:
        print(f"Could not authenticate with Gmail: {err}")
        print(f"The token is stored at {TOKEN_PATH}")
        return 0

    ids = collect_message_ids(service, query, amount)

    if not ids:
        print("Could not find any mail from this sender")
        return 0

    deleted = 0
    try:
        for start in range(0, len(ids), BATCH_SIZE):
            chunk = ids[start:start + BATCH_SIZE]
            _trash_batch(service, chunk)
            deleted += len(chunk)
    except HttpError as err:
        print(f"Trashing failed after {deleted} of {len(ids)} messages: {err}")
        print("Run the command again to continue with the remaining messages.")
        return deleted
    except Exception as err:
        print(f"You have the following error {err}, {type(err)=} : Please try again")
        return deleted

    print(f"Successfully deleted {deleted} emails from {', '.join(senders)}")
    return deleted
