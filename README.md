# Special Ops Critical Issues Dashboard — Dropbox editing version

This replaces the earlier sample-data dashboard. It is adapted to **SpOps_ProjectCriticalPoints-Priorities.xlsx**, using the supplied Dropbox link.

The dashboard reads **SPCL, SPOL and PM directly**. It never reads or edits **Overview**. Streamlit creates the consolidated overview itself.

Editors can change issue details and actions in Streamlit and press **Save changes to Dropbox**. The app updates the same Excel workbook in Dropbox. Viewers can browse and download reports but cannot save changes.

## 1. What has been adapted to your workbook

The workbook inspected contained five SPCL issues, with empty SPOL and PM templates. The Montessori issue spans three rows. The app treats that block as one issue with three detail rows, preserving the individual effects, solutions, responsibilities and timing.

- Original sheets, merged ranges, cell styles and Overview formula expressions are retained by targeted workbook edits.
- The original A:J columns are retained: Project, Topic, Root cause, Problem, Effects, Solution, partner responsibility, Special Ops responsibility, Timing and Notes.
- Your existing SPCL responsibility header is interpreted as the partner's responsibility column on all partner sheets; it is not renamed.
- Existing free-text timing is retained exactly as text in the editor. A separate typed action due date drives overdue calculations.
- Existing responsibility text can name several people. It is preserved. The app adds a separate accountable issue owner and action owner, rather than selecting someone from that text.
- Missing severity is **Unassessed** and missing status is **Unreviewed**. No priorities, dates or confirmed causes are inferred from your notes.
- There is no unique issue ID column.

## 2. Files to put in GitHub

Use all files from this v2 package. Keep the original filenames.

| File | Purpose |
| --- | --- |
| `streamlit_app.py` | Dashboard and data loading |
| `data_model.py` | Metrics and filtered report export |
| `workbook_model.py` | Reads and updates your exact workbook layout |
| `workbook_store.py` | Authenticated Dropbox download/save with revision checks |
| `editor.py` | Edit, add-issue and add-action forms |
| `auth.py` | Dashboard login and viewer/editor roles |
| `configure.py` | One-time local credential and user setup |
| `requirements.txt` | Dependencies |
| `.streamlit/config.toml` | Theme and upload limit |
| `.gitignore` | Excludes real credentials and workbooks |
| `secrets.example.toml` | Configuration example with placeholders |
| `test_dashboard.py` | Offline automated tests using fictional data |
| `README.md` | These instructions |

The package does not contain a copy of your company workbook. It reads the current file from Dropbox. The supplied shared link is embedded in `workbook_store.py` as the default, so use a private repository.

## 3. GitHub setup

1. Download and unzip the updated `critical-issues-dashboard.zip`.
2. Create a new private GitHub repository named `critical-issues-dashboard`, or use the repository you created for the previous version.
3. Upload every file from the extracted folder. The Python files and `requirements.txt` belong at the repository root, not inside an extra outer folder.
4. If using the previous version's repository, replace the entire old `streamlit_app.py` and `data_model.py` files, and add the new supporting files. Do not append the new code beneath old code.
5. If the `.streamlit` folder is not visible on your computer, use GitHub **Add file → Create new file**, name it `.streamlit/config.toml`, and paste:

```toml
[theme]
base = "light"
primaryColor = "#167D8D"
backgroundColor = "#F7FAFB"
secondaryBackgroundColor = "#EAF1F4"
textColor = "#173D50"
font = "sans serif"

[server]
maxUploadSize = 20
```

6. Create `.gitignore` the same way if necessary:

```gitignore
.streamlit/secrets.toml
__pycache__/
.venv/
*.xlsx
```

7. Commit the changes.

Do not replace your separate SPCL agriculture/production/social app with these files. This package is for the critical-issues dashboard.

## 4. One-time Dropbox setup to enable writing

A Dropbox shared link enables reading; it is not a write credential. The dashboard needs your authorization through a Dropbox API app. No Dropbox password or app secret should be pasted into ChatGPT or committed to GitHub.

### A. Create a Dropbox API app

1. Sign in to the Dropbox account that owns the workbook or has edit access to it.
2. Open https://www.dropbox.com/developers/apps and choose **Create app**.
3. Choose **Scoped access** if asked.
4. Choose **Full Dropbox**, since the workbook already exists outside a new app-specific folder. The deployed code targets only the configured workbook, but this authorization grants the chosen file scopes across that account's Dropbox. An App folder app would require moving the workbook into that app's folder and changing its location configuration.
5. Give the API app a distinct name, for example `Nathalie-SpecialOps-Dashboard`.
6. In its **Permissions** tab, enable:

   - `files.metadata.read`
   - `files.content.read`
   - `files.content.write`
   - `sharing.read`

7. Submit/save those permissions before authorizing.
8. Under **Settings**, find the **App key** and **App secret**. Keep this page open.

Use the refresh-token setup below. A short-lived generated access token is not sufficient for continuous operation.

### B. Run the setup helper on your computer

You need Python 3.12 installed for this one-time step. On Windows, open PowerShell in the extracted folder. On macOS/Linux, open Terminal there.

Install the packages:

```bash
python -m pip install -r requirements.txt
```

Run:

```bash
python configure.py
```

If Windows uses `py` instead of `python`, use `py -3.12` for both commands.

The helper will:

1. Ask for your Dropbox app key and secret.
2. Display a Dropbox authorization URL. Open it in your browser.
3. Ask you to authorize the app using the account with workbook edit access.
4. Ask you to paste the resulting authorization code into the local terminal. Input is hidden.
5. Exchange that code for a refresh token.
6. Ask you to create a dashboard username, display name, role and password.
7. Write a local `.streamlit/secrets.toml` containing the Dropbox credentials and a salted password hash. Tokens are not printed.

Choose `editor` for your own account. Your dashboard password is separate from your Dropbox password.

The helper uses Dropbox's out-of-band authorization-code flow, so no redirect URI is needed for this local helper. The credential exchange and deployed dashboard use refresh tokens to obtain short-lived access tokens.

### C. Put the credentials in Streamlit Secrets

Open the generated `.streamlit/secrets.toml` in a text editor on your computer. Copy its contents into your Streamlit app's **Settings → Secrets**, or **Advanced settings → Secrets** during deployment.

Do not upload the real `secrets.toml` file to GitHub. `secrets.example.toml` is only a placeholder example; it cannot enable access by itself.

## 5. Deploy on Streamlit

1. Sign in at https://share.streamlit.io.
2. Select **Create app** and choose the existing-app option if prompted.
3. Select your GitHub repository and branch (usually `main`).
4. Set the main file path to `streamlit_app.py`.
5. In **Advanced settings**, choose Python **3.12**.
6. Paste the complete generated secrets configuration into **Secrets**.
7. Deploy.
8. Sign in with the dashboard username and password you created.

For an already deployed earlier version, update its repository files and add the new Secrets settings. Streamlit will rebuild from the repository.

Before setup is complete, the app displays a setup message without loading company data. With user accounts configured but no Dropbox credentials, it can display the supplied workbook through the shared link in read-only mode. The app never substitutes sample data for a failed load.

Also set Streamlit's app sharing controls for the intended company audience. The built-in login is a lightweight internal-app login with per-user roles, salted password hashes, and a short session-based delay after failed attempts. It is not enterprise SSO, MFA or a distributed brute-force protection service. Use private app sharing as an additional access boundary.

## 6. Your first save

1. Open **Edit & Save**.
2. Select **Edit existing issue**.
3. Choose the relevant partner/project/issue.
4. Enter severity, reviewed status, an accountable owner, dates or another needed change.
5. In the detail table, update the existing Effects, Solutions, partner/Special Ops responsibilities or Timing as needed. Scroll horizontally to see all action-tracking columns.
6. Optionally enter a reason for the change.
7. Click **Save changes to Dropbox**.
8. Wait for the green **Saved to Dropbox** message.
9. Open the workbook in Dropbox to see the changed partner-sheet cells. New tracking columns appear to the right of your existing columns. App saves are recorded in **Dashboard History**.

The app saves only on an explicit Save button. Filters, charts, logins and ordinary page interactions do not save anything.

At the first save for a partner sheet, the app adds tracking column headers on that sheet. Untouched issues remain blank/unassessed until reviewed. There is no separate migration you need to run.

## 7. What is written where

| Change in Streamlit | Destination in the same workbook |
| --- | --- |
| Project, Topic, Root cause, Problem, Notes | Original partner-sheet cells A:D and J for the selected issue |
| Effects, Solution, partner/Special Ops responsibility, Timing | Original partner-sheet cells E:I on their corresponding detail rows |
| Severity, Status, Accountable owner, Dates, Decisions, Success criterion | New tracking columns beside the original partner-sheet columns |
| Owner, Status, Due date, Completed date, Blocker for an existing Solution row | New action-tracking columns on that same detail row |
| Add issue | A new row appended to the selected partner sheet |
| Add action | A new row in **Dashboard Actions**, linked by partner/project/issue description |
| Any successful app save | **Dashboard History**, with timestamp, username, field, previous/new value and note |
| Overview | No changes |

The issue-level tracking columns are: Severity, Status, Responsible, Date identified, Target resolution, Decision needed, Decision owner, Decision due, Last updated, Success criterion, Resolution date and Root cause confidence.

The detail-row action columns are: Action owner, Action status, Action due, Action completed and Action blocker.

Additional actions go into a separate sheet to avoid inserting rows into your merged issue blocks or shifting existing Excel formulas. Both existing Solution rows and additional actions appear together in the dashboard's Actions tab and issue detail.

No user-facing issue ID is added. The app constructs an Issue label from **Topic — Problem** and links additional actions/history using **Partner + Project + Issue**. It rejects duplicate labels within the same partner/project. Internal source row locations are tied to the exact downloaded workbook revision, not stored as persistent issue IDs.

## 8. Editing and adding records

### Existing issue

Choose **Issue and existing actions**. The form edits the issue-level fields and its existing detail/action rows. Row count is fixed so merged blocks are not inadvertently deleted or rearranged.

If a detail field is merged in Excel, keep the repeated values identical across those rows. The app will reject conflicting values for the same merged cell.

A nonblank original Solution cell counts as an action. A row containing only an Effect is retained as context and does not count as a separate action. A solution containing several sentences still counts as one action; use Add action to track steps independently.

### Add an issue

Choose **Add issue**, then SPCL, SPOL or PM. Enter at least Project and Problem, and fill in the other fields as available. The new issue is appended after the existing formatted/merged area of that partner sheet. It appears in Streamlit immediately after a successful save. The old Excel Overview formulas are not expanded; the app overview includes it automatically.

### Add an action

Select an existing issue, then **Add action**. Enter the concrete action, owner, status, due date and blocker as applicable. Save. It appears in the same workbook's Dashboard Actions sheet.

### Closing and reopening

All tracked actions must be Done before an issue can close. Closure also requires a Success criterion and Resolution date. Use Monitoring when actions are complete but you are still checking the result.

To reopen, change Status from Closed and clear Resolution date. A Reopened event is added to history. Add new actions after reopening.

### Rename or reorganize an issue

Rename Project, Topic or Problem through the app. It updates linked Dashboard Actions and Dashboard History labels together. If you change those labels directly in Excel, you must update the linked labels yourself or the app will reject orphaned actions.

Use Excel for deleting whole issues or changing merged layout. This version intentionally has no issue-delete command. Before deleting an issue in Excel, remove/reassign its linked additional actions; retain history if needed. Avoid sorting individual rows inside a merged issue block.

## 9. How saves avoid lost updates

- Each session loads the workbook and its Dropbox revision together.
- The workbook remains a stable snapshot while you edit.
- Save first checks whether Dropbox still has that revision.
- The upload also uses a revision-conditional update, with strict conflict handling and no automatic renaming. This protects the small interval between the check and upload.
- If another person saved first, the app refuses to overwrite their newer workbook. It keeps your draft available as a download.
- If a network timeout occurs, the app checks the remote content hash to determine whether the save actually succeeded. If it cannot confirm, it blocks further saves until you reload and inspect history.

When a conflict occurs:

1. Download the unsaved draft if you need to retain your changes.
2. Click **Reload from Dropbox**.
3. Review the newer data and History.
4. Reapply your changes to that current version and save.

Do not upload the whole draft over the newer workbook merely to clear a conflict.

Dropbox is a shared workbook store, not simultaneous cell-level coauthoring. The app cannot prevent someone later overwriting the file from a stale desktop Excel copy. Finish saving/syncing Excel before editing through Streamlit, and reload Excel after app saves rather than continuing in an old open copy.

## 10. Refreshing and history

**Your own save:** the dashboard immediately displays the saved workbook and its returned Dropbox revision.

**Someone else's save or an Excel edit:** click **Reload from Dropbox**. There is no background polling that replaces a workbook while you edit. Reloading, changing issue selection or leaving the page can discard unsaved form input; submit one form at a time.

App history is automatic for successful app saves. Direct Excel edits are reflected in the next loaded workbook but do not create Dashboard History entries. The app cannot reconstruct older edits from before installation.

Last updated is set automatically for issues edited through the app. History timestamps are UTC. The reporting date and overdue calculations use TIMEZONE from Secrets, default America/Los_Angeles.

## 11. Dashboard views and definitions

- **Attention Now:** critical issues, overdue actions, blockers, decisions, unassigned owners, ranked queue and information gaps.
- **All Issues:** searchable register, expanded issue details and a filtered Excel report download.
- **Actions & Owners:** original solution rows plus additional actions, owner workloads, overdue actions and shared blockers.
- **Patterns & Causes:** issue age versus impact, project/topic heatmap and root causes.
- **Progress & History:** automatic app change history, new issues, newly overdue actions, monthly opened/resolved counts, monitoring and recorded reopenings.
- **Edit & Save:** the source editing forms. This selector includes all issues, independently of sidebar dashboard filters.

Unreviewed and Monitoring issues count as unresolved. Unassessed issues are shown prominently as needing review; they do not count as Critical until assessed. A Done action is never counted as overdue. Due today is not overdue. Existing free-text Timing does not create an overdue flag; enter a typed action due date.

Priority ordering uses severity, overdue action count, overdue resolution date, then issue age. There is no hidden weighted score. Unassessed issues sort after assessed issues and appear in the information-gap list.

An issue can appear in several headline counts, so do not add the counts together. Charts and history use current sidebar filters. Monthly resolution counts use resolution dates of currently Closed issues, not every historical close/reopen event. Workload counts actions, not estimated hours.

The filtered Excel export is a separate report. It does not replace or edit your original workbook.

## 12. Additional users

Run locally:

```bash
python configure.py --user-only
```

Enter a username, display name, role (`viewer` or `editor`) and a password. Copy the printed user configuration into Streamlit Secrets below the existing users. The printed configuration contains a password hash, not the plaintext password.

- Viewers can read and download; they cannot save.
- Editors can edit all partner issues in this dashboard.
- Access is not restricted by partner or project.
- All Dropbox API activity uses the one authorized Dropbox account. Dashboard History distinguishes the dashboard usernames.

To change a user's password, generate a new hash and replace that user's section. To revoke access, remove the user section. The app checks current roles on each run and again before saving; password changes invalidate that user's existing dashboard session at the next interaction.

## 13. If the shared link cannot resolve to an editable file

The Dropbox account used for authorization must have access to the original workbook, not merely a downloadable copy of someone else's shared link.

Under `[dropbox]` in Streamlit Secrets, you can specify its exact account-relative path:

```toml
file_path = "/Your actual folder/SpOps_ProjectCriticalPoints-Priorities.xlsx"
```

Replace the placeholder folder with the real folder. A Dropbox website URL is not a file path. Alternatively, use a known Dropbox `file_id`. The code prefers file_id, then file_path, then shared-link resolution. Do not guess a file ID.

For files in a team space, your Dropbox administrator may need to provide `root_namespace_id`; the code supports this optional setting. The setup uses a user token for the account with workbook access, not a team-admin token or broad team impersonation.

## 14. Workbook compatibility

Keep the three source sheet names and their original first ten columns, with headers in row 4. Do not move headers above/below that row. To support another partner sheet in the same layout later, add its name to `PARTNERS` in `workbook_model.py`.

Do not put unrelated operational data into the partner issue table below the header. Blank styled rows are ignored. Issues need a Project and a Problem.

The patching code preserves the standard workbook structures present in the supplied file, including merged cells and Overview formula text. openpyxl does not calculate formulas: Excel will recalculate the existing Overview formulas on opening the saved workbook. Dropbox's preview may show old or empty formula results until Excel recalculates. This does not affect Streamlit, which reads partner cells directly.

This .xlsx workflow is not intended for macros, slicers, embedded objects or advanced Excel features added later without compatibility testing. If you add such features, test preservation before using app writes. The supplied workbook had no charts or embedded images to preserve.

The maximum workbook size is 20 MB. The app rewrites the Excel file as one revision, while patching selected cells in memory. It does not do independent cell-level API writes.

## 15. Troubleshooting

| Message or symptom | Fix |
| --- | --- |
| Setup required | Add a real users section to Streamlit Secrets. |
| Username/password not recognized | Use the dashboard credentials, not your Dropbox credentials. Check the generated hash was copied intact. |
| Read-only connection | Add app_key, app_secret and refresh_token under `[dropbox]`. |
| Dropbox authorization failed | Verify app credentials, token and approved scopes. Re-run configure.py if authorization was revoked or scopes changed. |
| Cannot resolve shared workbook | Authorize the correct account; configure exact file_path if needed. |
| Unexpected filename | Target the original SpOps_ProjectCriticalPoints-Priorities.xlsx file. |
| No write permission | The authorized Dropbox account needs edit access, and the API app needs files.content.write. |
| Workbook changed/conflict | Download your draft, reload, and reapply changes. |
| Save outcome uncertain | Reload and check History. Do not repeatedly retry the same upload. |
| Cannot close issue | Complete pending actions, enter success criterion and resolution date. |
| Additional action has no matching issue | Repair partner/project/issue labels after a direct Excel rename, or use the app to rename. |
| Formula-containing cell cannot be edited | Edit that formula's source in Excel. The app will not silently replace a formula. |
| New records absent from Excel Overview | Expected: Streamlit creates the overview; the app does not extend the old Overview formulas. |
| Data looks old | Save/sync the workbook in Dropbox, then Reload from Dropbox. |
| Missing Python module | Upload all provided Python files beside streamlit_app.py and include requirements.txt. |

## 16. Local run and tests

From the extracted folder:

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

The local app reads `.streamlit/secrets.toml` generated by configure.py.

Offline tests:

```bash
python -m unittest test_dashboard.py -v
```

Tests cover merged-issue parsing, original cell/style/formula preservation, changing a specific detail row, literal-text handling, adding actions and issues, linked-label updates, closure/reopening checks, duplicate/date validation, password verification, revision conflicts and uncertain save outcomes.

Additional Streamlit tests were run against the supplied workbook locally: login gate, six-tab rendering, editing with a mocked Dropbox save, empty filters, the new-issue form and viewer restrictions. No test wrote to your actual Dropbox workbook. Your first live authenticated save still needs to be verified after deployment.

## 17. Official references

- Streamlit deployment: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- Streamlit Secrets: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- Dropbox OAuth and refresh tokens: https://docs.dropboxapi.com/dropbox-api/docs/oauth
- Dropbox upload endpoint: https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/files/upload
- Dropbox upload revision/conflict specification: https://github.com/dropbox/dropbox-api-spec/blob/main/files.stone
