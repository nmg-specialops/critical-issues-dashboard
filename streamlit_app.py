"""Public issues register with an optional card view and protected editing."""
import re
from datetime import datetime
from html import escape
from hashlib import sha256
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
from data_model import KEY,SCHEMA,calculate,workbook_bytes
from workbook_model import read,PARTNERS
from workbook_store import DropboxStore,StoreError,DEFAULT_LINK,MAX_BYTES


APP_VERSION = "Cards-first · 2026-10-05.2"

# Internal login helpers with viewer/editor roles.
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


# Forms for editing and saving partner issues.
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from workbook_model import (PARTNERS,META,DETAIL_COLS,EXTRA_COLS,NATURAL,ISSUE_STATUSES,SEVERITIES,ACTION_STATUSES,patch_issue,add_action,add_issue,text)
from workbook_store import ConflictError,UnknownSaveError,StoreError


def date_value(v): return pd.Timestamp(v).date() if v is not None and text(v) else None


def commit(builder,store,snapshot,user):
    # Recheck authorization in the write path, not just the visibility of the editor.
    authenticated=current_user()
    if not authenticated or authenticated['role']!='editor' or not user or authenticated['username']!=user['username']:
        st.error('Your account does not have edit permission.');return
    if st.session_state.get('save_blocked'):
        st.error('Reload the workbook before another save. Download your draft first.');return
    try:
        data=builder()
        st.session_state.pending_draft=data
        new_snapshot=store.save(snapshot,data)
    except (ConflictError,UnknownSaveError) as exc:
        st.session_state.save_blocked=True
        st.error(str(exc));return
    except (ValueError,StoreError) as exc:
        st.error(str(exc));return
    except Exception:
        st.session_state.save_blocked=True
        st.error('Save could not be confirmed. Download your draft if available, then reload and check Dashboard History in Excel before retrying.');return
    st.session_state.snapshot=new_snapshot
    st.session_state.pop('pending_draft',None)
    st.session_state.pop('save_blocked',None)
    st.session_state.saved_message='Saved to Dropbox. The dashboard now shows the saved workbook.'
    st.rerun()


def fields_form(rec,key,new=False):
    fields={}
    a,b=st.columns(2)
    with a:
        fields['Project']=st.text_input('Project',value=rec.get('Project',''),key=key+'project')
        fields['Topic']=st.text_input('Topic',value=rec.get('Topic',''),key=key+'topic')
        fields['Problem']=st.text_area('Problem',value=rec.get('Problem',''),key=key+'problem')
        fields['Root cause']=st.text_area('Root cause',value=rec.get('Root cause',''),key=key+'cause')
        options=['','Suspected','Confirmed']
        confidence=rec.get('Root cause confidence','')
        fields['Root cause confidence']=st.selectbox('Root cause confidence',options,index=options.index(confidence) if confidence in options else 0,key=key+'confidence')
        severity=rec.get('Severity','Unassessed')
        fields['Severity']=st.selectbox('Severity',SEVERITIES,index=SEVERITIES.index(severity),key=key+'severity')
        status=rec.get('Status','New' if new else 'Unreviewed')
        fields['Status']=st.selectbox('Status',ISSUE_STATUSES,index=ISSUE_STATUSES.index(status),key=key+'status')
        fields['Responsible']=st.text_input('Accountable issue owner',value=rec.get('Responsible',''),key=key+'owner',help='One owner. Original partner and Special Ops responsibilities stay in the detail table below.')
    with b:
        for field in ['Date identified','Target resolution','Resolution date']:
            fields[field]=st.date_input(field,value=date_value(rec.get(field)),key=key+field)
        fields['Success criterion']=st.text_area('Success criterion',value=rec.get('Success criterion',''),key=key+'success')
        fields['Decision needed']=st.text_area('Decision needed',value=rec.get('Decision needed',''),key=key+'decision')
        fields['Decision owner']=st.text_input('Decision owner',value=rec.get('Decision owner',''),key=key+'decowner')
        fields['Decision due']=st.date_input('Decision due',value=date_value(rec.get('Decision due')),key=key+'decdue')
        fields['Pertinent notes']=st.text_area('Pertinent notes',value=rec.get('Pertinent notes',''),key=key+'notes')
    return fields


def action_form(key):
    return {'Action':st.text_area('Action',key=key+'act'),
            'Responsible':st.text_input('Action owner',key=key+'owner'),
            'Status':st.selectbox('Action status',ACTION_STATUSES,index=1,key=key+'status'),
            'Due date':st.date_input('Due date',value=None,key=key+'due'),
            'Completed date':st.date_input('Completed date',value=None,key=key+'done'),
            'Blocker':st.text_input('Blocker',key=key+'blocker'),
            'Pertinent notes':st.text_area('Action notes',key=key+'notes')}


def render_editor(parsed,store,snapshot,today):
    user=editor_login()
    if user is None: return
    st.subheader('Update the source workbook')
    if user['role']!='editor': st.info('Your account has view-only access.');return
    if store is None: st.info('Dropbox editing is not connected. Add the Dropbox credentials to Streamlit Secrets using README.md.');return
    st.caption('Edits stay in the form until Save to Dropbox is pressed. Refreshing, switching issues, or leaving the page can discard unsaved form input. Save one form at a time. Original Overview is never edited.')
    now=lambda:datetime.now(timezone.utc)
    issues=parsed['tables']['Issues']
    choice=st.radio('What would you like to do?',['Edit existing issue','Add issue'],horizontal=True)
    if choice=='Add issue':
        partner=st.selectbox('Partner sheet',PARTNERS,key='new_partner')
        key='new_'+snapshot['rev']+partner
        with st.form(key):
            fields=fields_form({'Date identified':today.date()},key,new=True)
            detail={}
            for field in ['Effects','Solutions','Partner responsible','Special Ops responsible','Timing']:
                detail[field]=st.text_area(field,key=key+field)
            st.caption('Use Add action after creating the issue to add separate actions with owners and deadlines.')
            submit=st.form_submit_button('Save new issue to Dropbox',disabled=st.session_state.get('save_blocked',False))
        if submit: commit(lambda:add_issue(snapshot['bytes'],partner,fields,detail,user['username'],now()),store,snapshot,user)
    else:
        if issues.empty: st.info('No issues yet. Choose Add issue.');return
        st.caption('This selector includes all issues, independent of the dashboard sidebar filters.')
        options=list(parsed['groups'])
        selected=st.selectbox('Issue to edit',options,format_func=lambda v: f"{v[0]} / {parsed['groups'][v]['issue']['Project']} / {parsed['groups'][v]['issue']['Topic']} — {parsed['groups'][v]['issue']['Problem']}")
        partner,start=selected;group=parsed['groups'][selected];rec=group['issue']
        key=snapshot['rev']+partner+str(start)
        operation=st.radio('Update type',['Issue and existing actions','Add action'],horizontal=True)
        if operation=='Add action':
            with st.form('addact_'+key):
                fields=action_form('addact_'+key)
                submit=st.form_submit_button('Save new action to Dropbox',disabled=st.session_state.get('save_blocked',False))
            if submit: commit(lambda:add_action(snapshot['bytes'],partner,start,fields,user['username'],now()),store,snapshot,user)
        else:
            with st.form('edit_'+key):
                fields=fields_form(rec,key)
                st.write('**Original issue detail rows**')
                st.caption('Each row retains its Effects, Solution, partner/Special Ops responsibilities and Timing. Only rows with a Solution count as actions. Excel row numbers are locations in this loaded workbook, not added issue IDs.')
                detail_df=pd.DataFrame(group['details'],columns=DETAIL_COLS)
                for col in ['Action due','Action completed']: detail_df[col]=pd.to_datetime(detail_df[col])
                edited=st.data_editor(detail_df,hide_index=True,num_rows='fixed',disabled=['Excel row'],width='stretch',key='detail_'+key,column_config={
                    'Action status':st.column_config.SelectboxColumn(options=ACTION_STATUSES,required=True),
                    'Action due':st.column_config.DateColumn(format='YYYY-MM-DD'),
                    'Action completed':st.column_config.DateColumn(format='YYYY-MM-DD')})
                extras=parsed['extra']; extra_edits=[]
                if len(extras):
                    mask=extras[NATURAL].apply(lambda row: tuple(row)==tuple(rec[c] for c in NATURAL),axis=1)
                    subset=extras[mask].copy()
                    if len(subset):
                        subset.insert(0,'Excel row',[extras.attrs['excel_rows'][i] for i in subset.index])
                        subset=subset[['Excel row']+EXTRA_COLS[3:]]
                        for col in ['Due date','Completed date']: subset[col]=pd.to_datetime(subset[col].replace('',None))
                        st.write('**Additional actions**')
                        extra_edited=st.data_editor(subset,hide_index=True,num_rows='fixed',disabled=['Excel row'],width='stretch',key='extra_'+key,column_config={
                            'Status':st.column_config.SelectboxColumn(options=ACTION_STATUSES,required=True),
                            'Due date':st.column_config.DateColumn(format='YYYY-MM-DD'),
                            'Completed date':st.column_config.DateColumn(format='YYYY-MM-DD')})
                        extra_edits=extra_edited.to_dict('records')
                note=st.text_input('Reason or context for this update',key='reason_'+key)
                submit=st.form_submit_button('Save changes to Dropbox',disabled=st.session_state.get('save_blocked',False))
            if submit: commit(lambda:patch_issue(snapshot['bytes'],partner,start,fields,edited.to_dict('records'),extra_edits,user['username'],now(),note),store,snapshot,user)
    if 'pending_draft' in st.session_state:
        st.download_button('Download unsaved draft workbook',st.session_state.pending_draft,'SpOps_unsaved_draft.xlsx',help='This download is a recovery copy. It does not mean Dropbox accepted the save.')


st.set_page_config(page_title='Special Ops | Issues',page_icon='📋',layout='wide')
st.markdown('''<style>
.block-container {max-width:1500px;padding-top:2rem;padding-bottom:3rem;}
h1,h2,h3 {letter-spacing:-.03em;}
.issue-tag {display:inline-block;border-radius:20px;padding:4px 11px;margin:0 5px 7px 0;font-size:12px;font-weight:600;}
.issue-eyebrow {font-size:12px;font-weight:650;letter-spacing:.06em;color:#52727c;text-transform:uppercase;margin:5px 0 10px;}
</style>''',unsafe_allow_html=True)
st.title('Critical issues, clearly.')
st.caption('One shared view of the problems, people and next steps for priority topics with partners across Special Ops.')
try: today=pd.Timestamp(datetime.now(ZoneInfo(setting('TIMEZONE','America/Los_Angeles'))).date())
except Exception: st.error('Set a valid TIMEZONE in Streamlit Secrets.');st.stop()
config=dict(setting('dropbox',{}))
connected=all(config.get(k) for k in ['app_key','app_secret','refresh_token'])
store=DropboxStore(config) if connected else None
with st.sidebar:
    st.subheader('Source workbook')
    st.caption('SPCL · SPOL · PM')
    st.caption('Version: '+APP_VERSION)
    if st.button('Refresh from Dropbox',width='stretch'):
        st.session_state.pop('snapshot',None)
        st.session_state.pop('save_blocked',None)
        st.rerun()
    st.caption('Refresh to see changes made by someone else. Save any form edits first.')
if 'snapshot' not in st.session_state:
    try:
        if store: st.session_state.snapshot=store.load()
        else:
            with requests.get(DEFAULT_LINK.replace('dl=0','dl=1'),timeout=(10,45),stream=True) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>MAX_BYTES: raise ValueError('Workbook exceeds 20 MB.')
                    chunks.append(chunk)
            data=b''.join(chunks)
            st.session_state.snapshot={'bytes':data,'rev':'read-only','file_id':'','name':'SpOps_ProjectCriticalPoints-Priorities.xlsx','modified':''}
    except StoreError as exc: st.error(str(exc));st.stop()
    except Exception: st.error('Could not load the Dropbox workbook. Try Refresh from Dropbox.');st.stop()
snapshot=st.session_state.snapshot
if store and snapshot['rev']=='read-only':
    st.session_state.pop('snapshot',None);st.rerun()
try: parsed=read(snapshot['bytes'])
except Exception as exc: st.error(f'Workbook layout or values need attention: {exc}');st.stop()
tables=parsed['tables']
issues,actions=calculate(tables,today,14)
if 'saved_message' in st.session_state: st.success(st.session_state.pop('saved_message'))
with st.sidebar:
    st.caption(snapshot['name'])
    if snapshot.get('modified'): st.caption('Dropbox update: '+snapshot['modified'])
    st.caption('Viewing is open. Sign in only in Edit & Save.')


def related(frame,subset):
    return frame.merge(subset[KEY],on=KEY,how='inner')


def date_label(value):
    return pd.Timestamp(value).strftime('%d %b %Y') if pd.notna(value) else 'Not set'


def labels(row):
    status=row['Status'];severity=row['Severity']
    colors={'Closed':('#dff3e6','#1c6037'),'Monitoring':('#e8edff','#404996'),'Blocked':('#ffe8db','#9c411c'),'In Progress':('#dff1f6','#20596b'),'New':('#e8edf0','#405461'),'Unreviewed':('#edf0f2','#536570')}
    background,foreground=colors.get(status,('#edf0f2','#536570'))
    result=f'<span class="issue-tag" style="background:{background};color:{foreground}">{escape(status)}</span>'
    sc={'Critical':('#fde2e4','#992533'),'High':('#ffeddb','#8b4d16'),'Medium':('#fff5cb','#745d13'),'Low':('#e8f3e9','#386040'),'Unassessed':('#edf0f2','#536570')}
    bg,fg=sc.get(severity,sc['Unassessed'])
    result+=f'<span class="issue-tag" style="background:{bg};color:{fg}">{escape(severity)}</span>'
    if row['Overdue actions']:result+=f'<span class="issue-tag" style="background:#fde2e4;color:#992533">{int(row["Overdue actions"])} overdue action(s)</span>'
    st.markdown(result,unsafe_allow_html=True)


def field(label,value):
    if value and str(value).strip():
        st.markdown('**'+label+'**')
        st.text(str(value))


def issue_details(row):
    labels(row)
    st.subheader(row['Topic'] or 'Issue')
    st.caption(f"{row['Partner']} / {row['Project']}")
    field('Problem',row['Problem'])
    left,right=st.columns(2)
    with left:
        field('Root cause',row['Root cause'])
        if row['Root cause confidence']:st.caption('Cause: '+row['Root cause confidence'])
        field('Effects',row['Effects'])
        field('Notes',row['Pertinent notes'])
    with right:
        field('Proposed solution',row['Solutions'])
        field('Issue owner',row['Responsible'])
        field('Partner responsible',row['Partner responsible'])
        field('Special Ops responsible',row['Special Ops responsible'])
        field('Timing',row['Timing'])
        if pd.notna(row['Target resolution']): st.caption('Target resolution: '+date_label(row['Target resolution']))
    with st.expander('More tracking details'):
        for name in ['Success criterion','Decision needed','Decision owner']:field(name,row[name])
        for name in ['Date identified','Decision due','Last updated','Resolution date']:
            if pd.notna(row[name]):st.write(f'{name}: {date_label(row[name])}')
    matched=related(actions,pd.DataFrame([row]))
    if len(matched):
        st.markdown('**Related actions**')
        st.dataframe(matched[['Action','Responsible','Status','Due date','Blocker']],hide_index=True,width='stretch',column_config={'Due date':st.column_config.DateColumn(format='DD MMM YYYY')})


def status_style(value):
    colors={'Closed':'background-color:#dff3e6;color:#1c6037','Blocked':'background-color:#ffe8db;color:#9c411c','In Progress':'background-color:#dff1f6;color:#20596b','Monitoring':'background-color:#e8edff;color:#404996','Critical':'background-color:#fde2e4;color:#992533','High':'background-color:#ffeddb;color:#8b4d16'}
    return colors.get(value,'')


def reset_filters():
    for name in ['filter_project','filter_status','filter_partner_responsible','filter_special_ops_responsible']:st.session_state[name]=[]
    st.session_state.filter_partner='All partners'
    st.session_state.filter_search=''


def responsible_names(value):
    if pd.isna(value):
        return []
    # Split shared assignments into individual selectable names.
    return [name for part in re.split(r'[,;\n/&]+|\s+and\s+', str(value), flags=re.I)
            if (name := part.strip().rstrip('.…').strip())]


def responsible_options(column):
    return sorted({name for value in issues[column] for name in responsible_names(value)}, key=str.casefold)


all_tab,edit_tab=st.tabs(['All Issues','Edit & Save'])
with all_tab:
    search_col,partner_col=st.columns([2,1])
    search=search_col.text_input('Find an issue',placeholder='Search projects, problems, people or notes…',key='filter_search')
    partner=partner_col.selectbox('Partner',['All partners']+PARTNERS,key='filter_partner')
    with st.expander('More filters'):
        a,b=st.columns(2)
        projects=a.multiselect('Project',sorted(issues['Project'].unique()),key='filter_project')
        statuses=b.multiselect('Status',sorted(issues['Status'].unique()),key='filter_status')
        partner_owners=a.multiselect('Partner responsible',responsible_options('Partner responsible'),key='filter_partner_responsible')
        special_ops_owners=b.multiselect('Special Ops responsible',responsible_options('Special Ops responsible'),key='filter_special_ops_responsible')
        st.button('Clear filters',on_click=reset_filters)
    selected=issues.copy()
    if partner!='All partners':selected=selected[selected['Partner'].eq(partner)]
    for col,values in [('Project',projects),('Status',statuses)]:
        if values:selected=selected[selected[col].isin(values)]
    for col,values in [('Partner responsible',partner_owners),('Special Ops responsible',special_ops_owners)]:
        if values:
            selected=selected[selected[col].apply(lambda value: bool(set(responsible_names(value)) & set(values)))]
    if search:
        searchable=SCHEMA['Issues']+['Partner responsible','Special Ops responsible','Timing']
        match=selected[searchable].fillna('').astype(str).apply(lambda c:c.str.contains(search,case=False,regex=False)).any(axis=1)
        selected=selected[match]
    st.caption('Includes all statuses by default. Unreviewed issues count as open; Unassessed means severity has not been entered.')
    display_col,download_col=st.columns([2,1])
    mode=display_col.radio('View',['Cards','Table'],index=0,horizontal=True,key='view_cards_20261005_2')
    scoped_actions=related(actions,selected)
    report={'Issues':selected[SCHEMA['Issues']],'Actions':scoped_actions[SCHEMA['Actions']],'Updates':pd.DataFrame(columns=SCHEMA['Updates'])}
    # Preserve original responsibility/timing fields in the downloadable read-only report.
    from io import BytesIO
    from openpyxl import load_workbook
    output=BytesIO(workbook_bytes(report));export_wb=load_workbook(output);export_ws=export_wb['Issues']
    for offset,name in enumerate(['Partner responsible','Special Ops responsible','Timing'],len(SCHEMA['Issues'])+1):
        export_ws.cell(1,offset,name)
        for r,v in enumerate(selected[name],2):
            cell=export_ws.cell(r,offset,str(v));cell.data_type='s'
    # History is kept in the source workbook, not presented in this simplified export.
    del export_wb['Updates']
    export_bytes=BytesIO();export_wb.save(export_bytes)
    download_col.download_button('Download this list',export_bytes.getvalue(),'critical_issues_list.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if selected.empty:st.info('No matching issues. Try another partner or clear the filters.')
    elif mode=='Table':
        full=st.checkbox('Show every spreadsheet field',value=False)
        columns=['Partner','Project','Topic','Problem','Status','Partner responsible','Special Ops responsible','Timing']
        if full:columns=['Partner','Project','Topic','Root cause','Problem','Effects','Solutions','Partner responsible','Special Ops responsible','Timing','Pertinent notes','Severity','Status','Target resolution','Decision needed','Decision owner','Decision due','Success criterion','Date identified','Last updated','Resolution date']
        frame=selected[columns].reset_index(drop=True)
        styled=frame.style.map(status_style,subset=[c for c in ['Status','Severity'] if c in frame])
        signature=sha256(repr((snapshot['rev'],selected[KEY].values.tolist(),columns)).encode()).hexdigest()[:12]
        st.caption('Click a row checkbox to read the full issue below. Column headings sort the list; the toolbar offers search and fullscreen.')
        event=st.dataframe(styled,hide_index=True,width='stretch',height=460,on_select='rerun',selection_mode='single-row',key='issue_table_'+signature,column_config={
            'Problem':st.column_config.TextColumn(width='large'),
            'Pertinent notes':st.column_config.TextColumn('Notes',width='large'),
            **{name:st.column_config.DateColumn(format='DD MMM YYYY') for name in ['Target resolution','Decision due','Date identified','Last updated','Resolution date']}})
        rows=event.selection.rows
        if rows and rows[0]<len(selected):
            with st.container(border=True):issue_details(selected.iloc[rows[0]])
    else:
        # One expandable card per issue. No text is cut off in the expanded detail.
        columns=st.columns(2)
        for idx,(_,row) in enumerate(selected.iterrows()):
            with columns[idx%2]:
                with st.container(border=True):
                    st.markdown(f'<div class="issue-eyebrow">{escape(row["Partner"])} / {escape(row["Project"])}</div>',unsafe_allow_html=True)
                    labels(row)
                    st.subheader(row['Topic'] or 'Issue')
                    st.text(row['Problem'])
                    owner=row['Responsible'] or row['Partner responsible'] or 'Not yet assigned'
                    st.caption('Owner' + ('' if row['Responsible'] else ' / partner contacts') + ': '+owner)
                    if row['Timing']:st.caption('Timing: '+row['Timing'])
                    with st.expander('Read full issue'):issue_details(row)

with edit_tab:
    render_editor(parsed,store,snapshot,today)
