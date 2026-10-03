"""One-time local setup. Saves credentials locally without printing tokens."""
import argparse
import getpass
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode
import requests
from auth import hash_password
from workbook_store import DEFAULT_LINK


def quoted(value): return json.dumps(value,ensure_ascii=False)


def new_user():
    username=input('Dashboard username (lowercase, e.g. nathalie): ').strip().lower()
    if not re.fullmatch('[a-z0-9_-]+',username): raise ValueError('Use lowercase letters, numbers, underscores or hyphens.')
    name=input('Display name: ').strip() or username
    role=input('Role (editor/viewer) [editor]: ').strip().lower() or 'editor'
    if role not in ['editor','viewer']: raise ValueError('Role must be editor or viewer.')
    password=getpass.getpass('New dashboard password (at least 14 characters): ')
    if len(password)<14: raise ValueError('Use at least 14 characters.')
    if password!=getpass.getpass('Repeat dashboard password: '): raise ValueError('Passwords do not match.')
    return '\n'.join([f'[users.{username}]',f'name = {quoted(name)}',f'role = {quoted(role)}',f'password_hash = {quoted(hash_password(password))}'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--user-only',action='store_true',help='Print only a new user configuration with a password hash; no Dropbox setup.')
    args=parser.parse_args()
    if args.user_only:
        print('\nAdd this section to Streamlit Secrets:\n'+new_user());return
    target=Path('.streamlit/secrets.toml')
    if target.exists(): raise ValueError('A local secrets.toml already exists. Keep a copy and move it aside before full setup, or use --user-only.')
    app_key=input('Dropbox app key: ').strip()
    app_secret=getpass.getpass('Dropbox app secret: ').strip()
    if not app_key or not app_secret: raise ValueError('App key and secret are required.')
    scopes='files.metadata.read files.content.read files.content.write sharing.read'
    params={'client_id':app_key,'response_type':'code','token_access_type':'offline','scope':scopes}
    print('\nOpen this URL in your browser, authorize using the Dropbox account with edit access to the workbook, then copy the authorization code:\n')
    print('https://www.dropbox.com/oauth2/authorize?'+urlencode(params))
    code=getpass.getpass('\nAuthorization code: ').strip()
    r=requests.post('https://api.dropboxapi.com/oauth2/token',auth=(app_key,app_secret),data={'grant_type':'authorization_code','code':code},timeout=(10,45))
    if r.status_code!=200 or 'refresh_token' not in r.json(): raise ValueError('Dropbox authorization failed. Check selected scopes and restart with a new authorization code.')
    token=r.json()['refresh_token']
    user=new_user()
    lines=['TIMEZONE = "America/Los_Angeles"','','[dropbox]',f'app_key = {quoted(app_key)}',f'app_secret = {quoted(app_secret)}',f'refresh_token = {quoted(token)}',f'shared_link = {quoted(DEFAULT_LINK)}','',user,'']
    target.parent.mkdir(exist_ok=True)
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:f.write('\n'.join(lines))
    print('\nCreated .streamlit/secrets.toml on this computer. Copy its contents into Streamlit app Settings > Secrets. Never upload this file to GitHub or send its contents in chat.')

if __name__=='__main__':
    try: main()
    except (ValueError,requests.RequestException) as exc:
        # Requests exceptions can include network details; credentials are never printed.
        print(str(exc) if isinstance(exc,ValueError) else 'Network request failed. Check your connection and retry setup.')
        raise SystemExit(1)
