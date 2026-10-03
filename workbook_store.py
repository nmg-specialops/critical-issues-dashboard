"""Dropbox transport. All writes use compare-and-swap against the loaded revision."""
import hashlib
import json
import requests

DEFAULT_LINK = 'https://www.dropbox.com/scl/fi/pajbtoz4v0jcfdoo2u79j/SpOps_ProjectCriticalPoints-Priorities.xlsx?rlkey=vnih493vt4grsudt4gf2bo546&dl=0'
MAX_BYTES = 20 * 1024 * 1024

class StoreError(Exception): pass
class ConflictError(StoreError): pass
class UnknownSaveError(StoreError): pass


def content_hash(data):
    hashes = b''.join(hashlib.sha256(data[i:i+4*1024*1024]).digest() for i in range(0,len(data),4*1024*1024))
    return hashlib.sha256(hashes).hexdigest()


class DropboxStore:
    def __init__(self, config, http=None):
        self.config = config
        self.http = http or requests.Session()
        self.token = None

    def _token(self):
        if self.token: return self.token
        try:
            r = self.http.post('https://api.dropboxapi.com/oauth2/token',
                auth=(self.config['app_key'],self.config['app_secret']),
                data={'grant_type':'refresh_token','refresh_token':self.config['refresh_token']}, timeout=(10,30))
            if r.status_code != 200: raise StoreError('Dropbox authorization failed. Check the app key, secret, refresh token and granted permissions.')
            self.token = r.json()['access_token']
            return self.token
        except (requests.RequestException, KeyError) as exc:
            raise StoreError('Could not authenticate with Dropbox. Check configuration and connection.') from exc

    def _headers(self, arg=None):
        headers = {'Authorization':'Bearer '+self._token()}
        if arg is not None: headers['Dropbox-API-Arg']=json.dumps(arg,ensure_ascii=True)
        root = self.config.get('root_namespace_id')
        if root: headers['Dropbox-API-Path-Root']=json.dumps({'.tag':'root','root':str(root)})
        return headers

    def metadata(self, file_id):
        try:
            r=self.http.post('https://api.dropboxapi.com/2/files/get_metadata',headers=self._headers(),json={'path':file_id},timeout=(10,30))
            if r.status_code != 200: raise StoreError('Cannot read workbook metadata. Check access to the original file.')
            return r.json()
        except requests.RequestException as exc: raise StoreError('Could not check the current workbook version.') from exc

    def load(self):
        try:
            target = self.config.get('file_id','') or self.config.get('file_path','')
            if not target:
                r = self.http.post('https://api.dropboxapi.com/2/sharing/get_shared_link_metadata',headers=self._headers(),json={'url':self.config.get('shared_link',DEFAULT_LINK)},timeout=(10,30))
                if r.status_code != 200: raise StoreError('Could not resolve the shared workbook. Configure its exact Dropbox file_path or file_id in Secrets.')
                meta=r.json()
                target=meta.get('id') or meta.get('path_lower')
                if not target: raise StoreError('This account cannot resolve the file for editing. Use an account with edit access and configure file_path.')
            with self.http.post('https://content.dropboxapi.com/2/files/download',headers=self._headers({'path':target}),timeout=(10,45),stream=True) as r:
                if r.status_code != 200: raise StoreError('Could not download the workbook through the authorized account. Check the file location and permissions.')
                meta=json.loads(r.headers['Dropbox-API-Result'])
                chunks=[]; size=0
                for chunk in r.iter_content(65536):
                    size+=len(chunk)
                    if size>MAX_BYTES: raise StoreError('Workbook exceeds 20 MB.')
                    chunks.append(chunk)
                data=b''.join(chunks)
            if not data.startswith(b'PK'): raise StoreError('The Dropbox file is not an .xlsx workbook.')
            if meta.get('name') != 'SpOps_ProjectCriticalPoints-Priorities.xlsx':
                raise StoreError('Configured file has an unexpected name. Point to SpOps_ProjectCriticalPoints-Priorities.xlsx.')
            return {'bytes':data,'rev':meta['rev'],'file_id':meta['id'],'name':meta['name'],'modified':meta.get('server_modified','')}
        except (requests.RequestException,KeyError,ValueError) as exc:
            raise StoreError('Could not load the workbook from Dropbox. Check access and connection.') from exc

    def save(self, snapshot, data):
        if len(data)>MAX_BYTES: raise StoreError('Updated workbook exceeds 20 MB.')
        current=self.metadata(snapshot['file_id'])
        if current['rev'] != snapshot['rev']:
            raise ConflictError('The workbook changed in Dropbox after you loaded it. Your changes were not written. Download your draft, reload the workbook, and reapply the changes.')
        args={'path':snapshot['file_id'],'mode':{'.tag':'update','update':snapshot['rev']},'autorename':False,'strict_conflict':True,'mute':False,'content_hash':content_hash(data)}
        headers=self._headers(args); headers['Content-Type']='application/octet-stream'
        try:
            r=self.http.post('https://content.dropboxapi.com/2/files/upload',headers=headers,data=data,timeout=(10,60))
        except requests.RequestException as exc:
            return self._reconcile(snapshot,data,exc)
        if r.status_code == 409:
            raise ConflictError('Dropbox rejected the save because of a conflict, file lock, or write restriction. Nothing was overwritten by this request. Download your draft and reload before retrying.')
        if r.status_code>=500: return self._reconcile(snapshot,data,None)
        if r.status_code != 200:
            raise StoreError('Dropbox did not accept the save. Check edit permission, granted files.content.write scope, and available storage. Your draft remains available.')
        meta=r.json()
        return dict(snapshot,bytes=data,rev=meta['rev'],modified=meta.get('server_modified',''))

    def _reconcile(self,snapshot,data,cause):
        # A timed-out upload may have succeeded. Never retry a write blindly.
        try:
            meta=self.metadata(snapshot['file_id'])
            if meta.get('content_hash')==content_hash(data):
                return dict(snapshot,bytes=data,rev=meta['rev'],modified=meta.get('server_modified',''))
        except StoreError: pass
        raise UnknownSaveError('Save outcome is uncertain. Do not click Save again. Download your draft, reload Dropbox, and check History before making further edits.') from cause
