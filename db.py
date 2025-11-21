"""db.py
Database layer for the Hospital Management System.

Responsibilities:
- Initialize SQLite database and create tables.
- Insert sample users & patients (first run only).
- Provide CRUD operations for users & patients.
- Provide logging utilities (audit trail) for integrity & transparency.
- Provide anonymization routine (masking or optional encryption) updating dedicated columns.

Tables:
users(user_id PK, username UNIQUE, password_hash, salt, role)
patients(patient_id PK, name, contact, diagnosis, anonymized_name, anonymized_contact, date_added)
logs(log_id PK, user_id, role, action, timestamp, details)

NOTE: All SQL uses parameterized queries to mitigate injection.
"""

from __future__ import annotations
import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from security import generate_salt, hash_password, anonymize_fields

DB_FILE = "database.db"


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row factory as dict-like objects."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if absent and insert sample data.

    This function is idempotent; sample data added only if users table empty.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Create tables
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            diagnosis TEXT NOT NULL,
            anonymized_name TEXT,
            anonymized_contact TEXT,
            date_added TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
    )

    # Sample users if empty
    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        sample_users = [
            ("admin", "admin123", "admin"),
            ("doctor", "doctor123", "doctor"),
            ("reception", "recep123", "receptionist"),
        ]
        for username, pwd, role in sample_users:
            salt = generate_salt()
            pwd_hash = hash_password(pwd, salt)
            cur.execute(
                "INSERT INTO users(username, password_hash, salt, role) VALUES(?,?,?,?)",
                (username, pwd_hash, salt, role),
            )

    # Sample patients if empty
    cur.execute("SELECT COUNT(*) AS c FROM patients")
    if cur.fetchone()["c"] == 0:
        now = datetime.utcnow().isoformat()
        sample_patients = [
            ("Alice Carter", "555-123-1111", "Flu"),
            ("Bob Stone", "555-222-2222", "Fracture"),
            ("Charlie Vega", "555-333-3333", "Checkup"),
        ]
        for name, contact, diag in sample_patients:
            cur.execute(
                """
                INSERT INTO patients(name, contact, diagnosis, anonymized_name, anonymized_contact, date_added)
                VALUES(?,?,?,?,?,?)
                """,
                (name, contact, diag, None, None, now),
            )

    conn.commit()
    conn.close()


def create_user(username: str, password_plain: str, role: str) -> bool:
    """Create a new user; returns success status."""
    try:
        salt = generate_salt()
        pwd_hash = hash_password(password_plain, salt)
        conn = get_connection()
        conn.execute(
            "INSERT INTO users(username, password_hash, salt, role) VALUES(?,?,?,?)",
            (username, pwd_hash, salt, role),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def log_action(user_id: Optional[int], role: Optional[str], action: str, details: str = "") -> None:
    conn = get_connection()
    ts = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO logs(user_id, role, action, timestamp, details) VALUES(?,?,?,?,?)",
        (user_id, role, action, ts, details),
    )
    conn.commit()
    conn.close()


def list_logs(limit: int = 200) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT log_id, user_id, role, action, timestamp, details FROM logs ORDER BY log_id DESC LIMIT ?",
        (limit,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_patient(name: str, contact: str, diagnosis: str) -> bool:
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO patients(name, contact, diagnosis, anonymized_name, anonymized_contact, date_added)
            VALUES(?,?,?,?,?,?)
            """,
            (name, contact, diagnosis, None, None, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def update_patient(patient_id: int, name: Optional[str] = None, contact: Optional[str] = None, diagnosis: Optional[str] = None) -> bool:
    fields = []
    params: List[Any] = []
    if name is not None:
        fields.append("name = ?")
        params.append(name)
    if contact is not None:
        fields.append("contact = ?")
        params.append(contact)
    if diagnosis is not None:
        fields.append("diagnosis = ?")
        params.append(diagnosis)
    if not fields:
        return False
    params.append(patient_id)
    sql = f"UPDATE patients SET {', '.join(fields)} WHERE patient_id = ?"
    try:
        conn = get_connection()
        conn.execute(sql, params)
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def fetch_patients_for_role(role: str) -> List[Dict[str, Any]]:
    """Return patient rows filtered by role visibility.

    Role visibility rules:
    - admin: sees all raw + anonymized columns
    - doctor: sees anonymized_name/contact (only anonymized data) + diagnosis + date
    - receptionist: sees patient_id, name (raw for editing forms) but contact hidden in listing; diagnosis
    """
    conn = get_connection()
    cur = conn.cursor()
    if role == "admin":
        cur.execute(
            "SELECT patient_id, name, contact, diagnosis, anonymized_name, anonymized_contact, date_added FROM patients ORDER BY patient_id DESC"
        )
    elif role == "doctor":
        cur.execute(
            "SELECT patient_id, anonymized_name AS name, anonymized_contact AS contact, diagnosis, date_added FROM patients ORDER BY patient_id DESC"
        )
    elif role == "receptionist":
        # Provide limited raw view (no contact displayed) for editing purpose name shown
        cur.execute(
            "SELECT patient_id, name, NULL AS contact, diagnosis, date_added FROM patients ORDER BY patient_id DESC"
        )
    else:
        cur.execute(
            "SELECT patient_id, anonymized_name AS name, anonymized_contact AS contact, diagnosis, date_added FROM patients ORDER BY patient_id DESC"
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def anonymize_all_patients(use_encryption: bool = False) -> int:
    """Anonymize name/contact for all patients that lack anonymized values.
    Returns count of rows updated.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT patient_id, name, contact FROM patients")
    rows = cur.fetchall()
    updated = 0
    for r in rows:
        pid = r["patient_id"]
        name = r["name"]
        contact = r["contact"]
        cur2 = conn.execute(
            "SELECT anonymized_name, anonymized_contact FROM patients WHERE patient_id = ?",
            (pid,),
        )
        anon_row = cur2.fetchone()
        if anon_row and anon_row["anonymized_name"] and anon_row["anonymized_contact"]:
            continue  # already anonymized
        a_name, a_contact = anonymize_fields(name, contact, use_encryption=use_encryption)
        conn.execute(
            "UPDATE patients SET anonymized_name = ?, anonymized_contact = ? WHERE patient_id = ?",
            (a_name, a_contact, pid),
        )
        updated += 1
    conn.commit()
    conn.close()
    return updated


def export_patients_csv(path: str = "patients_export.csv") -> bool:
    """Export full patient table (including anonymized columns) to CSV."""
    try:
        import csv
        conn = get_connection()
        cur = conn.execute(
            "SELECT patient_id, name, contact, diagnosis, anonymized_name, anonymized_contact, date_added FROM patients ORDER BY patient_id"
        )
        rows = cur.fetchall()
        fieldnames = [
            "patient_id",
            "name",
            "contact",
            "diagnosis",
            "anonymized_name",
            "anonymized_contact",
            "date_added",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fieldnames)
            for r in rows:
                writer.writerow([r[c] for c in fieldnames])
        conn.close()
        return True
    except Exception:
        return False


# Initialize database at import time (first run convenience)
if not os.path.exists(DB_FILE):
    init_db()
