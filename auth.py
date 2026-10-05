"""Small internal-app login with salted password hashes and explicit viewer/editor roles."""
import hashlib
import hmac
import secrets
import time
import streamlit as st


def hash_password(password):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify_password(password,encoded):
    try:
        algorithm,rounds,salt,expected=encoded.split('$')
        if algorithm!='pbkdf2_sha256': return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),int(rounds)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError): return False


def setting(key, default=None):
    try: return st.secrets.get(key, default)
    except FileNotFoundError: return default


def current_user():
    """Return a currently authenticated user; never stop public rendering."""
    username=st.session_state.get('signed_in_user')
    record=setting('users',{}).get(username,{}) if username else {}
    encoded=record.get('password_hash','')
    fingerprint=hashlib.sha256(encoded.encode()).hexdigest()
    if encoded and st.session_state.get('credential_fingerprint')==fingerprint:
        return {'username':username,'name':record.get('name',username),'role':record.get('role','viewer')}
    st.session_state.pop('signed_in_user',None)
    st.session_state.pop('credential_fingerprint',None)
    return None


def logout():
    # Discard editor drafts/widgets but keep the public workbook ready to browse.
    snapshot=st.session_state.get('snapshot')
    st.session_state.clear()
    if snapshot is not None: st.session_state.snapshot=snapshot


def editor_login():
    """Only called inside Edit & Save. Returns None until sign-in succeeds."""
    user=current_user()
    if user:
        st.caption(f"Signed in as {user['name']}")
        if st.button('Sign out of editing',key='editor_logout'):
            logout();st.rerun()
        return user
    st.subheader('Sign in to edit')
    st.caption('Everyone can browse the issues and actions. An editor account is needed to change the spreadsheet.')
    users=setting('users',{})
    if not users:
        st.info('Editor accounts have not been configured. Viewing remains available. Add the existing user settings to Streamlit Secrets to enable editing.')
        return None
    with st.form('editor_login',clear_on_submit=True):
        username=st.text_input('Username').strip().lower()
        password=st.text_input('Password',type='password')
        submit=st.form_submit_button('Sign in to edit')
    if submit:
        if time.time()<st.session_state.get('login_after',0):
            st.error('Please wait briefly before trying again.');return None
        record=users.get(username,{})
        if verify_password(password,record.get('password_hash','')):
            st.session_state.signed_in_user=username
            st.session_state.credential_fingerprint=hashlib.sha256(record['password_hash'].encode()).hexdigest()
            st.session_state.pop('login_after',None)
            st.rerun()
        else:
            st.session_state.login_after=time.time()+3
            st.error('Username or password was not recognized.')
    return None
