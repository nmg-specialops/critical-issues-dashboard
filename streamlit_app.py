"""Public issues register with an optional card view and protected editing."""
from datetime import datetime
from html import escape
from hashlib import sha256
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
from auth import setting
from data_model import KEY,SCHEMA,calculate,workbook_bytes
from workbook_model import read,PARTNERS
from workbook_store import DropboxStore,StoreError,DEFAULT_LINK,MAX_BYTES
from editor import render as render_editor

st.set_page_config(page_title='Special Ops | Issues',page_icon='📋',layout='wide')
st.markdown('''<style>
.block-container {max-width:1500px;padding-top:2rem;padding-bottom:3rem;}
h1,h2,h3 {letter-spacing:-.03em;}
[data-testid="stMetric"] {background:#eef5f5;border-radius:14px;padding:14px 20px;}
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {color:#173d50;}
.issue-tag {display:inline-block;border-radius:20px;padding:4px 11px;margin:0 5px 7px 0;font-size:12px;font-weight:600;}
.issue-eyebrow {font-size:12px;font-weight:650;letter-spacing:.06em;color:#52727c;text-transform:uppercase;margin:5px 0 10px;}
</style>''',unsafe_allow_html=True)
st.title('Critical issues, clearly.')
st.caption('One shared view of the problems, people and next steps across Special Ops.')
try: today=pd.Timestamp(datetime.now(ZoneInfo(setting('TIMEZONE','America/Los_Angeles'))).date())
except Exception: st.error('Set a valid TIMEZONE in Streamlit Secrets.');st.stop()
config=dict(setting('dropbox',{}))
connected=all(config.get(k) for k in ['app_key','app_secret','refresh_token'])
store=DropboxStore(config) if connected else None
with st.sidebar:
    st.subheader('Source workbook')
    st.caption('SPCL · SPOL · PM')
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
    for name in ['filter_project','filter_status','filter_priority']:st.session_state[name]=[]
    st.session_state.filter_partner='All partners'
    st.session_state.filter_search=''


all_tab,action_tab,edit_tab=st.tabs(['All Issues','Actions & Owners','Edit & Save'])
with all_tab:
    search_col,partner_col=st.columns([2,1])
    search=search_col.text_input('Find an issue',placeholder='Search projects, problems, people or notes…',key='filter_search')
    partner=partner_col.selectbox('Partner',['All partners']+PARTNERS,key='filter_partner')
    with st.expander('More filters'):
        a,b,c=st.columns(3)
        projects=a.multiselect('Project',sorted(issues['Project'].unique()),key='filter_project')
        statuses=b.multiselect('Status',sorted(issues['Status'].unique()),key='filter_status')
        priorities=c.multiselect('Severity',sorted(issues['Severity'].unique()),key='filter_priority')
        st.button('Clear filters',on_click=reset_filters)
    selected=issues.copy()
    if partner!='All partners':selected=selected[selected['Partner'].eq(partner)]
    for col,values in [('Project',projects),('Status',statuses),('Severity',priorities)]:
        if values:selected=selected[selected[col].isin(values)]
    if search:
        searchable=SCHEMA['Issues']+['Partner responsible','Special Ops responsible','Timing']
        match=selected[searchable].fillna('').astype(str).apply(lambda c:c.str.contains(search,case=False,regex=False)).any(axis=1)
        selected=selected[match]
    m1,m2,m3=st.columns(3)
    m1.metric('Issues shown',len(selected))
    m2.metric('Open',int(selected['Open'].sum()))
    m3.metric('Closed',int((~selected['Open']).sum()))
    st.caption('Includes all statuses by default. Unreviewed issues count as open; Unassessed means severity has not been entered.')
    display_col,download_col=st.columns([2,1])
    mode=display_col.radio('View',['Table','Cards'],horizontal=True,key='issue_view')
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
        columns=['Partner','Project','Topic','Problem','Status','Responsible','Partner responsible','Special Ops responsible','Timing']
        if full:columns=['Partner','Project','Topic','Root cause','Problem','Effects','Solutions','Responsible','Partner responsible','Special Ops responsible','Timing','Pertinent notes','Severity','Status','Target resolution','Decision needed','Decision owner','Decision due','Success criterion','Date identified','Last updated','Resolution date']
        frame=selected[columns].reset_index(drop=True)
        styled=frame.style.map(status_style,subset=[c for c in ['Status','Severity'] if c in frame])
        signature=sha256(repr((snapshot['rev'],selected[KEY].values.tolist(),columns)).encode()).hexdigest()[:12]
        st.caption('Click a row checkbox to read the full issue below. Column headings sort the list; the toolbar offers search and fullscreen.')
        event=st.dataframe(styled,hide_index=True,width='stretch',height=460,on_select='rerun',selection_mode='single-row',key='issue_table_'+signature,column_config={
            'Problem':st.column_config.TextColumn(width='large'),
            'Responsible':st.column_config.TextColumn('Issue owner'),
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

with action_tab:
    st.subheader('Who is doing what?')
    st.caption('Uses the partner, search and other filters from All Issues. Issue owners and action owners can be different people.')
    owner_col,scope_col=st.columns(2)
    owners=owner_col.multiselect('Action owner',sorted(scoped_actions['Responsible'].unique()),format_func=lambda x:x or 'Unassigned')
    scope=scope_col.radio('Show actions',['All','Pending','Overdue'],horizontal=True)
    view=scoped_actions.copy()
    if owners:view=view[view['Responsible'].isin(owners)]
    if scope=='Pending':view=view[view['Status'].ne('Done')]
    if scope=='Overdue':view=view[view['Overdue']]
    if view.empty:st.info('No actions match these filters.')
    else:
        view=view.sort_values('Due date',na_position='last')
        view['Days overdue']=view['Days overdue'].where(view['Overdue'],0)
        st.dataframe(view[['Partner','Project','Issue','Action','Responsible','Status','Due date','Blocker','Pertinent notes','Days overdue']],hide_index=True,width='stretch',column_config={'Due date':st.column_config.DateColumn(format='DD MMM YYYY'),'Action':st.column_config.TextColumn(width='large'),'Responsible':st.column_config.TextColumn('Action owner')})
        with st.expander('Group pending actions by owner'):
            pending=view[view['Status'].ne('Done')]
            for owner,group in pending.groupby('Responsible',dropna=False):
                st.markdown('**'+(owner or 'Unassigned')+f' ({len(group)})**')
                st.dataframe(group[['Project','Action','Status','Due date','Blocker']],hide_index=True,width='stretch')

with edit_tab:
    render_editor(parsed,store,snapshot,today)
