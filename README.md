# gmail-remover

A small command line tool for trashing Gmail messages from senders you do not
want to hear from, and for blocking senders so their mail never reaches your
inbox again.

> This project is for fun and is not meant to be taken seriously. Security
> risks are at your own responsibility.

## What it does

- **Delete emails** - move every message from one or more senders to the
  trash, optionally limited to a specific number of messages.
- **Block accounts** - create a Gmail filter that trashes everything from a
  sender automatically, and remove those filters again.

## Requirements

- Python 3.8 or newer
- A Google account
- Your own Google Cloud OAuth client (see below)

## Setup

### 1. Install the dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your own OAuth client

This project talks to Gmail through **your** Google Cloud project, so the
client credentials cannot be shipped with the code. Create your own:

1. Open <https://console.cloud.google.com/apis/credentials>
2. Create a project (or pick an existing one)
3. Enable the **Gmail API** for that project
4. Create an **OAuth client ID**
   - Application type: **Desktop app**
   - Name: anything you like
5. Click **Download JSON** and save the file as:

   ```
   authentication/credentials.json
   ```

   The `authentication/` folder is created for you if it does not exist yet.

### 3. Run it

```bash
python main.py
```

The first run opens a browser and asks you to consent. The app only asks for:

| Permission | Why |
|---|---|
| `gmail.settings.basic` | create, list and delete the filters used for blocking |
| `gmail.modify` | move messages to the trash |
| `userinfo.email` | read your own address, so you cannot block yourself by accident |

After you consent, the token is stored **outside the project folder** (in
`%LOCALAPPDATA%\gmail-remover\` on Windows) and is restricted to your own user
account. It is kept out of the project on purpose, so that a project living
in a cloud synced folder does not end up with your mailbox token in somebody
else's cloud. You will not be asked again until the grant is revoked or the
scopes change.

> If your consent screen is in the **Testing** publishing status, Google only
> lets you (and any test users you add) grant access. That is fine for
> personal use.

## Usage

```
$ python main.py

[?] What would you like to do?
 > Delete Emails
   Block Accounts
```

### Delete emails

Give one or more sender addresses, separated by commas. The sender is matched
as a literal term, so it can never widen the search beyond the address you
typed.

### Block accounts

Creates a Gmail filter with the action *move to trash*, and records the
address in `blocked.json`. The same list is used to unblock accounts again.

### Other commands

| Command | What it does |
|---|---|
| `python main.py --status` | show where the setup lives, which account is connected and whether the grant still works |
| `python main.py --reauth` | throw the stored grant away and consent again |
| `python main.py --help` | list the commands |

## Keeping your setup

Nothing is lost when you shut the computer down. The pieces are:

| Piece | Where | Survives a reboot |
|---|---|---|
| OAuth client | `authentication/credentials.json` | yes, and it syncs with the project folder |
| Token | `%LOCALAPPDATA%\gmail-remover\token.json` | yes, it is a plain file on disk |
| Blocked list | `blocked.json` | yes, in the project folder |

The token is deliberately **not** in the project folder, so that a project in
a cloud synced folder does not upload your mailbox token to the cloud. Set
`GMAIL_REMOVER_TOKEN_DIR` to keep it somewhere else.

> **If the grant stops working**, run `python main.py --reauth` and approve
> the request again. That is also the fix if you ever publish the app and
> Google decides the grant needs renewing.

## Files

| File | Purpose |
|---|---|
| `main.py` | command line interface |
| `SA.py` | OAuth scopes, token storage and the Gmail client |
| `functionality/deletemails.py` | searching for and trashing messages |
| `functionality/block.py` | creating, listing and removing filters |
| `blocked.json` | your local list of blocked addresses (created on first use) |
| `authentication/credentials.json` | your OAuth client, not in version control |
| `%LOCALAPPDATA%\gmail-remover\token.json` | your token, kept out of the project folder |

## Security notes

- The token file is written atomically and is only readable by the user
  running the program.
- The token is stored outside the project folder so that a cloud synced
  project does not sync your mailbox token. Set `GMAIL_REMOVER_TOKEN_DIR` to
  put it somewhere else.
- If you change the scopes in `SA.py`, run `python main.py --reauth` to
  consent again.
- Revoke the access at
  <https://myaccount.google.com/connections> if you ever want to cut it off.
- A refresh token also stops working if the OAuth consent screen is left in
  the **Testing** publishing status, because Google expires those after
  seven days. Switching the consent screen to **In production** avoids it.
