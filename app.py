"""app.py
Streamlit Hospital Management System demonstrating Privacy, Trust and CIA triad.

Features:
- Login & Role-Based Access Control (Admin, Doctor, Receptionist)
- Patient management (add/edit) with role visibility restrictions
- Data anonymization (masking or optional encryption) for PII
- Audit logging of all actions (login, view, add, edit, anonymize, export)
- CSV backup export (Admin only) for availability
- Uptime & last action info in footer

Run: `streamlit run app.py`

Security / Privacy Highlights:
- Confidentiality: Restricted views; doctor sees anonymized data only.
- Integrity: Centralized CRUD & logging; parameterized SQL queries.
- Availability: Graceful error handling; CSV export; uptime display.
- GDPR: Privacy by design (separate anonymized columns), transparency (logs), data minimization (role-based column exposure), control (admin triggers anonymization).
"""

from __future__ import annotations
import time
from datetime import datetime, timedelta
import traceback
import streamlit as st
import pandas as pd

from db import (
    get_user_by_username,
    log_action,
    fetch_patients_for_role,
    add_patient,
    update_patient,
    anonymize_all_patients,
    list_logs,
    export_patients_csv,
    count_soft_deletes_older_than,
    purge_soft_deletes_older_than,
)
from security import verify_password, get_fernet, encrypt_value, is_encrypted


# ----------------------------------------------------------------------------
# Session & Uptime Initialization
# ----------------------------------------------------------------------------
if "app_start" not in st.session_state:
    st.session_state.app_start = time.time()
if "last_action_time" not in st.session_state:
    st.session_state.last_action_time = None
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None  # username
if "role" not in st.session_state:
    st.session_state.role = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "consent_given" not in st.session_state:
    st.session_state.consent_given = False
if "consent_declined" not in st.session_state:
    st.session_state.consent_declined = False


def mark_action():
    st.session_state.last_action_time = time.time()


# ----------------------------------------------------------------------------
# Utility UI Functions
# ----------------------------------------------------------------------------
def footer():
    uptime_seconds = int(time.time() - st.session_state.app_start)
    uptime = str(timedelta(seconds=uptime_seconds))
    last_act = (
        datetime.utcfromtimestamp(st.session_state.last_action_time).isoformat()
        if st.session_state.last_action_time
        else "N/A"
    )
    st.markdown(
        f"---\n**System Uptime:** {uptime} | **Last Action (UTC):** {last_act}"
    )


def secure_error_box(err: Exception):
    st.error("An error occurred; operation aborted to preserve integrity.")
    st.caption(str(err))


# GDPR Consent Banner
def show_consent_banner() -> None:
    """Display a consent banner to the user and record the choice in session_state.

    - Records `consent_given` or `consent_declined` in session_state.
    - Logs the choice using log_action (user_id/role may be None if not logged in).
    - If the user declines, the calling code may choose to block further interaction.
    """
    # If a choice was already made, do nothing
    if st.session_state.get("consent_given") or st.session_state.get("consent_declined"):
        return

    st.info("We use audit logging for actions (login, view, edit) and provide anonymization features.\nPlease provide your consent to proceed.")
    cols = st.columns([1, 1, 6])
    with cols[2]:
        st.write("By accepting you agree to in-app audit logging and anonymization processes for GDPR/compliance demos. You can decline to opt-out of the demo; declining will disable interactive features.")
    with cols[0]:
        if st.button("Accept", key="consent_accept"):
            st.session_state.consent_given = True
            st.session_state.consent_declined = False
            try:
                log_action(st.session_state.get("user_id"), st.session_state.get("role"), "consent_accepted", "user_accepted_consent")
            except Exception:
                # logging should not interrupt UX
                pass
            mark_action()
            st.rerun()
    with cols[1]:
        if st.button("Decline", key="consent_decline"):
            st.session_state.consent_given = False
            st.session_state.consent_declined = True
            try:
                log_action(st.session_state.get("user_id"), st.session_state.get("role"), "consent_declined", "user_declined_consent")
            except Exception:
                pass
            mark_action()
            st.rerun()


# ----------------------------------------------------------------------------
# Authentication Component
# ----------------------------------------------------------------------------
def show_login():
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        try:
            user_row = get_user_by_username(username)
            if not user_row:
                st.warning("Invalid credentials.")
                log_action(None, None, "login_failed", f"username={username}")
                return
            if verify_password(password, user_row["salt"], user_row["password_hash"]):
                st.session_state.auth_user = user_row["username"]
                st.session_state.role = user_row["role"]
                st.session_state.user_id = user_row["user_id"]
                log_action(user_row["user_id"], user_row["role"], "login", f"user={username}")
                mark_action()
                st.success(f"Logged in as {user_row['role']}")
                st.rerun()
            else:
                st.warning("Invalid credentials.")
                log_action(user_row["user_id"], user_row["role"], "login_failed", "bad_password")
        except Exception as e:
            secure_error_box(e)
            log_action(None, None, "login_error", traceback.format_exc())


def logout():
    log_action(st.session_state.user_id, st.session_state.role, "logout", "")
    st.session_state.auth_user = None
    st.session_state.role = None
    st.session_state.user_id = None
    mark_action()
    st.rerun()


# ----------------------------------------------------------------------------
# Patient Views & Management
# ----------------------------------------------------------------------------
def view_patients():
    role = st.session_state.role
    
    # Header with Add Patient button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Patient Records")
    with col2:
        if role in ("admin", "receptionist"):
            if st.button("➕ Add New Patient", use_container_width=True, key="add_patient_btn"):
                st.session_state["show_add_patient_form"] = True
                st.rerun()
    
    # Admin toggle for dual view
    show_dual_view = False
    if role == "admin":
        show_dual_view = st.toggle("🔍 Show Dual View (Original + Anonymized)", value=False, key="dual_view_toggle")
    
    # Show add patient form if button was clicked
    if st.session_state.get("show_add_patient_form", False):
        with st.expander("📝 Add New Patient", expanded=True):
            with st.form("add_patient_inline"):
                new_name = st.text_input("👤 Full Name", key="add_name")
                new_contact = st.text_input("📞 Contact", key="add_contact")
                new_diagnosis = st.text_input("🏥 Diagnosis", key="add_diagnosis")
                
                form_cols = st.columns([1, 1])
                with form_cols[0]:
                    submitted = st.form_submit_button("💾 Add Patient", use_container_width=True)
                with form_cols[1]:
                    cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
            
            if cancel:
                st.session_state["show_add_patient_form"] = False
                st.rerun()
            
            if submitted:
                if not (new_name and new_contact and new_diagnosis):
                    st.warning("All fields are required.")
                else:
                    if add_patient(new_name, new_contact, new_diagnosis):
                        st.success("✅ Patient added successfully!")
                        log_action(st.session_state.user_id, role, "add_patient", new_name)
                        mark_action()
                        st.session_state["show_add_patient_form"] = False
                        st.rerun()
                    else:
                        st.error("Failed to add patient.")
                        log_action(st.session_state.user_id, role, "add_patient_fail", new_name)
        st.markdown("---")
    
    try:
        rows = fetch_patients_for_role(role)
        if not rows:
            st.info("No patients found.")
            return
        
        # Render patients as stacked cards (vertical layout)
        for r in rows:            # Create a container for the entire card with buttons
            with st.container():
                # Use columns: main content on left, buttons on right
                if role in ("admin", "receptionist"):
                    card_col, btn_col = st.columns([4, 1])
                else:
                    card_col = st.columns(1)[0]
                    btn_col = None
                
                with card_col:
                    # Card HTML with professional styling
                    # For admin dual view: show both original and anonymized side by side
                    if role == "admin" and show_dual_view:
                        # Check if values are encrypted and display accordingly
                        anon_name_display = r.get('anonymized_name') or 'Not Anonymized'
                        anon_contact_display = r.get('anonymized_contact') or 'Not Anonymized'
                        
                        # Replace encrypted values with "🔒 Encrypted" for display
                        if anon_name_display != 'Not Anonymized' and is_encrypted(anon_name_display):
                            anon_name_display = '🔒 Encrypted'
                        if anon_contact_display != 'Not Anonymized' and is_encrypted(anon_contact_display):
                            anon_contact_display = '🔒 Encrypted'
                        
                        card_html = f"""
                        <div class="patient-card">
                            <div class="patient-card-header">
                                <span class="patient-id">ID: {r['patient_id']}</span>
                                <span class="dual-view-badge">🔍 DUAL VIEW MODE</span>
                            </div>
                            <div class="dual-view-container">
                                <div class="dual-view-column">
                                    <div class="dual-view-title">📋 Original Data</div>
                                    <div class="patient-info">
                                        <div class="info-label">👤 Patient Name</div>
                                        <div class="info-value">{r.get('name') or 'N/A'}</div>
                                    </div>
                                    <div class="patient-info">
                                        <div class="info-label">📞 Contact</div>
                                        <div class="info-value">{r.get('contact') or 'N/A'}</div>
                                    </div>
                                    <div class="patient-info">
                                        <div class="info-label">🏥 Diagnosis</div>
                                        <div class="info-value">{r.get('diagnosis') or 'N/A'}</div>
                                    </div>
                                </div>
                                <div class="dual-view-divider"></div>
                                <div class="dual-view-column">
                                    <div class="dual-view-title">🔒 Anonymized/Masked Data</div>
                                    <div class="patient-info">
                                        <div class="info-label">👤 Anonymized Name</div>
                                        <div class="info-value anonymized">{anon_name_display}</div>
                                    </div>
                                    <div class="patient-info">
                                        <div class="info-label">📞 Anonymized Contact</div>
                                        <div class="info-value anonymized">{anon_contact_display}</div>
                                    </div>
                                    <div class="patient-info">
                                        <div class="info-label">🏥 Diagnosis</div>
                                        <div class="info-value">{r.get('diagnosis') or 'N/A'}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        """
                    else:
                        # Standard single view
                        # Check if values are encrypted and display accordingly
                        name_display = r.get('name') or 'N/A'
                        contact_display = r.get('contact') or 'N/A'
                        
                        # For non-admin roles, the name/contact might already be anonymized
                        # Replace encrypted values with "🔒 Encrypted"
                        if name_display != 'N/A' and is_encrypted(name_display):
                            name_display = '🔒 Encrypted'
                        if contact_display != 'N/A' and is_encrypted(contact_display):
                            contact_display = '🔒 Encrypted'
                        
                        card_html = f"""
                        <div class="patient-card">
                            <div class="patient-card-header">
                                <span class="patient-id">ID: {r['patient_id']}</span>
                            </div>
                            <div class="patient-info">
                                <div class="info-label">👤 Patient Name</div>
                                <div class="info-value">{name_display}</div>
                            </div>
                            <div class="patient-info">
                                <div class="info-label">📞 Contact</div>
                                <div class="info-value">{contact_display}</div>
                            </div>
                            <div class="patient-info">
                                <div class="info-label">🏥 Diagnosis</div>
                                <div class="info-value">{r.get('diagnosis') or 'N/A'}</div>
                            </div>
                        </div>
                        """
                    st.markdown(card_html, unsafe_allow_html=True)

                # Action buttons on the right side
                if role in ("admin", "receptionist") and btn_col is not None:
                    with btn_col:
                        edit_key = f"edit_btn_{r['patient_id']}"
                        delete_key = f"del_btn_{r['patient_id']}"

                        # Edit button
                        if st.button("✏️ Edit", key=edit_key, use_container_width=True):
                            st.session_state[f"edit_mode_{r['patient_id']}"] = True
                            st.rerun()                        # Only admin shows soft-delete
                        if role == "admin":
                            if st.button("🗑️ Delete", key=delete_key, use_container_width=True):
                                try:
                                    from db import soft_delete_patient
                                    if soft_delete_patient(r['patient_id']):
                                        st.success(f"Patient {r['patient_id']} marked as deleted.")
                                        log_action(st.session_state.user_id, role, "soft_delete", f"pid={r['patient_id']}")
                                        mark_action()
                                        st.rerun()
                                    else:
                                        st.error("Failed to soft-delete patient.")
                                except Exception as e:
                                    secure_error_box(e)
                                    log_action(st.session_state.user_id, role, "soft_delete_error", traceback.format_exc())

            # Inline edit form (shown when edit_mode flag set)
            edit_flag = st.session_state.get(f"edit_mode_{r['patient_id']}", False)
            if edit_flag:
                st.markdown("---")
                st.markdown("#### 📝 Edit Patient Information")
                with st.form(f"edit_form_{r['patient_id']}"):
                    new_name = st.text_input("👤 Name", value=r.get('name') or "", key=f"name_in_{r['patient_id']}")
                    new_contact = st.text_input("📞 Contact", value=r.get('contact') or "", key=f"contact_in_{r['patient_id']}")
                    new_diag = st.text_input("🏥 Diagnosis", value=r.get('diagnosis') or "", key=f"diag_in_{r['patient_id']}")
                    
                    form_cols = st.columns([1, 1])
                    with form_cols[0]:
                        submitted = st.form_submit_button("💾 Save Changes", use_container_width=True)
                    with form_cols[1]:
                        cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
                        
                if cancel:
                    st.session_state[f"edit_mode_{r['patient_id']}"] = False
                    st.rerun()
                    
                if submitted:
                    # Only call update if at least one change provided
                    if not any([new_name, new_contact, new_diag]):
                        st.warning("Provide at least one field to update.")
                    else:
                        try:
                            if update_patient(r['patient_id'], name=new_name or None, contact=new_contact or None, diagnosis=new_diag or None):
                                st.success("✅ Patient updated successfully!")
                                log_action(st.session_state.user_id, role, "edit_patient", f"pid={r['patient_id']}")
                                mark_action()
                                # clear edit flag and rerun to refresh view
                                st.session_state[f"edit_mode_{r['patient_id']}"] = False
                                st.rerun()
                            else:
                                st.error("Update failed.")
                                log_action(st.session_state.user_id, role, "edit_patient_fail", f"pid={r['patient_id']}")
                        except Exception as e:
                            secure_error_box(e)
                            log_action(st.session_state.user_id, role, "edit_patient_error", traceback.format_exc())

        # Log view action once after rendering
        log_action(st.session_state.user_id, role, "view_patients", f"count={len(rows)}")
        mark_action()
    except Exception as e:
        secure_error_box(e)
        log_action(st.session_state.user_id, role, "view_patients_error", traceback.format_exc())


def add_patient_form():
    st.markdown("### Add Patient")
    with st.form("add_patient"):
        name = st.text_input("Full Name")
        contact = st.text_input("Contact")
        diagnosis = st.text_input("Diagnosis")
        submitted = st.form_submit_button("Add")
    if submitted:
        if not (name and contact and diagnosis):
            st.warning("All fields required.")
            return
        if add_patient(name, contact, diagnosis):
            st.success("Patient added.")
            log_action(st.session_state.user_id, st.session_state.role, "add_patient", name)
            mark_action()
            st.rerun()
        else:
            st.error("Failed to add patient.")
            log_action(st.session_state.user_id, st.session_state.role, "add_patient_fail", name)


def edit_patient_form():
    st.markdown("### Edit Patient")
    role = st.session_state.role
    rows = fetch_patients_for_role(role)
    if not rows:
        st.info("No patients to edit.")
        return
    # Use raw patient_id list
    ids = [r["patient_id"] for r in rows]
    pid = st.selectbox("Select Patient ID", ids, key="edit_patient_pid")
    # Fields optional; blank means ignore update
    new_name = st.text_input("New Name (optional)")
    new_contact = st.text_input("New Contact (optional)")
    new_diag = st.text_input("New Diagnosis (optional)")
    if st.button("Update Patient"):
        if not any([new_name, new_contact, new_diag]):
            st.warning("Provide at least one field to update.")
            return
        if update_patient(pid, name=new_name or None, contact=new_contact or None, diagnosis=new_diag or None):
            st.success("Updated.")
            log_action(st.session_state.user_id, role, "edit_patient", f"pid={pid}")
            mark_action()
            st.rerun()
        else:
            st.error("Update failed.")
            log_action(st.session_state.user_id, role, "edit_patient_fail", f"pid={pid}")


# ----------------------------------------------------------------------------
# Anonymization & Logs
# ----------------------------------------------------------------------------
def anonymization_panel():
    st.subheader("Data Anonymization")
    st.caption("Mask names & contacts or encrypt them (if cryptography installed).")
    use_encryption = st.checkbox("Use Fernet Encryption (reversible)")
    if st.button("Run Anonymization"):
        try:
            count = anonymize_all_patients(use_encryption=use_encryption)
            st.success(f"Anonymization complete. {count} patient(s) updated.")
            log_action(st.session_state.user_id, st.session_state.role, "anonymize", f"count={count}; encrypted={use_encryption}")
            mark_action()
            st.rerun()
        except Exception as e:
            secure_error_box(e)
            log_action(st.session_state.user_id, st.session_state.role, "anonymize_error", traceback.format_exc())


def logs_view():
    st.subheader("Audit Logs")
    try:
        data = list_logs(limit=500)
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No logs yet.")
        log_action(st.session_state.user_id, st.session_state.role, "view_logs", f"count={len(data)}")
        mark_action()
    except Exception as e:
        secure_error_box(e)
        log_action(st.session_state.user_id, st.session_state.role, "view_logs_error", traceback.format_exc())


# New: Admin activity graphs panel
def activity_panel():
    """Show real-time activity graphs for admin users.

    - Actions per day (line chart)
    - Actions per role (bar chart for last 30 days)
    - Per-user counts for current day (hourly range 00:00 to now)
    """
    st.subheader("Real-time Activity")
    try:
        data = list_logs(limit=5000)
        if not data:
            st.info("No activity logged yet.")
            return
        df = pd.DataFrame(data)
        # parse timestamps reliably and force UTC
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"])  # remove malformed rows
        if df.empty:
            st.info("No valid timestamps in logs to plot.")
            st.dataframe(pd.DataFrame(data).head(20))
            return        # quick summary
        st.caption(f"Total log rows: {len(df)}")
        if st.checkbox("Show raw recent logs", value=False):
            st.dataframe(df.sort_values("timestamp", ascending=False).head(200), use_container_width=True)

        agg_choice = st.radio("📊 Select View", ["Actions per day", "Actions per role (last 30 days)", "Per-user today"], horizontal=True) 

        if agg_choice == "Actions per day":
            # group by date (date-only labels) so chart shows days instead of UTC midnight timestamps
            df["date"] = df["timestamp"].dt.date
            daily = df.groupby("date").size().reset_index(name="count").sort_values("date")
            if daily.empty:
                st.info("No actions to display per day.")
            else:
                # convert date to datetime index for nicer plotting
                daily["date"] = pd.to_datetime(daily["date"])
                daily = daily.set_index("date")
                st.line_chart(daily["count"])
        elif agg_choice == "Per-user today":
            # compute start of current day in UTC (use tz-aware now)
            now_utc = pd.Timestamp.now(tz='UTC')
            start_of_day_utc = now_utc.normalize()  # midnight UTC today
            # filter logs between midnight UTC and now
            today = df[(df["timestamp"] >= start_of_day_utc) & (df["timestamp"] <= now_utc)]
            if today.empty:
                st.info("No activity today.")
            else:
                # map user_id to username for display
                from db import get_username_by_id
                today["username"] = today["user_id"].apply(lambda uid: get_username_by_id(uid) or f"user_{uid}")
                counts = today.groupby("username").size().reset_index(name="count").sort_values("count", ascending=False)
                st.bar_chart(counts.set_index("username")["count"])
        else:
            since = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=30)
            recent = df[df["timestamp"] >= since]
            if recent.empty:
                st.info("No activity in the last 30 days.")
            else:
                by_role = recent.groupby("role").size().reset_index(name="count").sort_values("count", ascending=False)
                st.bar_chart(by_role.set_index("role")["count"])

        st.markdown("---")
        st.caption("Recent raw logs (latest 200)")
        st.dataframe(df.sort_values("timestamp", ascending=False).head(200), use_container_width=True)

        log_action(st.session_state.user_id, st.session_state.role, "view_activity", f"rows={len(df)}")
        mark_action()
    except Exception as e:
        secure_error_box(e)
        log_action(st.session_state.user_id, st.session_state.role, "view_activity_error", traceback.format_exc())


def export_backup():
    st.subheader("Backup / Export")
    if st.button("Export Patients CSV"):
        try:
            if export_patients_csv():
                st.success("Exported to patients_export.csv")
                log_action(st.session_state.user_id, st.session_state.role, "export_csv", "patients_export.csv")
            else:
                st.error("Export failed.")
                log_action(st.session_state.user_id, st.session_state.role, "export_csv_fail", "")
            mark_action()
        except Exception as e:
            secure_error_box(e)
            log_action(st.session_state.user_id, st.session_state.role, "export_csv_error", traceback.format_exc())


def deleted_management_panel():
    st.subheader("Deleted Patients (Soft-deleted)")
    try:
        from db import list_deleted_patients, recover_patient, permanently_delete_patient

        rows = list_deleted_patients()
        if not rows:
            st.info("No soft-deleted patients.")
            return
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

        ids = [r["patient_id"] for r in rows]
        pid = st.selectbox("Select deleted Patient ID", ids, key="deleted_patient_pid")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Recover Patient"):
                if recover_patient(pid):
                    st.success("Patient recovered (soft-delete removed).")
                    log_action(st.session_state.user_id, st.session_state.role, "recover_patient", f"pid={pid}")
                    mark_action()
                    st.rerun()
                else:
                    st.error("Failed to recover patient.")
        with col2:
            if st.checkbox("Confirm permanent delete"):
                if st.button("Permanently Delete"):
                    if permanently_delete_patient(pid):
                        st.success("Patient permanently deleted from database.")
                        log_action(st.session_state.user_id, st.session_state.role, "permanent_delete", f"pid={pid}")
                        mark_action()
                        st.rerun()
                    else:
                        st.error("Permanent delete failed.")
    except Exception as e:
        secure_error_box(e)
        log_action(st.session_state.user_id, st.session_state.role, "deleted_mgmt_error", traceback.format_exc())


# New admin scheduled purge panel
def scheduled_purge_panel():
    st.subheader("Scheduled Purge (Admin)")
    try:
        days = st.number_input("Permanently delete soft-deletes older than (days)", min_value=1, value=30)
        if st.button("Preview purge count"):
            n = count_soft_deletes_older_than(int(days))
            st.info(f"{n} soft-deleted patient(s) older than {days} days would be permanently removed.")
        st.caption("This action is irreversible. It will permanently delete rows from the DB.")
        if st.checkbox("Confirm purge"):
            if st.button("Run Purge Now"):
                removed = purge_soft_deletes_older_than(int(days))
                if removed > 0:
                    st.success(f"Permanently removed {removed} patient(s).")
                    log_action(st.session_state.user_id, st.session_state.role, "scheduled_purge", f"removed={removed}; days={days}")
                    mark_action()
                    st.rerun()
                else:
                    st.info("No rows matched the purge criteria or purge failed.")
    except Exception as e:
        secure_error_box(e)
        log_action(st.session_state.user_id, st.session_state.role, "scheduled_purge_error", traceback.format_exc())


# ----------------------------------------------------------------------------
# Main App Flow
# ----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Hospital Security Dashboard", layout="wide")
    
    # Apply global CSS theme to entire website
    st.markdown("""
        <style>
        /* Global theme styling */
        .stApp {
            background: linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
        }
        
        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
            border-right: 2px solid #d4af37;
        }
        
        [data-testid="stSidebar"] h1, 
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] label {
            color: #d4af37 !important;
        }
        
        [data-testid="stSidebar"] p {
            color: #e8e8e8 !important;
        }
        
        /* Main content area */
        .main .block-container {
            background: transparent;
            padding-top: 2rem;
        }
        
        /* Headers */
        h1, h2, h3, h4, h5, h6 {
            color: #d4af37 !important;
            font-weight: 600;
        }
        
        /* Regular text */
        p, span, div {
            color: #e8e8e8;
        }
        
        /* Input fields */
        .stTextInput input,
        .stNumberInput input,
        .stSelectbox select {
            background-color: #16213e !important;
            color: #ffffff !important;
            border: 1px solid #d4af37 !important;
            border-radius: 8px;
        }
        
        .stTextInput input:focus,
        .stNumberInput input:focus,
        .stSelectbox select:focus {
            border-color: #d4af37 !important;
            box-shadow: 0 0 10px rgba(212, 175, 55, 0.3) !important;
        }
        
        /* Labels */
        label {
            color: #d4af37 !important;
        }
        
        /* Buttons */
        .stButton button {
            background: linear-gradient(135deg, #d4af37 0%, #c4941f 100%) !important;
            color: #1a1a2e !important;
            border: none !important;
            border-radius: 8px;
            font-weight: 600;
            padding: 0.5rem 1.5rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(212, 175, 55, 0.3);
        }
        
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(212, 175, 55, 0.4);
        }
        
        /* Form submit buttons */
        .stFormSubmitButton button {
            background: linear-gradient(135deg, #d4af37 0%, #c4941f 100%) !important;
            color: #1a1a2e !important;
            border: none !important;
            font-weight: 600;
        }
        
        /* Info, Success, Warning, Error boxes */
        .stInfo {
            background-color: rgba(22, 33, 62, 0.8) !important;
            border-left: 4px solid #3b82f6 !important;
            color: #e8e8e8 !important;
        }
        
        .stSuccess {
            background-color: rgba(22, 33, 62, 0.8) !important;
            border-left: 4px solid #10b981 !important;
            color: #e8e8e8 !important;
        }
        
        .stWarning {
            background-color: rgba(22, 33, 62, 0.8) !important;
            border-left: 4px solid #f59e0b !important;
            color: #e8e8e8 !important;
        }
        
        .stError {
            background-color: rgba(22, 33, 62, 0.8) !important;
            border-left: 4px solid #ef4444 !important;
            color: #e8e8e8 !important;
        }
        
        /* Dataframes */
        .stDataFrame {
            background-color: #16213e !important;
            border: 1px solid #d4af37 !important;
            border-radius: 10px;
        }
        
        /* Checkboxes */
        .stCheckbox label {
            color: #e8e8e8 !important;
        }
        
        /* Captions */
        .caption {
            color: #d4af37 !important;
            opacity: 0.8;
        }
        
        /* Dividers */
        hr {
            border-color: rgba(212, 175, 55, 0.3) !important;
        }
        
        /* Patient cards */
        .patient-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 1.5rem;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            margin-bottom: 1.5rem;
            border-left: 5px solid #d4af37;
            border-top: 1px solid rgba(212, 175, 55, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .patient-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.4), 0 0 20px rgba(212, 175, 55, 0.1);
        }
        
        .patient-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid rgba(255,255,255,0.2);
        }
        
        .patient-card-wrapper {
            display: flex;
            gap: 1.5rem;
            align-items: stretch;
        }
        
        .patient-card-content {
            flex: 1;
        }
        
        .patient-card-actions {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            justify-content: center;
            min-width: 120px;
        }
        
        .patient-id {
            background: linear-gradient(135deg, #d4af37 0%, #c4941f 100%);
            color: #1a1a2e;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 8px rgba(212, 175, 55, 0.3);
        }
        
        .patient-info {
            color: #e8e8e8;
            margin: 0.8rem 0;
        }
        
        .info-label {
            font-size: 0.75rem;
            opacity: 0.7;
            color: #d4af37;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.2rem;
            font-weight: 600;
        }
        
        .info-value {
            font-size: 1rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
            color: #ffffff;
        }
          .role-badge {
            background: #10b981;
            color: white;
            padding: 0.2rem 0.6rem;
            border-radius: 12px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        /* Dual view badge */
        .dual-view-badge {
            background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
            color: white;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 8px rgba(139, 92, 246, 0.3);
        }
        
        /* Dual view container */
        .dual-view-container {
            display: flex;
            gap: 2rem;
            margin-top: 1rem;
        }
        
        .dual-view-column {
            flex: 1;
            padding: 1rem;
            background: rgba(26, 26, 46, 0.5);
            border-radius: 10px;
            border: 1px solid rgba(212, 175, 55, 0.2);
        }
        
        .dual-view-title {
            font-size: 1rem;
            font-weight: 700;
            color: #d4af37;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid rgba(212, 175, 55, 0.3);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
          .dual-view-divider {
            width: 2px;
            background: linear-gradient(180deg, transparent 0%, #d4af37 50%, transparent 100%);
            margin: 0 0.5rem;
        }
        
        /* Anonymized data styling */
        .info-value.anonymized {
            color: #8b5cf6;
            font-family: 'Courier New', monospace;
            font-weight: 600;
            letter-spacing: 1px;
        }
        
        /* Top Navigation Tabs Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 1rem;
            border-radius: 15px;
            border: 2px solid #d4af37;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }
        
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
            border: 1px solid rgba(212, 175, 55, 0.3);
            border-radius: 10px;
            color: #d4af37;
            font-weight: 600;
            padding: 0 24px;
            transition: all 0.3s ease;
        }
        
        .stTabs [data-baseweb="tab"]:hover {
            background: linear-gradient(135deg, #d4af37 0%, #c4941f 100%);
            color: #1a1a2e;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(212, 175, 55, 0.4);
        }
        
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #d4af37 0%, #c4941f 100%) !important;
            color: #1a1a2e !important;
            border: 1px solid #d4af37 !important;
            box-shadow: 0 4px 16px rgba(212, 175, 55, 0.5);
        }
        
        .stTabs [data-baseweb="tab-panel"] {
            padding-top: 2rem;        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("🏥 Hospital Management (Security Focus)")
    st.caption("Demonstrating RBAC, Anonymization, Logging, and GDPR concepts.")
    
    # Show consent banner early; if declined, block interaction
    show_consent_banner()
    if st.session_state.get("consent_declined"):
        st.warning("You declined consent for audit logging/anonymization. The demo is disabled. Contact an administrator to proceed.")
        footer()
        return

    # Check if user is authenticated
    if not st.session_state.auth_user:
        show_login()
        footer()
        return

    # Sidebar - User info and logout only
    with st.sidebar:
        st.header("User Profile")
        st.success(f"👤 **{st.session_state.auth_user}**")
        st.info(f"🔐 Role: **{st.session_state.role.upper()}**")
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            logout()

    # Top Navigation Bar with Tabs
    st.markdown("---")
    
    # Create tabs based on role
    tab_options = _sidebar_options_for_role(st.session_state.role)
    tabs = st.tabs(tab_options)
      # Map each tab to its content
    for idx, tab_name in enumerate(tab_options):
        with tabs[idx]:
            if tab_name == "Patient Records":
                view_patients()
            elif tab_name == "Anonymize Data" and st.session_state.role == "admin":
                anonymization_panel()
            elif tab_name == "Audit Logs" and st.session_state.role == "admin":
                logs_view()
            elif tab_name == "Activity Graphs" and st.session_state.role == "admin":
                activity_panel()
            elif tab_name == "Manage Deleted" and st.session_state.role == "admin":
                deleted_management_panel()
            elif tab_name == "Scheduled Purge" and st.session_state.role == "admin":
                scheduled_purge_panel()
            elif tab_name == "Backup / Export CSV" and st.session_state.role == "admin":
                export_backup()


    footer()


def _sidebar_options_for_role(role: str):
    base = ["Patient Records"]
    if role == "admin":
        base += ["Anonymize Data", "Audit Logs", "Backup / Export CSV", "Activity Graphs", "Manage Deleted", "Scheduled Purge"]
    return ["Login"] + base if st.session_state.auth_user is None else base


if __name__ == "__main__":
    main()
