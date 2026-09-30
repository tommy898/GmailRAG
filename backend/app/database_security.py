"""Read-only deployment checks for the application's database boundary.

Run from backend/: python -m app.database_security
Use --require-runtime-role when testing the eventual production DB credential.
Queries inspect PostgreSQL catalogs/permissions, never email or token contents.
"""

import argparse
import json

from dotenv import load_dotenv
from psycopg.rows import dict_row

from app.db import get_connection


APPLICATION_TABLES = frozenset({
    "profiles", "gmail_accounts", "emails", "email_chunks", "email_embeddings",
    "sync_jobs", "queries", "answers", "answer_sources",
})


def inspect_database_security(conn) -> dict:
    conn.row_factory = dict_row
    tables = conn.execute("""
        select c.relname as table_name, c.relrowsecurity as rls_enabled,
            pg_has_role(current_user, c.relowner, 'MEMBER') as runtime_owns_table
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind in ('r', 'p')
        order by c.relname
    """).fetchall()
    client_privileges = conn.execute("""
        select c.relname as table_name, r.rolname as role,
            has_table_privilege(r.oid, c.oid,
                'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                or case when current_setting('server_version_num')::int >= 170000
                    then has_table_privilege(r.oid, c.oid, 'MAINTAIN')
                    else false end as table_access,
            has_any_column_privilege(r.oid, c.oid,
                'SELECT,INSERT,UPDATE,REFERENCES') as column_access
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        cross join pg_roles r
        where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm')
            and r.rolname in ('anon', 'authenticated')
        order by c.relname, r.rolname
    """).fetchall()
    client_roles = conn.execute("""
        select rolname as role, rolbypassrls or rolsuper as bypasses_rls,
            has_schema_privilege(oid, 'public', 'CREATE') as can_create,
            pg_has_role(oid, 'postgres', 'MEMBER') as admin_member
        from pg_roles where rolname in ('anon', 'authenticated')
    """).fetchall()
    client_policies = conn.execute("""
        select tablename as table_name, policyname
        from pg_policies where schemaname = 'public'
            and roles && array['public', 'anon', 'authenticated']::name[]
    """).fetchall()
    exposed_functions = conn.execute("""
        select p.oid::regprocedure::text as function_name
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.prosecdef
            and (p.proname = 'handle_new_user'
                or p.prorettype not in ('trigger'::regtype, 'event_trigger'::regtype))
            and (has_function_privilege('anon', p.oid, 'EXECUTE')
                or has_function_privilege('authenticated', p.oid, 'EXECUTE'))
    """).fetchall()
    defaults = conn.execute("""
        select d.defaclobjtype::text as object_type, a.privilege_type
        from pg_default_acl d
        left join pg_namespace n on n.oid = d.defaclnamespace
        cross join lateral aclexplode(d.defaclacl) a
        where d.defaclrole = 'postgres'::regrole
            and (n.nspname = 'public' or d.defaclnamespace = 0)
            and (a.grantee = 0 or a.grantee in
                ('anon'::regrole::oid, 'authenticated'::regrole::oid))
    """).fetchall()
    function_defaults = conn.execute("""
        select exists (
            select 1 from aclexplode(coalesce(
                (select defaclacl from pg_default_acl
                    where defaclrole = 'postgres'::regrole
                        and defaclnamespace = 0 and defaclobjtype = 'f'),
                acldefault('f', 'postgres'::regrole::oid)
            )) a where a.grantee = 0 and a.privilege_type = 'EXECUTE'
        ) as public_execute
    """).fetchone()
    auth_trigger = conn.execute("""
        select p.prosecdef as security_definer,
            p.proconfig @> array['search_path=""']::text[] as fixed_search_path,
            has_function_privilege('supabase_auth_admin', p.oid, 'EXECUTE')
                as auth_can_execute,
            exists (select 1 from pg_trigger t
                where t.tgrelid = (select c.oid from pg_class c
                    join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'auth' and c.relname = 'users')
                    and t.tgfoid = p.oid
                    and t.tgname = 'on_auth_user_created'
                    and t.tgenabled in ('O', 'A')) as trigger_enabled
        from pg_proc p where p.oid = 'public.handle_new_user()'::regprocedure
    """).fetchone()
    runtime = conn.execute("""
        select current_user as role,
            exists (select 1 from pg_roles r
                where (r.rolsuper or r.rolbypassrls or r.rolcreaterole
                    or r.rolcreatedb or r.rolreplication)
                    and pg_has_role(current_user, r.oid, 'MEMBER')) as elevated,
            has_schema_privilege(current_user, 'public', 'CREATE') as can_create,
            has_table_privilege(current_user,
                (select c.oid from pg_class c
                    join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'auth' and c.relname = 'users'), 'SELECT')
                as can_read_auth_users
    """).fetchone()
    return {
        "tables": tables, "client_privileges": client_privileges,
        "client_roles": client_roles, "client_policies": client_policies,
        "exposed_functions": exposed_functions, "defaults": defaults,
        "public_function_default": function_defaults["public_execute"],
        "auth_trigger": auth_trigger, "runtime": runtime,
    }


def security_violations(snapshot: dict, *, require_runtime_role: bool = False) -> list[str]:
    violations = []
    found = {row["table_name"] for row in snapshot["tables"]}
    for name in sorted(APPLICATION_TABLES - found):
        violations.append(f"Missing application table: {name}")
    for row in snapshot["tables"]:
        if not row["rls_enabled"]:
            violations.append(f"RLS disabled: {row['table_name']}")
        if require_runtime_role and row["runtime_owns_table"]:
            violations.append(f"Runtime can assume table owner: {row['table_name']}")
    for row in snapshot["client_privileges"]:
        if row["table_access"] or row["column_access"]:
            violations.append(f"Client privilege remains: {row['role']} on {row['table_name']}")
    found_roles = {row["role"] for row in snapshot["client_roles"]}
    if found_roles != {"anon", "authenticated"}:
        violations.append("Expected Supabase client roles are missing")
    for row in snapshot["client_roles"]:
        if row["bypasses_rls"] or row["can_create"] or row["admin_member"]:
            violations.append(f"Client role has elevated access: {row['role']}")
    if snapshot["client_policies"]:
        violations.append("Browser-access RLS policies exist on backend-only tables")
    if snapshot["exposed_functions"]:
        violations.append("Client-callable security-definer function exists")
    if snapshot["defaults"] or snapshot["public_function_default"]:
        violations.append("Future objects can inherit client/PUBLIC permissions")
    trigger = snapshot["auth_trigger"]
    if not trigger or not all(trigger.values()):
        violations.append("Supabase profile-creation trigger is not safely configured")
    runtime = snapshot["runtime"]
    if require_runtime_role and (
        runtime["elevated"] or runtime["can_create"] or runtime["can_read_auth_users"]
    ):
        violations.append("Production database credential is privileged")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only database security audit")
    parser.add_argument("--require-runtime-role", action="store_true")
    arguments = parser.parse_args(argv)
    load_dotenv()
    try:
        with get_connection() as conn:
            conn.execute("set transaction read only")
            snapshot = inspect_database_security(conn)
        violations = security_violations(
            snapshot, require_runtime_role=arguments.require_runtime_role,
        )
    except Exception as exc:
        # Driver errors may contain credentials/URLs. Never render them.
        print(f"Database security audit failed: {type(exc).__name__}")
        return 1
    print(json.dumps({
        "passed": not violations,
        "public_tables_checked": len(snapshot["tables"]),
        "violations": violations,
        "runtime_role": snapshot["runtime"]["role"],
        "runtime_is_privileged": snapshot["runtime"]["elevated"],
        "runtime_credential_verified": arguments.require_runtime_role and not violations,
    }, indent=2))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
