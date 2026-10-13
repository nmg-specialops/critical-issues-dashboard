"""Partner critical issues: compact tables and explicit anonymous saves."""

from datetime import date
from hashlib import sha256
from html import escape

import requests
import streamlit as st

from partner_model import PARTNERS, FIELDS, DATES, read, save_issue, text
from workbook_store import (
    DropboxStore,
    StoreError,
    ConflictError,
    UnknownSaveError,
    DEFAULT_LINK,
    MAX_BYTES,
)


def setting(key, default=None):
    try:
        return st.secrets.get(key, default)
    except FileNotFoundError:
        return default


st.set_page_config(
    page_title="Special Ops - Partner Critical Issues",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1900px;
        padding: 2rem 1rem 3rem;
    }

    h1, h2, h3 {
        letter-spacing: -.025em;
    }

   .partner-table-wrap {
    overflow-x: auto;
    margin-left: 8px;
    width: calc(100% - 8px);
    margin-bottom: 24px;
}

    .partner-table {
        width: 100%;
        min-width: 1100px;
        border-collapse: collapse;
        table-layout: fixed;
        font-size: 13px;
    }

    .partner-table th,
    .partner-table td {
        padding: 6px;
        border: 1px solid #d9dfe3;
        text-align: left;
        vertical-align: top;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }

    .partner-table th {
        background: #edf1f3;
        color: #25343b;
    }

    .partner-table .project-row td {
        background: #e8eef0;
        color: #263c45;
        font-size: 15px;
        font-weight: 650;
    }

    /* Topic: slightly wider, with bold text. */
    .partner-table th:first-child {
        width: 105px;
        box-sizing: border-box;
    }

    .partner-table tbody tr:not(.project-row) td:first-child {
        font-weight: 700;
    }

    /* Identified and Target date */
    .partner-table th:nth-child(7),
    .partner-table th:nth-child(8) {
        width: 84px;
        box-sizing: border-box;
        padding: 4px;
        font-size: 12px;
    }

    .partner-table tbody tr:not(.project-row) td:nth-child(7),
    .partner-table tbody tr:not(.project-row) td:nth-child(8) {
        white-space: nowrap;
        overflow-wrap: normal;
        padding: 4px;
        font-size: 12px;
    }

    /* Status */
    .partner-table th:nth-child(10) {
        width: 80px;
        box-sizing: border-box;
    }

    /* Notes fit within the height set by the other cells. */
    .partner-table td.notes-column {
        position: relative;
    }

    .notes-cell {
        position: absolute;
        inset: 6px;
        overflow: hidden;
    }

    .notes-cell summary {
        cursor: pointer;
        display: block;
        height: 100%;
        box-sizing: border-box;
        padding-bottom: 16px;
        list-style: none;
        white-space: normal;
    }

    .notes-cell summary::-webkit-details-marker {
        display: none;
    }

    .notes-preview {
        display: block;
        height: 100%;
        overflow: hidden;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }

    .notes-cell summary::after {
        content: "▸";
        position: absolute;
        bottom: 0;
        right: 0;
        color: #246773;
    }

    .notes-cell[open] {
        position: static;
        overflow: visible;
    }

    .notes-cell[open] summary {
        height: 18px;
        padding: 0;
        position: relative;
    }

    .notes-cell[open] .notes-preview {
        display: none;
    }

    .notes-cell[open] summary::after {
        content: "▾";
    }

    .notes-full {
        margin-top: 6px;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }
    .partner-table thead th {
    vertical-align: middle;
    padding-top: 6px;
    padding-bottom: 6px;
    line-height: 1.4;
}
.partner-table thead th:nth-child(7),
.partner-table thead th:nth-child(8),
.partner-table tbody tr:not(.project-row) td:nth-child(7),
.partner-table tbody tr:not(.project-row) td:nth-child(8) {
    font-size: 13px;
}

.partner-table tbody tr:not(.project-row) td:nth-child(7),
.partner-table tbody tr:not(.project-row) td:nth-child(8) {
    letter-spacing: -0.25px;
}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Special Ops - Partner Critical Issues.")
st.caption(
    "One shared view of the problems, people and next steps "
    "for priority topics with partners across Special Ops."
)

config = dict(setting("dropbox", {}))
connected = all(
    config.get(key)
    for key in ["app_key", "app_secret", "refresh_token"]
)
store = DropboxStore(config) if connected else None

with st.sidebar:
    st.caption("SPCL · SPOL · PM")

    if st.button("Refresh from Dropbox"):
        st.session_state.pop("snapshot", None)
        st.session_state.pop("save_blocked", None)
        st.session_state.pop("pending_draft", None)

    st.caption(
        "Save before refreshing. "
        "Version: Compact table · Update last · 2026-10-13"
    )

if "snapshot" not in st.session_state:
    try:
        if store:
            st.session_state.snapshot = store.load()
        else:
            url = config.get("shared_link", DEFAULT_LINK)
            url = url.replace("dl=0", "dl=1")

            with requests.get(
                url,
                timeout=(10, 45),
                stream=True,
            ) as response:
                response.raise_for_status()
                chunks = []
                size = 0

                for chunk in response.iter_content(65536):
                    size += len(chunk)

                    if size > MAX_BYTES:
                        raise StoreError("Workbook exceeds 20 MB.")

                    chunks.append(chunk)

                st.session_state.snapshot = {
                    "bytes": b"".join(chunks),
                    "rev": "read-only",
                }

    except Exception as exc:
        st.error("Could not load the workbook. " + str(exc))
        st.stop()

snapshot = st.session_state.snapshot

try:
    records = read(snapshot["bytes"])
except Exception as exc:
    st.error("Could not read the workbook. " + str(exc))
    st.stop()

if st.session_state.get("saved_message"):
    st.success(st.session_state.pop("saved_message"))


def projects(items):
    return list(dict.fromkeys(item["Project"] for item in items))


def cell_html(field, value):
    value = escape(text(value))

    if field == "Notes" and value:
        return (
            '<details class="notes-cell">'
            '<summary title="Expand or collapse notes">'
            '<span class="notes-preview">'
            + value
            + "</span></summary>"
            '<div class="notes-full">'
            + value
            + "</div></details>"
        )

    return value


partner_colors = {
    "SPCL": "#A34336",  # Brick red
    "SPOL": "#2463A6",  # Blue
    "PM": "#4C9F86",    # Mint green
}

# Display labels only; workbook and editor names remain unchanged.
table_labels = {
    "Root cause": "Root Cause",
    "Date Identified": "Identified",
    "Targeted Resolution": "Target Date",
}

# Explicit order keeps Update as the final column.
columns = [
    "Topic",
    "Root cause",
    "Problem",
    "Effects",
    "Solutions",
    "Responsible",
    "Date Identified",
    "Targeted Resolution",
    "Notes",
    "Status",
    "Update",
]

mode = st.radio(
    "View",
    ["Table", "Cards"],
    horizontal=True,
    index=0,
    key="partner_view_20261012",
)

for partner, title in PARTNERS.items():
    items = [
        record
        for record in records
        if record["Partner"] == partner
    ]

    st.markdown(
        '<h2 style="color:'
        + partner_colors[partner]
        + ';">'
        + escape(title)
        + "</h2>",
        unsafe_allow_html=True,
    )

    if not items:
        st.caption("No issues listed yet.")
        continue

    if mode == "Table":
        header = "".join(
            '<th scope="col">'
            + escape(table_labels.get(field, field))
            + "</th>"
            for field in columns
        )
        body = []

        for project in projects(items):
            body.append(
                '<tr class="project-row"><td colspan="'
                + str(len(columns))
                + '">'
                + escape(project or "Other projects")
                + "</td></tr>"
            )

            for item in items:
                if item["Project"] != project:
                    continue

                cells = []

                for field in columns:
                    opening_tag = (
                        '<td class="notes-column">'
                        if field == "Notes"
                        else "<td>"
                    )
                    cells.append(
                        opening_tag
                        + cell_html(field, item[field])
                        + "</td>"
                    )

                body.append("<tr>" + "".join(cells) + "</tr>")

        table_html = (
            '<div class="partner-table-wrap">'
            '<table class="partner-table" aria-label="'
            + escape(title)
            + ' issues"><thead><tr>'
            + header
            + "</tr></thead><tbody>"
            + "".join(body)
            + "</tbody></table></div>"
        )

        st.markdown(table_html, unsafe_allow_html=True)

    else:
        for project in projects(items):
            st.subheader(project or "Other projects")

            for item in items:
                if item["Project"] != project:
                    continue

                summary = " ".join(item["Problem"].split())

                if len(summary) > 95:
                    summary = summary[:92] + "…"

                with st.expander(item["Topic"] + " | " + summary):
                    for field in columns:
                        if text(item[field]):
                            st.markdown("**" + field + "**")
                            st.text(item[field])

st.divider()
st.subheader("Edit issues")

if store is None:
    st.info(
        "Dropbox editing is not connected. Keep the existing "
        "Dropbox credentials in Streamlit Secrets to enable saving."
    )

else:
    st.caption(
        "Changes are saved only when you click Save Changes. "
        "App saves are recorded in the workbook’s Dashboard History "
        "as Anonymous editor."
    )

    partner = st.selectbox(
        "Partner",
        list(PARTNERS),
        format_func=lambda key: PARTNERS[key],
    )

    mode_edit = st.radio(
        "Choose",
        ["Edit existing issue", "Add issue"],
        horizontal=True,
    )

    candidates = [
        record
        for record in records
        if record["Partner"] == partner
    ]
    chosen = None

    if mode_edit == "Edit existing issue":
        if candidates:
            project = st.selectbox(
                "Project to edit",
                projects(candidates),
            )

            options = [
                record
                for record in candidates
                if record["Project"] == project
            ]

            index = st.selectbox(
                "Topic to edit",
                range(len(options)),
                format_func=lambda i: (
                    options[i]["Topic"]
                    + " — "
                    + options[i]["Problem"][:100]
                ),
            )

            chosen = options[index]

        else:
            st.info(
                "No issues for this partner. "
                "Select Add issue to create one."
            )

    if chosen is not None or mode_edit == "Add issue":
        current = chosen or {field: "" for field in FIELDS}
        source_row = chosen["SourceRow"] if chosen else None

        signature = (
            str(snapshot["rev"])
            + sha256(snapshot["bytes"]).hexdigest()
            + partner
            + str(source_row if chosen else "new")
        )
        key = sha256(signature.encode()).hexdigest()[:16]

        with st.form("issue_" + key):
            fields = {}
            left, right = st.columns(2)

            for index, field in enumerate(FIELDS):
                column = left if index % 2 == 0 else right

                with column:
                    if field in DATES:
                        try:
                            value = (
                                date.fromisoformat(current[field][:10])
                                if current[field]
                                else None
                            )
                        except ValueError:
                            value = None

                        if current[field] and value is None:
                            fields[field] = st.text_input(
                                field,
                                value=current[field],
                                help="Use YYYY-MM-DD to save a date.",
                            )
                        else:
                            fields[field] = st.date_input(
                                field,
                                value=value,
                                format="DD/MM/YYYY",
                                key=key + field,
                            )

                    elif field == "Status":
                        statuses = [
                            "",
                            "New",
                            "In Progress",
                            "Blocked",
                            "Monitoring",
                            "Closed",
                        ]

                        if current[field] not in statuses:
                            statuses.append(current[field])

                        fields[field] = st.selectbox(
                            field,
                            statuses,
                            index=statuses.index(current[field]),
                        )

                    elif field in ["Project", "Topic", "Responsible"]:
                        fields[field] = st.text_input(
                            field,
                            value=current[field],
                        )

                    else:
                        fields[field] = st.text_area(
                            field,
                            value=current[field],
                            height=90,
                        )

            submit = st.form_submit_button(
                "Save Changes",
                type="primary",
            )

        if submit:
            if st.session_state.get("save_blocked"):
                st.error(
                    "Refresh the workbook before another save. "
                    "Download your unsaved draft first."
                )

            else:
                try:
                    data = save_issue(
                        snapshot["bytes"],
                        partner,
                        source_row,
                        fields,
                    )

                    st.session_state.pending_draft = data
                    st.session_state.snapshot = store.save(
                        snapshot,
                        data,
                    )

                except (ConflictError, UnknownSaveError) as exc:
                    st.session_state.save_blocked = True
                    st.error(str(exc))

                except (ValueError, StoreError) as exc:
                    st.error(str(exc))

                except Exception:
                    st.session_state.save_blocked = True
                    st.error(
                        "Save could not be confirmed. Download your "
                        "draft, refresh, and check Dashboard History "
                        "before retrying."
                    )

                else:
                    st.session_state.pop("pending_draft", None)
                    st.session_state.saved_message = "Changes saved."
                    st.rerun()

    if "pending_draft" in st.session_state:
        st.download_button(
            "Download unsaved draft",
            st.session_state.pending_draft,
            "SpOps_unsaved_draft.xlsx",
        )
