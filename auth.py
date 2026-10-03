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


def require_user():
    try: users=st.secrets.get('users',{})
    except FileNotFoundError: users={}
    if not users:
        st.info('Setup required: add user password hashes and Dropbox credentials to Streamlit Secrets. Follow README.md. No company data is loaded before login.')
        st.stop()
    user=st.session_state.get('signed_in_user')
    if user in users:
        record=users[user]
        if st.session_state.get('credential_fingerprint')==hashlib.sha256(record.get('password_hash','').encode()).hexdigest():
            return {'username':user,'name':record.get('name',user),'role':record.get('role','viewer')}
        st.session_state.clear()
    st.subheader('Sign in')
    with st.form('login'):
        username=st.text_input('Username').strip().lower()
        password=st.text_input('Password',type='password')
        submit=st.form_submit_button('Sign in')
    if submit:
        if time.time()<st.session_state.get('login_after',0):
            st.error('Please wait briefly before trying again.'); st.stop()
        record=users.get(username,{})
        if verify_password(password,record.get('password_hash','')):
            st.session_state.signed_in_user=username
            st.session_state.credential_fingerprint=hashlib.sha256(record['password_hash'].encode()).hexdigest()
            st.rerun()
        else:
            st.session_state.login_after=time.time()+3
            st.error('Username or password was not recognized.')
    st.stop()
