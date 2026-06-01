# School ERP — Database Schema Reference

> **Purpose:** Complete schema reference for the School ERP platform. Intended for AI/ML teams consuming this data for LLM training or service development.
> **Database:** PostgreSQL (Supabase) — all tables in the `public` schema.
> **Multi-tenancy:** Every school-scoped table carries a `school_id` UUID. Row-Level Security (RLS) enforces tenant isolation at the database layer.
> **Currency:** INR (₹), stored as `DECIMAL(10,2)`.
> **Languages:** `preferred_language` is `'en'` (English) or `'ta'` (Tamil).

---

## Table of Contents

1. [Authentication & Identity](#1-authentication--identity)
2. [Schools (Tenants)](#2-schools-tenants)
3. [Feature System](#3-feature-system)
4. [Students](#4-students)
5. [Admissions](#5-admissions)
6. [Staff](#6-staff)
7. [Classes & Sections](#7-classes--sections)
8. [Subjects](#8-subjects)
9. [Academic Years](#9-academic-years)
10. [Entity Relationships (Summary)](#10-entity-relationships-summary)
11. [Access Control Model](#11-access-control-model)
12. [Key Business Rules](#12-key-business-rules)

---

## 1. Authentication & Identity

### `auth.users` _(Supabase Auth — managed, not editable)_
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key; referenced throughout as the user identity anchor |
| `email` | TEXT | Login email |
| `phone` | TEXT | Phone login |
| `created_at` | TIMESTAMPTZ | |

---

### `public.profiles`
One-to-one extension of `auth.users`. Created automatically on sign-up via trigger.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | FK → `auth.users(id)` ON DELETE CASCADE |
| `full_name` | TEXT | YES | Display name |
| `phone` | TEXT | YES | |
| `role` | TEXT | NO | `super_admin` \| `school_admin` \| `staff` \| `teaching_staff` \| `parent` \| `student` |
| `preferred_language` | TEXT | NO | `en` \| `ta`. Default `'en'` |
| `avatar_url` | TEXT | YES | Storage URL |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | Auto-updated via trigger |

**RLS:** Each user can read/write only their own row. `super_admin` has full access.

---

### `public.school_memberships`
Links users to schools with a role. One user can belong to multiple schools.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `user_id` | UUID | NO | FK → `auth.users(id)` ON DELETE CASCADE |
| `school_id` | UUID | NO | FK → `schools(id)` ON DELETE CASCADE |
| `role` | TEXT | NO | `school_admin` \| `staff` \| `teaching_staff` \| `parent` |
| `is_active` | BOOLEAN | NO | Default `true` |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |

**Constraint:** UNIQUE(`user_id`, `school_id`) — one membership row per user per school.

---

## 2. Schools (Tenants)

### `public.schools`
Top-level tenant entity. Every school-scoped table references this.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `name` | TEXT | NO | School's full name |
| `address` | TEXT | YES | |
| `phone` | TEXT | YES | |
| `email` | TEXT | YES | |
| `logo_url` | TEXT | YES | Storage URL |
| `school_code` | TEXT | YES | Short code used in employee ID generation (e.g. `ABCSCH`) |
| `settings` | JSONB | NO | Per-school config blob. Default `{}` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | Auto-updated via trigger |

---

## 3. Feature System

Schools can enable/disable modules, and roles can be granted read/write per feature.

### `public.feature_catalog`
Global registry of all available modules.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `key` | TEXT PK | NO | Slug e.g. `admissions`, `student_management`, `staff_management`, `subjects`, `classes`, `academic_years` |
| `name` | TEXT | NO | Human-readable label |
| `description` | TEXT | YES | |
| `is_active` | BOOLEAN | NO | Default `true` |
| `created_at` | TIMESTAMPTZ | NO | |

---

### `public.school_feature_settings`
Per-school feature on/off switch.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `feature_key` | TEXT | NO | FK → `feature_catalog(key)` |
| `is_enabled` | BOOLEAN | NO | Default `false` |
| `created_at` | TIMESTAMPTZ | NO | |

**Constraint:** UNIQUE(`school_id`, `feature_key`)

---

### `public.role_feature_permissions`
Per-role access grants within a school for a specific feature.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `role` | TEXT | NO | `staff` \| `teaching_staff` \| `parent` |
| `feature_key` | TEXT | NO | FK → `feature_catalog(key)` |
| `can_read` | BOOLEAN | NO | Default `false` |
| `can_write` | BOOLEAN | NO | Default `false` |
| `created_at` | TIMESTAMPTZ | NO | |

**Constraint:** UNIQUE(`school_id`, `role`, `feature_key`)

---

## 4. Students

### `public.students`
Core student record. Attached to a school and optionally to a class section.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` ON DELETE CASCADE |
| `full_name` | TEXT | NO | |
| `surname` | TEXT | YES | |
| `date_of_birth` | DATE | YES | |
| `class` | TEXT | YES | Free-text class name (legacy; `class_section_id` preferred) |
| `section` | TEXT | YES | Free-text section (legacy) |
| `class_section_id` | UUID | YES | FK → `class_sections(id)` ON DELETE SET NULL |
| `roll_number` | TEXT | YES | Class-level, changes yearly |
| `registration_number` | TEXT | YES | School-assigned permanent ID. UNIQUE per school (non-null) |
| `father_name` | TEXT | YES | |
| `father_phone` | TEXT | YES | |
| `father_email` | TEXT | YES | |
| `father_occupation` | TEXT | YES | |
| `father_qualification` | TEXT | YES | |
| `father_annual_income` | TEXT | YES | |
| `father_office_address` | TEXT | YES | |
| `mother_name` | TEXT | YES | |
| `mother_phone` | TEXT | YES | |
| `mother_email` | TEXT | YES | |
| `mother_occupation` | TEXT | YES | |
| `mother_qualification` | TEXT | YES | |
| `mother_annual_income` | TEXT | YES | |
| `mother_office_address` | TEXT | YES | |
| `aadhaar_number` | TEXT | YES | Indian national ID |
| `place_of_birth` | TEXT | YES | |
| `city` | TEXT | YES | |
| `district` | TEXT | YES | |
| `state` | TEXT | YES | |
| `disability` | TEXT | YES | |
| `caste` | TEXT | YES | |
| `mother_tongue` | TEXT | YES | |
| `category` | TEXT | YES | e.g. General, OBC, SC, ST |
| `religion` | TEXT | YES | |
| `last_school` | TEXT | YES | Previous school name |
| `admission_class` | TEXT | YES | Class at time of initial admission |
| `blood_group` | TEXT | YES | `A+` \| `A-` \| `B+` \| `B-` \| `AB+` \| `AB-` \| `O+` \| `O-` |
| `identification_mark` | TEXT | YES | Physical identification mark |
| `photo_path` | TEXT | YES | Storage path for student photo |
| `status` | TEXT | YES | Student status (active, withdrawn, etc.) |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | Auto-updated via trigger |

---

### `public.student_addresses`
Permanent address stored separately for history tracking (one row per student currently).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `student_id` | UUID | NO | FK → `students(id)` ON DELETE CASCADE. UNIQUE (one per student) |
| `address_line` | TEXT | YES | |
| `city` | TEXT | YES | |
| `district` | TEXT | YES | |
| `state` | TEXT | YES | |
| `pincode` | TEXT | YES | |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

---

### `public.student_parents`
Links students to parent user accounts.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `student_id` | UUID | NO | FK → `students(id)` |
| `parent_user_id` | UUID | NO | FK → `auth.users(id)` |
| `relationship` | TEXT | NO | `father` \| `mother` \| `guardian` |
| `created_at` | TIMESTAMPTZ | NO | |

**Constraint:** UNIQUE(`student_id`, `parent_user_id`)

---

### `public.student_documents`
Documents uploaded for a student (Aadhaar, birth certificate, etc.).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `student_id` | UUID | NO | FK → `students(id)` |
| `doc_type` | TEXT | NO | e.g. `aadhaar`, `birth_certificate`, `tc` |
| `file_path` | TEXT | NO | Storage path |
| `uploaded_by` | UUID | YES | FK → `auth.users(id)` |
| `uploaded_at` | TIMESTAMPTZ | NO | |

---

## 5. Admissions

### `public.admission_applications`
Tracks a prospective student through the inquiry → admitted → enrolled funnel.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` ON DELETE CASCADE |
| `student_name` | TEXT | NO | |
| `date_of_birth` | DATE | YES | |
| `class_applied` | TEXT | NO | Class the student is applying for |
| `section_applied` | TEXT | YES | |
| `parent_name` | TEXT | NO | |
| `parent_phone` | TEXT | NO | |
| `parent_email` | TEXT | YES | |
| `notes` | TEXT | YES | Internal notes |
| `status` | TEXT | NO | `inquiry` \| `admitted` \| `enrolled` \| `rejected`. Default `inquiry` |
| `form_number` | TEXT | YES | Printed form number given to applicant |
| `date_of_issue` | DATE | YES | Date form was issued |
| `registration_number` | TEXT | YES | Pre-enrollment registration number |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | Auto-updated via trigger |

**RPC:** `enroll_student(p_admission_id UUID) → UUID`
Atomically promotes an `admitted` application to `enrolled` and creates a `students` row. Returns the new student ID. `SECURITY DEFINER`.

---

### `public.admission_documents`
Documents attached to an admission application.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `admission_id` | UUID | NO | FK → `admission_applications(id)` |
| `doc_type` | TEXT | NO | |
| `file_path` | TEXT | NO | Storage path |
| `uploaded_by` | UUID | YES | FK → `auth.users(id)` |
| `uploaded_at` | TIMESTAMPTZ | NO | |

---

### `public.parent_form_tokens`
Tokenized links sent to parents to fill in student details themselves.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `admission_id` | UUID | NO | FK → `admission_applications(id)` |
| `token` | TEXT | NO | Unique random token embedded in parent URL |
| `expires_at` | TIMESTAMPTZ | NO | |
| `used_at` | TIMESTAMPTZ | YES | NULL = not yet submitted |
| `created_at` | TIMESTAMPTZ | NO | |

---

## 6. Staff

### `public.staff`
Comprehensive employee record. Covers personal info, contact, employment, payroll, and status.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` ON DELETE CASCADE |
| `user_id` | UUID | YES | FK → `auth.users(id)` ON DELETE SET NULL. Links to login account |
| `employee_id` | TEXT | NO | Auto-generated as `{SCHOOL_CODE}-{YY}-{NNNN}` e.g. `ABCSCH-26-0001` |
| **Personal** | | | |
| `first_name` | TEXT | NO | |
| `last_name` | TEXT | YES | |
| `preferred_name` | TEXT | YES | |
| `father_name` | TEXT | YES | |
| `dob` | DATE | YES | Date of birth |
| `gender` | TEXT | YES | `male` \| `female` \| `other` \| `prefer_not_to_say` |
| `blood_group` | TEXT | YES | `A+/A-/B+/B-/AB+/AB-/O+/O-/unknown` |
| `marital_status` | TEXT | YES | `single` \| `married` \| `divorced` \| `widowed` \| `separated` |
| `nationality` | TEXT | YES | Default `'Indian'` |
| `religion` | TEXT | YES | |
| `caste_category` | TEXT | YES | `General` \| `OBC` \| `MBC` \| `DNC` \| `SC` \| `SCA` \| `ST` |
| `sub_caste` | TEXT | YES | |
| `aadhar_number` | TEXT | YES | UNIQUE per school (non-deleted) |
| `pan_number` | TEXT | YES | |
| `profile_photo_path` | TEXT | YES | Storage path |
| **Contact** | | | |
| `personal_mobile` | TEXT | NO | UNIQUE per school (non-deleted) |
| `alternate_mobile` | TEXT | YES | |
| `emergency_contact_name` | TEXT | YES | |
| `emergency_contact_relationship` | TEXT | YES | |
| `emergency_contact_phone` | TEXT | YES | |
| `personal_email` | TEXT | YES | |
| `official_email` | TEXT | YES | |
| `whatsapp_number` | TEXT | YES | |
| `preferred_language` | TEXT | NO | `en` \| `ta`. Default `'en'` |
| `current_address` | JSONB | NO | Default `{}` |
| `permanent_address` | JSONB | NO | Default `{}` |
| **Employment** | | | |
| `staff_category` | TEXT | NO | See values below¹ |
| `designation` | TEXT | YES | Job title |
| `department` | TEXT | YES | |
| `employment_type` | TEXT | NO | `permanent` \| `probation` \| `contract` \| `part_time` \| `guest` \| `outsourced` \| `consultant` \| `intern` |
| `probation_period_months` | INTEGER | YES | |
| `contract_start` | DATE | YES | |
| `contract_end` | DATE | YES | |
| `date_of_joining` | DATE | NO | |
| `date_of_confirmation` | DATE | YES | When probation ended |
| `work_location` | TEXT | YES | |
| `reporting_manager_id` | UUID | YES | FK → `staff(id)`. Self-referential hierarchy. Cycle detection enforced by trigger |
| `shift_timing` | TEXT | YES | |
| `weekly_off_days` | TEXT[] | NO | Default `[]` |
| **Payroll** | | | |
| `pay_grade` | TEXT | YES | |
| `ctc` | DECIMAL(10,2) | YES | Cost to company (INR) |
| `in_hand_salary` | DECIMAL(10,2) | YES | Take-home (INR) |
| `pf_account_number` | TEXT | YES | Provident Fund |
| `uan` | TEXT | YES | Universal Account Number |
| `esi_number` | TEXT | YES | Employee State Insurance |
| `bank_name` | TEXT | YES | |
| `bank_account_number` | TEXT | YES | |
| `ifsc` | TEXT | YES | Bank branch code |
| `bank_account_holder_name` | TEXT | YES | |
| **Flags** | | | |
| `has_system_access` | BOOLEAN | NO | Default `true` |
| `blacklist` | BOOLEAN | NO | Default `false` |
| **Status** | | | |
| `status` | TEXT | NO | `draft` \| `on_probation` \| `active` \| `on_leave` \| `notice_period` \| `resigned` \| `terminated` \| `retired` \| `absconded` \| `deceased` \| `archived` |
| **Lifecycle** | | | |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | Auto-updated via trigger |
| `deleted_at` | TIMESTAMPTZ | YES | Soft-delete timestamp |
| `deleted_by` | UUID | YES | FK → `auth.users(id)` |

¹ **`staff_category` values:** `teaching_pgt`, `teaching_tgt`, `teaching_prt`, `teaching_ntt`, `teaching_special_subject`, `teaching_special_educator`, `teaching_part_time`, `teaching_visiting`, `teaching_guest`, `management`, `administrative`, `finance`, `library`, `laboratory`, `it`, `transport`, `support`, `security`, `canteen`, `medical`, `hostel`, `sports_coach`, `contract_outsourced`

---

### `public.staff_employee_id_sequence`
Counter used to auto-generate sequential employee IDs per school per year.

| Column | Type | Notes |
|--------|------|-------|
| `school_id` | UUID PK | FK → `schools(id)` |
| `year_yy` | TEXT PK | Two-digit year e.g. `'26'` |
| `last_value` | INTEGER | Incremented on each new hire |

---

### `public.staff_qualifications`
Academic qualifications for a staff member.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `staff_id` | UUID | NO | FK → `staff(id)` ON DELETE CASCADE |
| `level` | TEXT | NO | `class_10` \| `class_12` \| `diploma` \| `graduation` \| `post_graduation` \| `mphil` \| `phd` \| `other` |
| `qualification_name` | TEXT | NO | e.g. `B.Ed`, `M.Sc Mathematics` |
| `specialization` | TEXT | YES | |
| `university` | TEXT | YES | |
| `institution` | TEXT | YES | |
| `year_of_passing` | INTEGER | YES | |
| `grade` | TEXT | YES | |
| `mode` | TEXT | YES | `regular` \| `distance` \| `online` \| `correspondence` |
| `certificate_doc_path` | TEXT | YES | Storage path |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

---

### `public.staff_certifications`
Professional certifications and teaching licenses.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `staff_id` | UUID | NO | FK → `staff(id)` |
| `cert_type` | TEXT | NO | e.g. `TET`, `CTET`, `NET` |
| `cert_name` | TEXT | YES | |
| `cert_number` | TEXT | YES | |
| `issue_date` | DATE | YES | |
| `validity_date` | DATE | YES | |
| `level` | TEXT | YES | |
| `doc_path` | TEXT | YES | Storage path |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

---

### `public.staff_experience`
Previous employment history.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `staff_id` | UUID | NO | FK → `staff(id)` |
| `institution` | TEXT | NO | Previous employer name |
| `designation` | TEXT | YES | Role held |
| `from_date` | DATE | YES | |
| `to_date` | DATE | YES | NULL = current job |
| `subjects_taught` | TEXT[] | YES | Array of subject names |
| `reason_for_leaving` | TEXT | YES | |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

---

### `public.staff_documents`
Documents uploaded for a staff member with verification workflow.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `staff_id` | UUID | NO | FK → `staff(id)` |
| `doc_type` | TEXT | NO | e.g. `aadhar`, `pan`, `degree`, `experience_letter` |
| `doc_label` | TEXT | YES | Human-readable label |
| `file_url` | TEXT | NO | Storage URL |
| `uploaded_by` | UUID | YES | FK → `auth.users(id)` |
| `uploaded_at` | TIMESTAMPTZ | NO | |
| `expiry_date` | DATE | YES | For time-bound documents |
| `verified_by` | UUID | YES | FK → `auth.users(id)` |
| `verified_at` | TIMESTAMPTZ | YES | |
| `verification_status` | TEXT | NO | `pending` \| `verified` \| `rejected`. Default `pending` |
| `verification_notes` | TEXT | YES | |

---

### `public.staff_designation_history`
Immutable log of designation/department/pay grade changes.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | |
| `staff_id` | UUID | NO | FK → `staff(id)` |
| `old_designation` | TEXT | YES | |
| `new_designation` | TEXT | YES | |
| `old_department` | TEXT | YES | |
| `new_department` | TEXT | YES | |
| `old_pay_grade` | TEXT | YES | |
| `new_pay_grade` | TEXT | YES | |
| `effective_date` | DATE | NO | |
| `reason` | TEXT | YES | |
| `approved_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |

---

### `public.staff_exit_records`
Records staff departure with full exit details (one row per staff member).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | |
| `staff_id` | UUID | NO | FK → `staff(id)` UNIQUE |
| `exit_type` | TEXT | NO | `resigned` \| `terminated` \| `retired` \| `absconded` \| `deceased` \| `contract_ended` |
| `exit_date` | DATE | NO | |
| `reason_enum` | TEXT | YES | Structured reason code |
| `reason_notes` | TEXT | YES | Free text |
| `notice_period_days` | INTEGER | YES | |
| `last_working_day` | DATE | YES | |
| `severance_amount` | DECIMAL(10,2) | YES | INR |
| `fnf_status` | TEXT | YES | `pending` \| `processing` \| `settled` \| `disputed` |
| `blacklist_flag` | BOOLEAN | NO | Default `false` |
| `posh_case_ref` | TEXT | YES | POSH (harassment) case reference if applicable |
| `exit_interview_notes` | TEXT | YES | |
| `processed_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |

---

### `public.staff_audit_log`
Append-only audit trail for all changes to the `staff` table.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | |
| `staff_id` | UUID | NO | |
| `table_name` | TEXT | NO | Always `'staff'` currently |
| `record_id` | UUID | NO | |
| `action` | TEXT | NO | `INSERT` \| `UPDATE` \| `DELETE` \| `SOFT_DELETE` \| `RESTORE` \| `STATUS_CHANGE` |
| `old_values` | JSONB | YES | Full row before change |
| `new_values` | JSONB | YES | Full row after change |
| `changed_by` | UUID | YES | FK → `auth.users(id)` |
| `changed_at` | TIMESTAMPTZ | NO | |

---

### `public.staff_teaching_assignments`
Teaching assignments per staff member per academic year.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `staff_id` | UUID | NO | FK → `staff(id)` |
| `academic_year` | TEXT | NO | e.g. `'2025-2026'` |
| `class_name` | TEXT | NO | |
| `section` | TEXT | NO | |
| `subject_name` | TEXT | NO | |
| `periods_per_week` | INTEGER | YES | |
| `is_class_teacher` | BOOLEAN | NO | Default `false` |
| `is_substitute` | BOOLEAN | NO | Default `false` |
| `effective_from` | DATE | NO | |
| `effective_to` | DATE | YES | NULL = current |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

**Constraints:**
- UNIQUE: one class teacher per section per academic year
- UNIQUE: one staff+subject+class+section per academic year (non-substitute)

---

## 7. Classes & Sections

### `public.classes`
Permanent class master (e.g. LKG, Class 1 … Class 12). Not tied to a year.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `name` | TEXT | NO | e.g. `'LKG'`, `'Class 6'`. UNIQUE per school (case-insensitive) |
| `grade_level` | SMALLINT | NO | `0` (pre-primary) to `12`. Used for subject compatibility filtering |
| `display_order` | INTEGER | NO | Default `0` |
| `description` | TEXT | YES | |
| `is_active` | BOOLEAN | NO | Default `true` |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

---

### `public.class_sections`
Permanent section structure (A, B, C or custom) within a class.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `class_id` | UUID | NO | FK → `classes(id)` ON DELETE CASCADE |
| `name` | TEXT | NO | e.g. `'A'`, `'Rose'`. UNIQUE within class (case-insensitive) |
| `display_order` | INTEGER | NO | Default `0` |
| `is_active` | BOOLEAN | NO | Default `true` |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

---

### `public.class_section_years`
Per-year configuration for a section (class teacher, capacity, active flag).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `section_id` | UUID | NO | FK → `class_sections(id)` ON DELETE CASCADE |
| `academic_year` | TEXT | NO | Pattern `YYYY-YYYY` |
| `class_teacher_id` | UUID | YES | FK → `staff(id)` ON DELETE SET NULL |
| `capacity` | INTEGER | YES | Max students |
| `is_active` | BOOLEAN | NO | Default `true` |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

**Constraint:** UNIQUE(`section_id`, `academic_year`)

---

### `public.class_subjects`
Subjects assigned to a class for a given academic year (class-level, not section-level).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `class_id` | UUID | NO | FK → `classes(id)` ON DELETE CASCADE |
| `subject_id` | UUID | NO | FK → `subjects(id)` ON DELETE CASCADE |
| `academic_year` | TEXT | NO | Pattern `YYYY-YYYY` |
| `periods_per_week` | INTEGER | YES | |
| `is_elective` | BOOLEAN | NO | Default `false` |
| `display_order` | INTEGER | NO | Default `0` |
| `is_active` | BOOLEAN | NO | Default `true` |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

**Constraint:** UNIQUE(`class_id`, `subject_id`, `academic_year`)

---

## 8. Subjects

### `public.subject_templates`
Global subject catalog (not school-scoped). Used as a picker when schools set up their own subjects.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `name` | TEXT | NO | UNIQUE (case-insensitive) |
| `aliases` | TEXT[] | NO | Alternative spellings/names |
| `code` | TEXT | YES | |
| `category` | TEXT | NO | `language` \| `mathematics` \| `science` \| `social_studies` \| `computer_science` \| `arts` \| `physical_education` \| `commerce` \| `activity_special` |
| `is_special_activity` | BOOLEAN | NO | Default `false` |
| `assessment_type` | TEXT | NO | `marks` \| `grade` \| `attendance_only` \| `none`. Default `marks` |
| `from_grade` | INTEGER | NO | Grade range start (0–12). Default `1` |
| `to_grade` | INTEGER | NO | Grade range end (0–12). Default `12` |
| `is_active` | BOOLEAN | NO | Default `true` |

**RLS:** Any authenticated user can SELECT. Only `super_admin` can mutate.

---

### `public.subjects`
Per-school subject catalog. Schools customize from templates or create their own.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `name` | TEXT | NO | UNIQUE per school (case-insensitive, non-deleted) |
| `code` | TEXT | YES | UNIQUE per school (case-insensitive, non-deleted, non-null) |
| `category` | TEXT | NO | Same values as `subject_templates.category` |
| `is_special_activity` | BOOLEAN | NO | Default `false` |
| `assessment_type` | TEXT | NO | `marks` \| `grade` \| `attendance_only` \| `none` |
| `max_marks` | INTEGER | YES | Must be > 0 if set |
| `pass_marks` | INTEGER | YES | Must be ≤ `max_marks` if set |
| `from_grade` | INTEGER | NO | Default `1` |
| `to_grade` | INTEGER | NO | Default `12` |
| `periods_per_week` | INTEGER | YES | |
| `color` | TEXT | NO | UI color token. Default `'slate'` |
| `description` | TEXT | YES | |
| `status` | TEXT | NO | `active` \| `inactive` |
| `display_order` | INTEGER | NO | Default `0` |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |
| `deleted_at` | TIMESTAMPTZ | YES | Soft-delete |
| `deleted_by` | UUID | YES | FK → `auth.users(id)` |

---

### `public.subject_class_configs`
Per-class (and optionally per-section) overrides for a subject (teacher, periods). Lazy-populated.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `subject_id` | UUID | NO | FK → `subjects(id)` |
| `class_id` | UUID | YES | FK → `classes(id)` ON DELETE SET NULL |
| `class_name` | TEXT | NO | Free-text class name |
| `section` | TEXT | YES | NULL = applies to all sections |
| `academic_year` | TEXT | NO | |
| `periods_per_week` | INTEGER | YES | Overrides `subjects.periods_per_week` |
| `is_elective` | BOOLEAN | NO | Default `false` |
| `primary_staff_id` | UUID | YES | FK → `staff(id)` ON DELETE SET NULL. Subject teacher for this class |
| `is_active` | BOOLEAN | NO | Default `true` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

**Constraint:** UNIQUE(`school_id`, `subject_id`, `class_name`, `section` (COALESCE null→''), `academic_year`)

---

## 9. Academic Years

### `public.academic_years`
First-class academic year entity. Replaces free-text `academic_year` strings.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID PK | NO | |
| `school_id` | UUID | NO | FK → `schools(id)` |
| `name` | TEXT | NO | Format `YYYY-YYYY` where second year = first + 1. UNIQUE per school |
| `start_date` | DATE | NO | |
| `end_date` | DATE | NO | Must be > `start_date`. Minimum 90-day span |
| `status` | TEXT | NO | `draft` \| `active` \| `archived`. Default `draft` |
| `is_current` | BOOLEAN | NO | Exactly one `true` per school (enforced by partial unique index + trigger) |
| `is_locked` | BOOLEAN | NO | When `true`, prevents data edits for the year |
| `created_by` | UUID | YES | FK → `auth.users(id)` |
| `created_at` | TIMESTAMPTZ | NO | |
| `updated_at` | TIMESTAMPTZ | NO | |

**Business rules:**
- `status` lifecycle: `draft` → `active` → `archived`
- Only `draft` years can be hard-deleted; others must be archived
- Setting `is_current = true` on one row automatically sets all siblings to `false` (trigger)

---

## 10. Entity Relationships (Summary)

```
auth.users
  └── profiles (1:1)
  └── school_memberships (1:many) → schools
        └── school_feature_settings → feature_catalog
        └── role_feature_permissions → feature_catalog

schools
  ├── students (1:many)
  │     ├── student_addresses (1:1)
  │     ├── student_parents (many:many) → auth.users
  │     └── student_documents (1:many)
  │
  ├── admission_applications (1:many)
  │     ├── admission_documents (1:many)
  │     └── parent_form_tokens (1:many)
  │
  ├── staff (1:many)
  │     ├── staff_qualifications (1:many)
  │     ├── staff_certifications (1:many)
  │     ├── staff_experience (1:many)
  │     ├── staff_documents (1:many)
  │     ├── staff_designation_history (1:many)
  │     ├── staff_exit_records (1:1)
  │     ├── staff_audit_log (1:many)
  │     └── staff_teaching_assignments (1:many)
  │
  ├── classes (1:many)
  │     ├── class_sections (1:many)
  │     │     └── class_section_years (1:many) — links to staff (class teacher)
  │     └── class_subjects (1:many) — links to subjects
  │
  ├── subjects (1:many)
  │     └── subject_class_configs (1:many)
  │
  └── academic_years (1:many)

subject_templates (global, no school_id)
```

---

## 11. Access Control Model

### Roles
| Role | Scope | Description |
|------|-------|-------------|
| `super_admin` | Platform-wide | Full access to all schools and all tables |
| `school_admin` | Own school | Full CRUD on all school-scoped data |
| `staff` | Own school | Read/write gated by `role_feature_permissions` |
| `teaching_staff` | Own school | Read/write gated by `role_feature_permissions` |
| `parent` | Own children | Read-only access to own student's data |
| `student` | Own record | Limited read access (future) |

### RLS Helper Functions
| Function | Purpose |
|----------|---------|
| `is_super_admin()` | Returns `true` if calling user's profile role is `super_admin` |
| `has_school_role(school_id, role)` | Returns `true` if user has the given role in the given school |
| `has_feature_access(school_id, feature_key, mode)` | Returns `true` if the feature is enabled and the user's role has read/write access |
| `parent_has_student(student_id)` | Returns `true` if the calling user is a linked parent of the student |
| `get_auth_school_id()` | Returns the school_id for the current user's primary school |

### RLS Pattern per Table
Every school-scoped table follows this pattern:
1. `super_admin` → unrestricted ALL
2. `school_admin` → ALL within `school_id`
3. `staff` / `teaching_staff` → feature-gated SELECT (and sometimes INSERT/UPDATE)
4. `parent` → SELECT on own child's rows only

---

## 12. Key Business Rules

| Rule | Detail |
|------|--------|
| **Soft deletes** | `staff` and `subjects` are soft-deleted via `deleted_at`. Hard-delete is blocked or unused |
| **Employee ID format** | `{SCHOOL_CODE}-{YY}-{NNNN}` — auto-generated on INSERT if blank |
| **Admission funnel** | `inquiry` → `admitted` → `enrolled` (via `enroll_student()` RPC) or `rejected` |
| **One class teacher** | Only one staff member can be `is_class_teacher` per section per academic year |
| **Academic year uniqueness** | Only one `is_current = true` per school; non-draft years cannot be deleted |
| **Subject grade range** | `from_grade <= to_grade`; grades 0–12 (0 = pre-primary) |
| **Reporting manager cycle** | Trigger prevents circular manager hierarchies up to depth 20 |
| **Currency** | All monetary fields use `DECIMAL(10,2)` (INR) |
| **Timestamps** | All tables have `created_at` + `updated_at` (auto-set via trigger) |
| **Multi-tenancy** | Every school-scoped table has `school_id`; RLS enforces isolation |
