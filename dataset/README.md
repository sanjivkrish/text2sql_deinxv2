# School ERP — Dataset

## Masking Policy

| Field type | Treatment |
|------------|-----------|
| Aadhaar / PAN number | `[REDACTED]` |
| Phone numbers | `[REDACTED]` |
| Email addresses | `[REDACTED]` |
| Date of birth | `[REDACTED]` |
| Pincode | `[REDACTED]` |
| School name & address | `[SCHOOL NAME REDACTED]` / `[ADDRESS REDACTED]` |
| Passwords / auth tokens | Not generated |
| Bank account numbers, IFSC, PF | `[REDACTED]` |

## Schools

| ID suffix | Code | Target students | Target staff |
|-----------|------|-----------------|--------------|
| ...000001 | SCH-A | 2200 | 175 |
| ...004545 | SCH-B | 1800 | 130 |
| ...008283 | SCH-C | 1000 | 70 |

## Files

| File | Records | Description |
|------|---------|-------------|
| `schools.json` | 3 | schools |
| `academic_years.json` | 6 | academic years |
| `classes.json` | 41 | classes |
| `class_sections.json` | 128 | class sections |
| `class_section_years.json` | 128 | class section years |
| `subjects.json` | 45 | subjects |
| `staff.json` | 375 | staff |
| `staff_qualifications.json` | 755 | staff qualifications |
| `staff_certifications.json` | 56 | staff certifications |
| `staff_experience.json` | 323 | staff experience |
| `students.json` | 5,000 | students |
| `student_addresses.json` | 3,396 | student addresses |
| `admission_applications.json` | 135 | admission applications |

## Key Enumerations

**`students.status`:** `active`, `inactive`

**`staff.status`:** `draft` · `on_probation` · `active` · `on_leave` · `notice_period` · `resigned` · `terminated` · `retired` · `absconded` · `deceased` · `archived`

**`staff.staff_category`:** `teaching_pgt` · `teaching_tgt` · `teaching_prt` · `teaching_ntt` · `management` · `administrative` · `finance` · `library` · `laboratory` · `it` · `transport` · `support` · `security` · `canteen`

**`admission_applications.status`:** `inquiry` · `admitted` · `enrolled` · `rejected`

**`academic_years.status`:** `draft` · `active` · `archived`

## Notes

- `class_section_years.class_teacher_id` references a staff record in the same school.
- `staff.reporting_manager_id` references another staff record (hierarchy, no cycles).
- All UUIDs are deterministic counter-based IDs, not cryptographic UUIDs.
