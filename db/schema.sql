-- School ERP minimal schema for text-to-SQL v2
-- Only public.* tables (no auth schema)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Schools (tenant root)
CREATE TABLE IF NOT EXISTS public.schools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    email TEXT,
    logo_url TEXT,
    school_code TEXT,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Academic years
CREATE TABLE IF NOT EXISTS public.academic_years (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    is_current BOOLEAN NOT NULL DEFAULT false,
    is_locked BOOLEAN NOT NULL DEFAULT false,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Classes
CREATE TABLE IF NOT EXISTS public.classes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    grade_level SMALLINT NOT NULL DEFAULT 0,
    display_order INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Class sections
CREATE TABLE IF NOT EXISTS public.class_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id),
    class_id UUID NOT NULL REFERENCES public.classes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Class section years
CREATE TABLE IF NOT EXISTS public.class_section_years (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id),
    section_id UUID NOT NULL REFERENCES public.class_sections(id) ON DELETE CASCADE,
    academic_year TEXT NOT NULL,
    class_teacher_id UUID,
    capacity INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Subjects
CREATE TABLE IF NOT EXISTS public.subjects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id),
    name TEXT NOT NULL,
    code TEXT,
    category TEXT NOT NULL,
    is_special_activity BOOLEAN NOT NULL DEFAULT false,
    assessment_type TEXT NOT NULL DEFAULT 'marks',
    max_marks INTEGER,
    pass_marks INTEGER,
    from_grade INTEGER NOT NULL DEFAULT 1,
    to_grade INTEGER NOT NULL DEFAULT 12,
    periods_per_week INTEGER,
    color TEXT NOT NULL DEFAULT 'slate',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    display_order INTEGER NOT NULL DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    deleted_by UUID
);

-- Staff
CREATE TABLE IF NOT EXISTS public.staff (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id) ON DELETE CASCADE,
    user_id UUID,
    employee_id TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT,
    preferred_name TEXT,
    father_name TEXT,
    dob DATE,
    gender TEXT,
    blood_group TEXT,
    marital_status TEXT,
    nationality TEXT DEFAULT 'Indian',
    religion TEXT,
    caste_category TEXT,
    sub_caste TEXT,
    aadhar_number TEXT,
    pan_number TEXT,
    profile_photo_path TEXT,
    personal_mobile TEXT,
    alternate_mobile TEXT,
    emergency_contact_name TEXT,
    emergency_contact_relationship TEXT,
    emergency_contact_phone TEXT,
    personal_email TEXT,
    official_email TEXT,
    whatsapp_number TEXT,
    preferred_language TEXT NOT NULL DEFAULT 'en',
    current_address JSONB NOT NULL DEFAULT '{}',
    permanent_address JSONB NOT NULL DEFAULT '{}',
    staff_category TEXT NOT NULL,
    designation TEXT,
    department TEXT,
    employment_type TEXT NOT NULL,
    probation_period_months INTEGER,
    contract_start DATE,
    contract_end DATE,
    date_of_joining DATE NOT NULL,
    date_of_confirmation DATE,
    work_location TEXT,
    reporting_manager_id UUID,
    shift_timing TEXT,
    weekly_off_days TEXT[] NOT NULL DEFAULT '{}',
    pay_grade TEXT,
    ctc DECIMAL(10,2),
    in_hand_salary DECIMAL(10,2),
    pf_account_number TEXT,
    uan TEXT,
    esi_number TEXT,
    bank_name TEXT,
    bank_account_number TEXT,
    ifsc TEXT,
    bank_account_holder_name TEXT,
    has_system_access BOOLEAN NOT NULL DEFAULT true,
    blacklist BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'active',
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    deleted_by UUID
);

-- Staff qualifications
CREATE TABLE IF NOT EXISTS public.staff_qualifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id),
    staff_id UUID NOT NULL REFERENCES public.staff(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    qualification_name TEXT NOT NULL,
    specialization TEXT,
    university TEXT,
    institution TEXT,
    year_of_passing INTEGER,
    grade TEXT,
    mode TEXT,
    certificate_doc_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Staff certifications
CREATE TABLE IF NOT EXISTS public.staff_certifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id),
    staff_id UUID NOT NULL REFERENCES public.staff(id),
    cert_type TEXT NOT NULL,
    cert_name TEXT,
    cert_number TEXT,
    issue_date DATE,
    validity_date DATE,
    level TEXT,
    doc_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Staff experience
CREATE TABLE IF NOT EXISTS public.staff_experience (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id),
    staff_id UUID NOT NULL REFERENCES public.staff(id),
    institution TEXT NOT NULL,
    designation TEXT,
    from_date DATE,
    to_date DATE,
    subjects_taught TEXT[],
    reason_for_leaving TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Students
CREATE TABLE IF NOT EXISTS public.students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    surname TEXT,
    date_of_birth DATE,
    class TEXT,
    section TEXT,
    class_section_id UUID REFERENCES public.class_sections(id) ON DELETE SET NULL,
    roll_number TEXT,
    registration_number TEXT,
    father_name TEXT,
    father_phone TEXT,
    father_email TEXT,
    father_occupation TEXT,
    father_qualification TEXT,
    father_annual_income TEXT,
    father_office_address TEXT,
    mother_name TEXT,
    mother_phone TEXT,
    mother_email TEXT,
    mother_occupation TEXT,
    mother_qualification TEXT,
    mother_annual_income TEXT,
    mother_office_address TEXT,
    aadhaar_number TEXT,
    place_of_birth TEXT,
    city TEXT,
    district TEXT,
    state TEXT,
    disability TEXT,
    caste TEXT,
    mother_tongue TEXT,
    category TEXT,
    religion TEXT,
    last_school TEXT,
    admission_class TEXT,
    blood_group TEXT,
    identification_mark TEXT,
    photo_path TEXT,
    status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Student addresses
CREATE TABLE IF NOT EXISTS public.student_addresses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id),
    student_id UUID NOT NULL REFERENCES public.students(id) ON DELETE CASCADE,
    address_line TEXT,
    city TEXT,
    district TEXT,
    state TEXT,
    pincode TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Admission applications
CREATE TABLE IF NOT EXISTS public.admission_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id UUID NOT NULL REFERENCES public.schools(id) ON DELETE CASCADE,
    student_name TEXT NOT NULL,
    date_of_birth DATE,
    class_applied TEXT NOT NULL,
    section_applied TEXT,
    parent_name TEXT NOT NULL,
    parent_phone TEXT,
    parent_email TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'inquiry',
    form_number TEXT,
    date_of_issue DATE,
    registration_number TEXT,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
