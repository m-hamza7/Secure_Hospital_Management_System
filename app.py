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
)
from security import verify_password, get_fernet, encrypt_value


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
    st.subheader("Patient Records")
    try:
        rows = fetch_patients_for_role(role)
        if not rows:
            st.info("No patients found.")
            return
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
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
    pid = st.selectbox("Select Patient ID", ids)
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


# ----------------------------------------------------------------------------
# Main App Flow
# ----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Hospital Security Dashboard", layout="wide")
    st.title("🏥 Hospital Management (Security Focus)")
    st.caption("Demonstrating RBAC, Anonymization, Logging, and GDPR concepts.")

    # Sidebar
    with st.sidebar:
        st.header("Navigation")
        if st.session_state.auth_user:
            st.success(f"Logged in: {st.session_state.auth_user} ({st.session_state.role})")
            choice = st.selectbox(
                "Go to",
                options=_sidebar_options_for_role(st.session_state.role),
            )
            if st.button("Logout"):
                logout()
        else:
            choice = "Login"

    if not st.session_state.auth_user:
        show_login()
        footer()
        return

    # Role-based screens
    if choice == "Patient Records":
        view_patients()
        if st.session_state.role == "receptionist":
            add_patient_form()
            edit_patient_form()
        elif st.session_state.role == "admin":
            # Allow editing for admin as well
            add_patient_form()
            edit_patient_form()
    elif choice == "Anonymize Data" and st.session_state.role == "admin":
        anonymization_panel()
    elif choice == "Audit Logs" and st.session_state.role == "admin":
        logs_view()
    elif choice == "Backup / Export CSV" and st.session_state.role == "admin":
        export_backup()
    elif choice == "Login":
        show_login()
    else:
        st.info("Select a feature from the sidebar.")

    footer()


def _sidebar_options_for_role(role: str):
    base = ["Patient Records"]
    if role == "admin":
        base += ["Anonymize Data", "Audit Logs", "Backup / Export CSV"]
    return ["Login"] + base if st.session_state.auth_user is None else base


if __name__ == "__main__":
    main()
