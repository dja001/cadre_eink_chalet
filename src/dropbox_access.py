#
# The procedure I followed to get the three keys necessary:
#     
# Step-by-step: exactly what to do
# Step 1 — Get the App key and App secret (2 minutes)
# 
# Go to: Dropbox App Console
# 
# Click your app
# 
# Go to the Settings tab
# 
# You will see:
# 
# App key → copy this
# 
# App secret → click “Show”, then copy
# 
# These two values already exist — you just haven’t needed them yet.
# 
# Step 2 — Confirm the app is configured correctly
# 
# Still in Settings:
# 
# OAuth 2
# 
# Access token expiration → enabled (default)
# 
# Redirect URIs
# 
# Add this (temporary, just for setup):
# 
# http://localhost
# 
# 
# Save changes.
# 
# Why this matters: Dropbox won’t issue a refresh token without a redirect URI.
# 
# Step 3 — Generate an authorization code (one-time)
# 
# Open a browser and visit this URL, replacing APP_KEY:
# 
# https://www.dropbox.com/oauth2/authorize
# ?client_id=APP_KEY
# &response_type=code
# &token_access_type=offline
# &redirect_uri=http://localhost
# 
# 
# What happens:
# 
# Dropbox asks you to approve the app
# 
# You’re redirected to:
# 
# http://localhost/?code=ABCDEFG...
# 
# 
# Copy the code=... value
# That’s the authorization code (short-lived, one-time use).
# 
# Step 4 — Exchange the code for a refresh token
# 
# Run this one-time Python script (you can delete it afterward):
# 
# import requests
# 
# APP_KEY = "PASTE_APP_KEY"
# APP_SECRET = "PASTE_APP_SECRET"
# AUTH_CODE = "PASTE_AUTH_CODE"
# 
# resp = requests.post(
#     "https://api.dropboxapi.com/oauth2/token",
#     data={
#         "code": AUTH_CODE,
#         "grant_type": "authorization_code",
#         "client_id": APP_KEY,
#         "client_secret": APP_SECRET,
#         "redirect_uri": "http://localhost",
#     },
# )
# 
# resp.raise_for_status()
# print(resp.json())
# 
# 
# You’ll see output like:
# 
# {
#   "access_token": "...",
#   "expires_in": 14400,
#   "refresh_token": "sl.ABCDEF...",
#   "token_type": "bearer"
# }
# 
# 
# Copy only the refresh_token
# Ignore the access token — it’s disposable.
# 
# Step 5 — Create / update your .env file
# 
# Yes — they all go in the same .env file.
# 
# ~/.config/Dropbox/.env:
# 
# DROPBOX_APP_KEY=your_app_key
# DROPBOX_APP_SECRET=your_app_secret
# DROPBOX_REFRESH_TOKEN=your_refresh_token
# 
# 
# Permissions (important):
# 
# chmod 600 ~/.config/Dropbox/.env
# 
# 
# At this point you are fully set up.
# 
# Step 6 — Use the client (forever, unchanged)
# 
# From now on, your script only does this:
# 
# dbx = get_dropbox_client()
# metadata, res = dbx.files_download("/listes/fermeture_du_chalet.txt")
# 




import os
import datetime
import dropbox
from dotenv import load_dotenv
from dropbox.exceptions import AuthError
from dropbox.files import FileMetadata, FolderMetadata

def get_dropbox_client(validate=True):
    """
    Create and optionally validate a Dropbox client.

    validate=True:
        Performs a lightweight API call to ensure credentials are valid.
    """

    env_path = os.path.expanduser("~/.config/Dropbox/.env")
    load_dotenv(env_path)

    app_key = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")

    if not all([app_key, app_secret, refresh_token]):
        raise ValueError(
            "Missing Dropbox credentials in ~/.config/Dropbox/.env"
        )

    dbx = dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
    )

    if validate:
        try:
            dbx.users_get_current_account()
        except AuthError as e:
            raise RuntimeError(
                "Dropbox authentication failed. "
                "Check refresh token, app key/secret, or app permissions."
            ) from e

    return dbx


def ensure_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def sync_dropbox_dir(dropbox_dir, local_dir):
    """
    Sync a Dropbox directory to a local directory (rsync -au style).

    Parameters
    ----------
    dropbox_dir : str
        Path in Dropbox (e.g. "/listes")
    local_dir : str
        Local directory path
    """

    os.makedirs(local_dir, exist_ok=True)

    dbx = get_dropbox_client(validate=True)

    def _sync_folder(dbx_path, local_path):
        result = dbx.files_list_folder(dbx_path)

        while True:
            for entry in result.entries:
                if isinstance(entry, FolderMetadata):
                    # Recurse into subdirectory
                    sub_local = os.path.join(local_path, entry.name)
                    os.makedirs(sub_local, exist_ok=True)
                    _sync_folder(entry.path_lower, sub_local)

                elif isinstance(entry, FileMetadata):
                    local_file = os.path.join(local_path, entry.name)

                    download = False
                    if not os.path.exists(local_file):
                        download = True
                    else:
                        # Compare modification times
                        entry_mtime = ensure_utc(entry.client_modified)
                        local_mtime = datetime.datetime.fromtimestamp(
                            os.path.getmtime(local_file),
                            tz=datetime.timezone.utc,
                        )
                        if entry_mtime > local_mtime:
                            download = True

                    if download:
                        print(f"Downloading {entry.path_lower} → {local_file}")
                        _, res = dbx.files_download(entry.path_lower)
                        with open(local_file, "wb") as f:
                            f.write(res.content)

                        # Preserve modification time
                        mtime = entry.client_modified.timestamp()
                        os.utime(local_file, (mtime, mtime))

            if not result.has_more:
                break
            result = dbx.files_list_folder_continue(result.cursor)

    _sync_folder(dropbox_dir, local_dir)



def get_todo_list():

    
    dbx = get_dropbox_client(validate=True)
    
    metadata, res = dbx.files_download("/listes/fermeture_du_chalet.txt")
    #print(metadata)
    #print(res)
    #print(res.content)

    text = res.content.decode("utf-8")
    lines = text.splitlines()

    return lines
    



if __name__ == '__main__' :

    get_todo_list()
