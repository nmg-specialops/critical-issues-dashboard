"""Partner critical issues: fixed grouped tables and explicit anonymous saves."""
from datetime import date
from hashlib import sha256
from html import escape
import requests
import streamlit as st
from partner_model import PARTNERS,FIELDS,DATES,read,save_issue,text
from workbook_store import DropboxStore,StoreError,ConflictError,UnknownSaveError,DEFAULT_LINK,MAX_BYTES

def setting(key,default=None):
    try:return st.secrets.get(key,default)
    except FileNotFoundError:return default

st.set_page_config(page_title='Special Ops - Partner Critical Issues',page_icon='📋',layout='wide')
st.markdown('''<style>
.block-container{max-width:1900px;padding:2rem 1.5rem 3rem;}
h1,h2,h3{letter-spacing:-.025em;}
.partner-table-wrap{overflow-x:auto;margin-bottom:24px;}
.partner-table{width:100%;min-width:1400px;border-collapse:collapse;table-layout:fixed;font-size:13px;}
.partner-table th,.partner-table td{padding:9px;border:1px solid #d9dfe3;text-align:left;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere;}
.partner-table th{background:#edf1f3;color:#25343b;}
.partner-table .project-row td{background:#e8eef0;color:#263c45;font-size:15px;font-weight:650;}
.partner-table th:nth-child(7),.partner-table th:nth-child(8){width:112px;box-sizing:border-box;}
.partner-table tbody tr:not(.project-row) td:nth-child(7),.partner-table tbody tr:not(.project-row) td:nth-child(8){white-space:nowrap;overflow-wrap:normal;}
.notes-cell summary{cursor:pointer;display:flex;align-items:center;gap:6px;list-style:none;white-space:normal;}
.notes-cell summary::-webkit-details-marker{display:none;}
.notes-preview{display:block;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.notes-cell summary::after{content:"▸";flex:none;color:#246773;}
.notes-cell[open] summary::after{content:"▾";}
.notes-full{margin-top:8px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:240px;overflow-y:auto;}
</style>''',unsafe_allow_html=True)
st.title('Special Ops - Partner Critical Issues.')
st.caption('One shared view of the problems, people and next steps for priority topics with partners across Special Ops.')
config=dict(setting('dropbox',{}))
store=DropboxStore(config) if all(config.get(k) for k in ['app_key','app_secret','refresh_token']) else None
with st.sidebar:
    st.caption('SPCL · SPOL · PM')
    if st.button('Refresh from Dropbox'):
        st.session_state.pop('snapshot',None)
        st.session_state.pop('save_blocked',None)
        st.session_state.pop('pending_draft',None)
    st.caption('Save before refreshing. Version: Partner tables · 2026-10-12')
if 'snapshot' not in st.session_state:
    try:
        if store:st.session_state.snapshot=store.load()
        else:
            with requests.get(config.get('shared_link',DEFAULT_LINK).replace('dl=0','dl=1'),timeout=(10,45),stream=True) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>MAX_BYTES:raise StoreError('Workbook exceeds 20 MB.')
                    chunks.append(chunk)
                st.session_state.snapshot={'bytes':b''.join(chunks),'rev':'read-only'}
    except Exception as exc:st.error('Could not load the workbook. '+str(exc));st.stop()
snapshot=st.session_state.snapshot
try:records=read(snapshot['bytes'])
except Exception as exc:st.error('Could not read the workbook. '+str(exc));st.stop()
if st.session_state.get('saved_message'):st.success(st.session_state.pop('saved_message'))

def projects(items):
    return list(dict.fromkeys(item['Project'] for item in items))

def cell_html(field,value):
    value=escape(text(value))
    if field=='Notes' and value:
        return ('<details class="notes-cell"><summary title="Expand or collapse notes">'
                '<span class="notes-preview">'+value+'</span></summary>'
                '<div class="notes-full">'+value+'</div></details>')
    return value

mode=st.radio('View',['Table','Cards'],horizontal=True,index=0,key='partner_view_20261012')
columns=[f for f in FIELDS if f!='Project']
for partner,title in PARTNERS.items():
    items=[r for r in records if r['Partner']==partner]
    st.header(title)
    if not items:
        st.caption('No issues listed yet.');continue
    if mode=='Table':
        header=''.join('<th scope="col">'+escape(f)+'</th>' for f in columns)
        body=[]
        for project in projects(items):
            body.append('<tr class="project-row"><td colspan="'+str(len(columns))+'">'+escape(project or 'Other projects')+'</td></tr>')
            for item in (r for r in items if r['Project']==project):
                body.append('<tr>'+''.join('<td>'+cell_html(f,item[f])+'</td>' for f in columns)+'</tr>')
        st.markdown('<div class="partner-table-wrap"><table class="partner-table" aria-label="'+escape(title)+' issues"><thead><tr>'+header+'</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>',unsafe_allow_html=True)
    else:
        for project in projects(items):
            st.subheader(project or 'Other projects')
            for item in (r for r in items if r['Project']==project):
                summary=' '.join(item['Problem'].split())
                if len(summary)>95:summary=summary[:92]+'…'
                with st.expander(item['Topic']+' | '+summary):
                    for f in columns:
                        if text(item[f]):
                            st.markdown('**'+f+'**');st.text(item[f])

st.divider()
st.subheader('Edit issues')
if store is None:
    st.info('Dropbox editing is not connected. Keep the existing Dropbox credentials in Streamlit Secrets to enable saving.')
else:
    st.caption('Changes are saved only when you click Save Changes. App saves are recorded in the workbook’s Dashboard History as Anonymous editor.')
    partner=st.selectbox('Partner',list(PARTNERS),format_func=lambda k:PARTNERS[k])
    mode_edit=st.radio('Choose',['Edit existing issue','Add issue'],horizontal=True)
    candidates=[r for r in records if r['Partner']==partner]
    chosen=None
    if mode_edit=='Edit existing issue':
        if candidates:
            project=st.selectbox('Project to edit',projects(candidates))
            options=[r for r in candidates if r['Project']==project]
            index=st.selectbox('Topic to edit',range(len(options)),format_func=lambda i:options[i]['Topic']+' — '+options[i]['Problem'][:100])
            chosen=options[index]
        else:st.info('No issues for this partner. Select Add issue to create one.')
    if chosen is not None or mode_edit=='Add issue':
        current=chosen or {f:'' for f in FIELDS}
        key=sha256((str(snapshot['rev'])+sha256(snapshot['bytes']).hexdigest()+partner+str(chosen['SourceRow'] if chosen else 'new')).encode()).hexdigest()[:16]
        with st.form('issue_'+key):
            fields={}
            left,right=st.columns(2)
            for index,f in enumerate(FIELDS):
                with (left if index%2==0 else right):
                    if f in DATES:
                        try:value=date.fromisoformat(current[f][:10]) if current[f] else None
                        except ValueError:value=None
                        if current[f] and value is None:
                            fields[f]=st.text_input(f,value=current[f],help='Use YYYY-MM-DD to save a date.')
                        else:fields[f]=st.date_input(f,value=value,format='DD/MM/YYYY',key=key+f)
                    elif f=='Status':
                        statuses=['','New','In Progress','Blocked','Monitoring','Closed']
                        if current[f] not in statuses:statuses.append(current[f])
                        fields[f]=st.selectbox(f,statuses,index=statuses.index(current[f]))
                    elif f in ['Project','Topic','Responsible']:fields[f]=st.text_input(f,value=current[f])
                    else:fields[f]=st.text_area(f,value=current[f],height=90)
            submit=st.form_submit_button('Save Changes',type='primary')
        if submit:
            if st.session_state.get('save_blocked'):st.error('Refresh the workbook before another save. Download your unsaved draft first.')
            else:
                try:
                    data=save_issue(snapshot['bytes'],partner,chosen['SourceRow'] if chosen else None,fields)
                    st.session_state.pending_draft=data
                    st.session_state.snapshot=store.save(snapshot,data)
                except (ConflictError,UnknownSaveError) as exc:
                    st.session_state.save_blocked=True;st.error(str(exc))
                except (ValueError,StoreError) as exc:st.error(str(exc))
                except Exception:
                    st.session_state.save_blocked=True
                    st.error('Save could not be confirmed. Download your draft, refresh, and check Dashboard History before retrying.')
                else:
                    st.session_state.pop('pending_draft',None)
                    st.session_state.saved_message='Changes saved.'
                    st.rerun()
    if 'pending_draft' in st.session_state:
        st.download_button('Download unsaved draft',st.session_state.pending_draft,'SpOps_unsaved_draft.xlsx')
