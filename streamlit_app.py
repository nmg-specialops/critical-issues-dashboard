from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import plotly.express as px
import streamlit as st
from auth import require_user
from data_model import KEY,SCHEMA,calculate,workbook_bytes
from workbook_model import read
from workbook_store import DropboxStore,StoreError,DEFAULT_LINK,MAX_BYTES
from editor import render as render_editor

st.set_page_config(page_title='Special Ops | Critical Issues',page_icon='📍',layout='wide')
st.markdown('<style>.block-container {padding-top:2rem;} [data-testid="stMetric"] {background:#edf4f5;padding:1rem;border-radius:12px;color:#173D50;} h1,h2,h3 {letter-spacing:-.025em;}</style>',unsafe_allow_html=True)
st.title('Special Ops · Critical Issues & Priorities')
user=require_user()
try: today=pd.Timestamp(datetime.now(ZoneInfo(st.secrets.get('TIMEZONE','America/Los_Angeles'))).date())
except Exception: st.error('Set a valid TIMEZONE in Secrets.');st.stop()
config=dict(st.secrets.get('dropbox',{}))
connected=all(config.get(k) for k in ['app_key','app_secret','refresh_token'])
store=DropboxStore(config) if connected else None
with st.sidebar:
    st.write(f"Signed in: {user['name']} ({user['role']})")
    if st.button('Sign out'):
        st.session_state.clear();st.rerun()
    st.header('Workbook')
    st.caption('Source: SPCL, SPOL and PM partner sheets. Overview is excluded.')
    st.caption('Refresh discards unsaved form input. Save or download a draft first.')
    if st.button('Reload from Dropbox',width='stretch'):
        st.session_state.pop('snapshot',None)
        st.session_state.pop('save_blocked',None)
        st.rerun()
    stale_days=st.number_input('Flag updates older than (days)',min_value=1,value=14)
if 'snapshot' not in st.session_state:
    try:
        if store:
            st.session_state.snapshot=store.load()
        else:
            # Read-only access to the exact supplied link; no source file is packaged in GitHub.
            with requests.get(DEFAULT_LINK.replace('dl=0','dl=1'),timeout=(10,45),stream=True) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>MAX_BYTES: raise ValueError('Workbook exceeds 20 MB.')
                    chunks.append(chunk)
            data=b''.join(chunks)
            st.session_state.snapshot={'bytes':data,'rev':'read-only','file_id':'','name':'SpOps_ProjectCriticalPoints-Priorities.xlsx','modified':''}
    except StoreError as exc: st.error(str(exc));st.stop()
    except Exception: st.error('Could not download the source workbook. Check Dropbox access and try Reload.');st.stop()
snapshot=st.session_state.snapshot
# If credentials have been added to a previously read-only session, obtain an authenticated snapshot before allowing saves.
if store and snapshot['rev']=='read-only':
    st.session_state.pop('snapshot',None);st.rerun()
try: parsed=read(snapshot['bytes'])
except Exception as exc: st.error(f'Workbook layout or values need attention: {exc}');st.stop()
tables=parsed['tables']
issues,actions=calculate(tables,today,stale_days)
if 'saved_message' in st.session_state: st.success(st.session_state.pop('saved_message'))
if not connected: st.info('Read-only connection. To enable Save to Dropbox, complete the one-time Dropbox setup in README.md.')
st.caption(f"{snapshot['name']} · {len(issues)} issues · Reporting date {today:%d %b %Y} · {snapshot.get('modified','')}")
unassessed = int(issues['Severity'].eq('Unassessed').sum())
unreviewed = int(issues['Status'].eq('Unreviewed').sum())
if unassessed or unreviewed:
    st.warning(f'{unassessed} issues have no assessed severity; {unreviewed} have no reviewed status. Review these in Edit & Save. Existing responsibility and timing text is preserved.')

with st.sidebar:
    st.header('Filters')
    selected = issues.copy()
    for col in ['Partner','Project','Topic','Severity','Status','Responsible']:
        options = sorted(issues[col].unique())
        values = st.multiselect('Issue '+col.lower(),options,format_func=lambda x: x or '(Unassigned)')
        if values: selected = selected[selected[col].isin(values)]
    search = st.text_input('Search issue text')
    if search:
        mask = selected[SCHEMA['Issues']].fillna('').astype(str).apply(lambda col: col.str.contains(search,case=False,regex=False)).any(axis=1)
        selected = selected[mask]
    st.caption('Sidebar filters apply to the five dashboard tabs. Edit & Save has its own issue selector. Responsible filters the issue owner; the Actions tab has a separate action-owner filter.')

def related(frame, subset):
    return frame.merge(subset[KEY],on=KEY,how='inner')

def table(frame, columns=None):
    if frame.empty: st.info('No matching records.'); return
    st.dataframe(frame[columns] if columns else frame,hide_index=True,width='stretch')

def chart(fig):
    fig.update_layout(margin=dict(l=15,r=15,t=35,b=20),height=420,legend=dict(orientation='h',y=-.25),font=dict(size=13))
    st.plotly_chart(fig,width='stretch')

def card(row):
    title = f"{row['Severity']} · {row['Issue']} — {row['Partner']} / {row['Project']}"
    with st.expander(title):
        st.write(row['Attention reasons'])
        st.write(f"**Status:** {row['Status']} · **Owner:** {row['Responsible'] or 'Unassigned'}")
        for label in ['Partner responsible','Special Ops responsible','Timing','Problem','Effects','Root cause','Root cause confidence','Solutions','Success criterion','Decision needed','Decision owner','Pertinent notes']:
            if row[label]: st.write(f'**{label}:** {row[label]}')
        for label in ['Date identified','Target resolution','Decision due','Last updated']:
            if pd.notna(row[label]): st.write(f'**{label}:** {row[label]:%d %b %Y}')
        if row['Data gaps']: st.warning(row['Data gaps'])
        one = pd.DataFrame([row])
        st.write('**Actions**')
        table(related(actions,one),['Action','Responsible','Status','Due date','Blocker','Pertinent notes'])
        updates = related(tables['Updates'],one).sort_values('Date',ascending=False)
        if len(updates):
            st.write('**Update history**'); table(updates,['Date','Change type','Previous value','New value','Note'])

active = selected[selected['Open']]
scoped_actions = related(actions,selected)
open_actions = scoped_actions[scoped_actions['Status'].ne('Done')]
tabs = st.tabs(['Attention Now','All Issues','Actions & Owners','Patterns & Causes','Progress & History','Edit & Save'])
with tabs[0]:
    st.subheader('Where attention is needed')
    metrics = [('Critical',int(active['Severity'].eq('Critical').sum())),('Overdue actions',int(open_actions['Overdue'].sum())),('Blocked',int(active['Status'].eq('Blocked').sum())),('Decisions',int(active['Decision pending'].sum())),('Unassigned',int(active['Responsible'].eq('').sum()))]
    if 'focus' not in st.session_state: st.session_state.focus = 'All open'
    for col,(label,value) in zip(st.columns(5),metrics):
        col.metric(label,value)
        if col.button('Show '+label.lower(),key=label,width='stretch'): st.session_state.focus=label
    if st.button('Show all open issues'): st.session_state.focus='All open'
    focus = st.session_state.focus
    masks = {'Critical':active['Severity'].eq('Critical'),'Overdue actions':active['Overdue actions'].gt(0),'Blocked':active['Status'].eq('Blocked'),'Decisions':active['Decision pending'],'Unassigned':active['Responsible'].eq('')}
    queue = active[masks[focus]] if focus in masks else active
    queue = queue.sort_values(['Impact level','Overdue actions','Resolution overdue','Age (days)'],ascending=[False,False,False,False],na_position='last')
    st.write(f'**Attention queue: {focus} ({len(queue)} issues)**')
    st.caption('Ranked by severity, overdue action count, overdue resolution, then issue age. No hidden priority score.')
    if queue.empty: st.success('No issues match this attention filter.')
    for _,row in queue.iterrows(): card(row)
    st.subheader('Decisions needed')
    table(active[active['Decision pending']].sort_values('Decision due'),KEY+['Decision needed','Decision owner','Decision due'])
    st.subheader('Information gaps')
    table(selected[selected['Data gaps'].ne('')],KEY+['Status','Data gaps'])
with tabs[1]:
    st.subheader('Issue register')
    table(selected,SCHEMA['Issues']+['Partner responsible','Special Ops responsible','Timing','Age (days)','Overdue actions','Attention reasons','Data gaps'])
    # Export to Excel to preserve dates and avoid CSV formula interpretation.
    export = {'Issues':selected[SCHEMA['Issues']], 'Actions':scoped_actions[SCHEMA['Actions']], 'Updates':related(tables['Updates'],selected)}
    st.caption('This export is a separate report, not the source workbook. Use Edit & Save for changes to Dropbox.')
    st.download_button('Export filtered report',workbook_bytes(export),'filtered_issues.xlsx')
    if len(selected):
        index = st.selectbox('Inspect an issue',list(selected.index),format_func=lambda n: ' / '.join(selected.loc[n,KEY]))
        card(selected.loc[index])
with tabs[2]:
    st.subheader('Actions & owners')
    owners = st.multiselect('Action owner',sorted(scoped_actions['Responsible'].unique()),format_func=lambda x: x or '(Unassigned)')
    view = scoped_actions[scoped_actions['Responsible'].isin(owners)] if owners else scoped_actions
    only_overdue = st.checkbox('Only overdue actions')
    if only_overdue: view = view[view['Overdue']]
    table(view.sort_values('Due date'),SCHEMA['Actions']+['Overdue','Days overdue'])
    workload = view[view['Status'].ne('Done')].copy()
    if len(workload):
        workload['Responsible'] = workload['Responsible'].replace('','Unassigned')
        chart(px.histogram(workload,x='Responsible',color='Status',title='Pending action workload',barmode='stack'))
    gaps = scoped_actions[(scoped_actions['Status'].ne('Done') & (scoped_actions['Responsible'].eq('') | scoped_actions['Due date'].isna())) | (scoped_actions['Status'].eq('Done') & scoped_actions['Completed date'].isna())]
    st.write('**Actions needing an owner, deadline, or completion date**')
    table(gaps,SCHEMA['Actions'])
    st.subheader('Shared blockers')
    blocked = open_actions[open_actions['Blocker'].ne('')].copy()
    st.caption('Use the same blocker wording on affected actions to reveal shared dependencies. This is a grouped dependency view, not an automatically inferred task network.')
    if len(blocked):
        for blocker, group in blocked.groupby('Blocker'):
            with st.expander(f'{blocker} — {len(group)} actions / {len(group[KEY].drop_duplicates())} issues'):
                table(group,KEY+['Action','Responsible','Due date'])
    else: st.info('No recorded blockers.')
with tabs[3]:
    st.subheader('Patterns behind unresolved issues')
    if active.empty: st.info('No open issues in the selected scope.')
    else:
        aged = active.dropna(subset=['Age (days)','Impact level'])
        if len(aged):
            fig = px.scatter(aged,x='Age (days)',y='Impact level',color='Status',hover_name='Issue',hover_data=['Partner','Project','Responsible'],title='Issue age versus impact')
            fig.update_traces(marker=dict(size=14,opacity=.8))
            fig.update_yaxes(tickvals=[1,2,3,4],ticktext=['Low','Medium','High','Critical'])
            chart(fig)
        st.caption(f"{len(active)-len(aged)} open issues lack an identification date or assessed severity and are excluded from the age plot.")
        heat = pd.crosstab(active['Project'],active['Topic'].replace('','Unspecified'))
        chart(px.imshow(heat,text_auto=True,aspect='auto',color_continuous_scale='Blues',title='Open issues by project and topic'))
        causes = active.copy(); causes['Root cause']=causes['Root cause'].replace('','Not recorded')
        chart(px.histogram(causes,y='Root cause',color='Root cause confidence',title='Root causes — suspected and confirmed'))
with tabs[4]:
    st.subheader('What changed?')
    since = pd.Timestamp(st.date_input('Review changes since',value=(today-pd.Timedelta(days=7)).date(),max_value=today.date()))
    updates = related(tables['Updates'],selected)
    recent = updates[updates['Date'].between(since,today)].sort_values('Date',ascending=False)
    table(recent,SCHEMA['Updates'])
    st.caption('History records saves made through this app. Direct Excel edits are reflected after reload but are not automatically logged. Current sidebar filters also limit this history.')
    st.write('**Newly identified issues in this review period**')
    table(selected[selected['Date identified'].between(since,today)],KEY+['Severity','Responsible','Date identified'])
    st.write('**Actions that became overdue during this review period**')
    table(open_actions[open_actions['Due date'].ge(since-pd.Timedelta(days=1)) & open_actions['Due date'].lt(today)],KEY+['Action','Responsible','Due date'])
    st.subheader('Opened versus resolved')
    created = selected['Date identified'].dropna()
    resolved = selected.loc[selected['Status'].eq('Closed'),'Resolution date'].dropna()
    created = created[created.le(today)]; resolved = resolved[resolved.le(today)]
    if len(created) or len(resolved):
        starts = list(created)+list(resolved)
        periods = pd.period_range(min(starts).to_period('M'),today.to_period('M'),freq='M')
        counts = pd.DataFrame({'Opened':created.dt.to_period('M').value_counts().reindex(periods,fill_value=0),'Resolved':resolved.dt.to_period('M').value_counts().reindex(periods,fill_value=0)})
        counts.index = counts.index.astype(str)
        chart(px.bar(counts,barmode='group',labels={'index':'Month','value':'Issues','variable':'Event'}))
    else: st.info('Add identification and resolution dates to see trends.')
    st.caption('Monthly counts use identification dates and resolution dates of currently closed issues. Repeated reopen/close cycles appear in app history but are not separate lifecycle events in this chart.')
    st.subheader('Solution effectiveness')
    table(selected[selected['Status'].eq('Monitoring')],KEY+['Solutions','Success criterion','Responsible','Target resolution'])
    reopened = updates[updates['Change type'].eq('Reopened') & updates['Date'].between(since,today)]
    st.metric('Recorded reopenings in review period',len(reopened))
    if len(reopened): table(reopened,SCHEMA['Updates'])

with tabs[5]:
    render_editor(parsed,store,snapshot,user,today)
