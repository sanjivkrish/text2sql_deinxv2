import re
from core.models.sql import SQLResult

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "truncate",
    "alter", "create", "grant", "revoke", "union",
}

# Internal/auth tables that must never appear in user-facing queries
BLOCKED_TABLES = {
    "profiles",
    "school_admin_credentials_mvp",
    "school_memberships",
    "role_feature_permissions",
    "feature_catalog",
    "school_feature_settings",
    "parent_form_tokens",
    "staff_audit_log",
    "staff_employee_id_sequence",
}

class OutputValidator:
    def validate(self, result: SQLResult) -> dict:
        sql = result.sql.strip()
        warnings: list[str] = list(result.warnings)
        issues: list[str] = []

        # Rule 1: Must start with SELECT
        if not sql.upper().lstrip().startswith("SELECT"):
            issues.append("Rule 1: SQL must start with SELECT")

        # Rule 2: Must have FROM
        if "FROM" not in sql.upper():
            issues.append("Rule 2: SQL must contain FROM clause")

        # Rule 3: Must have LIMIT as a clause keyword (not inside a string literal)
        stripped_for_limit = re.sub(r"'[^']*'", "", sql)
        if not re.search(r'\bLIMIT\s+\d+', stripped_for_limit, re.IGNORECASE):
            issues.append("Rule 3: SQL must contain LIMIT clause")

        # Rule 4: No semicolons (prevent statement stacking)
        if ";" in sql:
            issues.append("Rule 4: SQL must not contain semicolons")

        # Rule 5: No forbidden DML/DDL keywords (strip quoted literals first)
        # Use '? to make closing quote optional so unterminated literals are also stripped
        stripped = re.sub(r"'[^']*'?", "", sql)
        tokens = set(re.findall(r'\b\w+\b', stripped.lower()))
        bad_tokens = tokens & FORBIDDEN_KEYWORDS
        if bad_tokens:
            issues.append(f"Rule 5: Forbidden keywords found: {bad_tokens}")

        # Rule 6: No comment sequences
        if "--" in sql or "/*" in sql:
            issues.append("Rule 6: SQL must not contain comment sequences")

        # Rule 8: students.class is a reserved-keyword column reference — reject it
        # The students table has no 'class' column; class-based queries must join through class_sections → classes
        if re.search(r'\bstudents\s*\.\s*class\b', sql, re.IGNORECASE):
            issues.append("Rule 8: students.class is invalid — 'class' is a reserved SQL keyword and not a column on students; join through class_sections and classes instead")

        # Rule 9: No internal/auth tables
        sql_no_literals = re.sub(r"'[^']*'", "", sql)
        referenced_tables = set(re.findall(r'\b([a-z_][a-z0-9_]*)\b', sql_no_literals.lower()))
        blocked_hit = referenced_tables & BLOCKED_TABLES
        if blocked_hit:
            issues.append(f"Rule 9: Query references internal tables not allowed in user queries: {blocked_hit}")

        # Rule 7: Low confidence warning (non-blocking)
        if result.confidence_score < 0.5:
            warnings.append(f"Rule 7: Low confidence score ({result.confidence_score:.2f}) — review SQL before use")

        return {
            "is_valid": len(issues) == 0,
            "warnings": warnings + issues,
        }
