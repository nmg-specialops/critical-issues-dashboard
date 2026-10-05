"""Explicit-save forms for partner issue cells and additional actions."""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from workbook_model import (PARTNERS,META,DETAIL_COLS,EXTRA_COLS,NATURAL,ISSUE_STATUSES,SEVERITIES,ACTION_STATUSES,patch_issue,add_action,add_issue,text)
from workbook_store import ConflictError,UnknownSaveError,StoreError
from auth import current_user,editor_login


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


def render(parsed,store,snapshot,today):
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
