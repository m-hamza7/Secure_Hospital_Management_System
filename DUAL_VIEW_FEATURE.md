# Admin Dual-View Feature

## Overview
The **Dual-View Feature** allows admin users to see both **original (raw)** and **anonymized/masked/encrypted** patient data side by side in the Patient Records view.

## Features Implemented

### 1. Toggle Switch for Admin Users
- Located at the top of the Patient Records page
- **Label**: "🔍 Show Dual View (Original + Anonymized)"
- Only visible to users with the `admin` role
- Can be toggled on/off to switch between views

### 2. Dual-View Display

When **enabled**, each patient card shows:

#### Left Column: 📋 Original Data
- **Patient Name**: Raw, unmodified name from database
- **Contact**: Raw, unmodified contact information
- **Diagnosis**: Patient diagnosis (same in both columns)

#### Right Column: 🔒 Anonymized/Masked Data
- **Anonymized Name**: Masked or encrypted version (e.g., `ANON_F4A2`)
- **Anonymized Contact**: Masked contact (e.g., `XXXXXXX789` showing only last 3 digits)
- **Diagnosis**: Patient diagnosis (same in both columns)

### 3. Visual Design

#### Dual-View Badge
- Purple gradient badge appears next to Patient ID when dual-view is active
- Displays "🔍 DUAL VIEW MODE" to indicate the viewing mode

#### Two-Column Layout
- Side-by-side columns with clear separation
- Gradient divider line between original and anonymized data
- Each column has:
  - Distinct background (semi-transparent navy)
  - Gold border for consistency with theme
  - Title headers with icons

#### Color Coding
- **Original data**: Standard white/light gray text
- **Anonymized data**: Purple color (`#8b5cf6`) with monospace font
- Makes it easy to distinguish at a glance

### 4. Standard View (Default)

When **disabled** (default state):
- Shows the standard view (raw data for admin)
- No dual-view badge displayed
- Single-column layout as before

## Usage Instructions

### For Admin Users:

1. **Login** as admin (`admin` / `admin123`)
2. Navigate to **Patient Records** from the sidebar
3. Look for the toggle switch at the top: "🔍 Show Dual View (Original + Anonymized)"
4. **Toggle ON** to activate dual-view mode
5. View patient cards showing both original and anonymized data side by side
6. **Toggle OFF** to return to standard view

### Important Notes:

- **Anonymization Required**: If a patient has not been anonymized yet, the anonymized column will show "Not Anonymized"
- **Run Anonymization**: Use the "Anonymize Data" panel (Admin only) to generate anonymized values for all patients
- **Encryption Option**: When anonymizing, you can choose to use Fernet encryption instead of simple masking

## Technical Implementation

### Modified Files:
- **app.py**: 
  - Added toggle switch in `view_patients()` function
  - Implemented dual-view HTML rendering
  - Added CSS styles for dual-view components

### CSS Classes Added:
- `.dual-view-badge`: Badge styling for dual-view indicator
- `.dual-view-container`: Flex container for two columns
- `.dual-view-column`: Individual column styling
- `.dual-view-title`: Section title styling
- `.dual-view-divider`: Visual separator between columns
- `.info-value.anonymized`: Special styling for anonymized data (purple, monospace)

### Database Columns Used:
- `name` - Original patient name
- `contact` - Original contact info
- `anonymized_name` - Masked/encrypted name
- `anonymized_contact` - Masked/encrypted contact
- `diagnosis` - Same in both views

## Benefits

### 1. Transparency
- Admins can verify that anonymization is working correctly
- Easy to audit data protection measures

### 2. Compliance
- Demonstrates GDPR privacy-by-design principles
- Shows clear separation between raw PII and anonymized data

### 3. Data Quality Assurance
- Compare original vs anonymized to ensure no data loss
- Verify encryption/masking algorithms are functioning

### 4. Training & Education
- Visual demonstration of data anonymization concepts
- Helps stakeholders understand privacy measures

## Security Considerations

- **Access Control**: Only admin role can toggle dual-view
- **Non-Admin Users**: 
  - Doctors: See only anonymized data (no raw PII)
  - Receptionists: See limited raw data (name only, no contact)
- **Audit Logging**: View actions are logged in the audit trail
- **No Data Leakage**: Toggle state is session-based, not persistent

## Future Enhancements (Optional)

1. **Decryption View**: For encrypted fields, add a "Decrypt" button to temporarily reveal original values
2. **Field-Level Toggle**: Allow toggling individual fields instead of all at once
3. **Export Both Views**: CSV export with both original and anonymized columns
4. **Comparison Highlighting**: Highlight differences between original and anonymized
5. **Audit Trail for Dual-View**: Log when dual-view is activated/deactivated

## Screenshots

### Standard View (Dual-View OFF)
- Single card showing current data based on role
- Admin sees raw data by default

### Dual-View Mode (Dual-View ON)
- Two-column layout
- Left: Original data with 📋 icon
- Right: Anonymized data with 🔒 icon
- Purple badge indicating dual-view mode
- Gradient divider between columns

## Testing

### Test Scenarios:

1. **Login as admin**
   - Verify toggle appears
   - Toggle ON and verify dual columns appear
   - Verify badge shows "DUAL VIEW MODE"

2. **Login as doctor**
   - Verify toggle does NOT appear
   - Verify only anonymized data is shown

3. **Login as receptionist**
   - Verify toggle does NOT appear
   - Verify limited data is shown (no contact)

4. **Anonymization**
   - Add new patient
   - Verify "Not Anonymized" shows in dual-view
   - Run anonymization
   - Verify anonymized values appear

5. **Encryption**
   - Run anonymization with encryption enabled
   - Verify encrypted strings appear in anonymized column
   - Verify they differ from masked versions

## Conclusion

The dual-view feature provides admin users with a powerful tool for:
- **Verifying** data protection measures
- **Auditing** anonymization processes
- **Understanding** the difference between raw and protected data
- **Demonstrating** GDPR compliance to stakeholders

This feature enhances transparency, security, and trust in the hospital management system while maintaining strict role-based access controls.
