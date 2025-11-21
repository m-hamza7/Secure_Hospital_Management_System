# Streamlit Hospital Management System (Privacy & Security)

## Overview
This project is a small Hospital Management Dashboard demonstrating core Information Security concepts: Privacy, Trust, and the CIA triad (Confidentiality, Integrity, Availability) along with GDPR-aligned practices (privacy by design, transparency, data minimization, control).

Built with: Python, Streamlit, SQLite, optional Fernet encryption.

## Features
- Role-Based Access Control (RBAC): Admin, Doctor, Receptionist.
- Secure Login with hashed passwords (SHA-256 + salt).
- Patient Management: add, edit, view with role restrictions.
- Data Anonymization (masking) and optional reversible encryption (Fernet) for demonstration.
- Audit Logging of all user actions (login, view, add, edit, anonymize, export).
- CSV Backup export (Admin only) for availability & resilience.
- Integrity controls via controlled CRUD paths and logging.
- Availability helpers: error handling, graceful fallbacks, uptime display.

## Tables (SQLite)
1. `users(user_id INTEGER PK, username TEXT UNIQUE, password_hash TEXT, salt TEXT, role TEXT)`
2. `patients(patient_id INTEGER PK, name TEXT, contact TEXT, diagnosis TEXT, anonymized_name TEXT, anonymized_contact TEXT, date_added TEXT)`
3. `logs(log_id INTEGER PK, user_id INTEGER, role TEXT, action TEXT, timestamp TEXT, details TEXT)`

## Roles
- Admin: Full access, view raw & anonymized data, trigger anonymization, view logs, export CSV.
- Doctor: View only anonymized patient data (no raw PII).
- Receptionist: Add/Edit patient records; sees only limited non-sensitive fields (no contact details in listing).

## GDPR Principles Applied
- Privacy by Design: Separation of raw vs anonymized fields; restricted views.
- Data Minimization: Roles only see necessary columns.
- Transparency: Audit logs visible to Admin; clear labeling of anonymized data.
- Control: Admin can (re)run anonymization; optional encryption toggle.

## Anonymization Rules
- Name → `ANON_XXXX` (random suffix)
- Contact → `XXX-XXX-XXXX`
- Optional encryption replaces anonymized values with Fernet ciphertext (still concealed from Doctor/Receptionist).

## Getting Started
```bash
pip install -r requirements.txt
streamlit run app.py
```

On first run the database (`database.db`) is created with sample users & patients.

### Sample Credentials
| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |
| Doctor | doctor | doctor123 |
| Receptionist | reception | recep123 |

## Environment Variables (Optional)
Create a `.env` file if you want a custom Fernet key:
```
FERNET_KEY=your_base64_key_here
```
If omitted, a key file `fernet.key` is generated at runtime.

## Running Notes
- CSV export writes `patients_export.csv` in project root.
- Uptime and last sync shown in footer.
- All actions appended to `logs` table.

## Security Notes
- Passwords never stored in plaintext; salted hash used.
- Direct SQL injection risk mitigated using parameterized queries.
- Encryption optional to illustrate reversible anonymization scenario.

## Future Improvements (Not Implemented Here)
- JWT or session token system.
- Multi-factor authentication.
- Automatic log rotation & archival.
- Granular consent management per patient.

## License
Educational use only for Information Security assignment.
