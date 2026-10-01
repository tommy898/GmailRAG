import copy
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.database_security import (
    APPLICATION_TABLES,
    inspect_database_security,
    main,
    security_violations,
)


def safe_snapshot() -> dict:
    return {
        "tables": [{"table_name": name, "rls_enabled": True,
                    "runtime_owns_table": False} for name in sorted(APPLICATION_TABLES)],
        "client_privileges": [{"role": role, "table_name": name,
                               "table_access": False, "column_access": False}
                              for name in APPLICATION_TABLES
                              for role in ("anon", "authenticated")],
        "client_roles": [{"role": role, "bypasses_rls": False,
                          "can_create": False, "admin_member": False}
                         for role in ("anon", "authenticated")],
        "client_policies": [], "exposed_functions": [], "defaults": [],
        "public_function_default": False,
        "auth_trigger": {"security_definer": True, "fixed_search_path": True,
                         "auth_can_execute": True, "trigger_enabled": True},
        "runtime": {"role": "restricted_runtime", "elevated": False,
                    "can_create": False, "can_read_auth_users": False},
    }


class DatabaseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = safe_snapshot()

    def test_locked_down_snapshot_passes_including_runtime(self):
        self.assertEqual(security_violations(self.snapshot, require_runtime_role=True), [])

    def test_missing_table_fails(self):
        self.snapshot["tables"].pop()
        self.assertTrue(security_violations(self.snapshot))

    def test_disabled_rls_fails(self):
        self.snapshot["tables"][0]["rls_enabled"] = False
        self.assertTrue(security_violations(self.snapshot))

    def test_effective_table_or_column_privilege_fails(self):
        for field in ("table_access", "column_access"):
            with self.subTest(field=field):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["client_privileges"][0][field] = True
                self.assertTrue(security_violations(snapshot))

    def test_client_role_membership_or_ddl_or_bypass_fails(self):
        for field in ("bypasses_rls", "can_create", "admin_member"):
            with self.subTest(field=field):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["client_roles"][0][field] = True
                self.assertTrue(security_violations(snapshot))

    def test_missing_supabase_roles_fails(self):
        self.snapshot["client_roles"].pop()
        self.assertTrue(security_violations(self.snapshot))

    def test_client_policy_or_security_definer_fails(self):
        for field in ("client_policies", "exposed_functions"):
            with self.subTest(field=field):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot[field] = [{"name": "unsafe"}]
                self.assertTrue(security_violations(snapshot))

    def test_future_object_grants_fail(self):
        for field, value in (("defaults", [{"privilege_type": "TRUNCATE"}]),
                             ("public_function_default", True)):
            with self.subTest(field=field):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot[field] = value
                self.assertTrue(security_violations(snapshot))

    def test_auth_trigger_security_is_required(self):
        for field in self.snapshot["auth_trigger"]:
            with self.subTest(field=field):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["auth_trigger"][field] = False
                self.assertTrue(security_violations(snapshot))

    def test_admin_runtime_requires_strict_deployment_check(self):
        self.snapshot["runtime"]["elevated"] = True
        self.assertEqual(security_violations(self.snapshot), [])
        self.assertTrue(security_violations(self.snapshot, require_runtime_role=True))

    def test_ownership_ddl_and_auth_access_fail_runtime_check(self):
        self.snapshot["tables"][0]["runtime_owns_table"] = True
        self.assertTrue(security_violations(self.snapshot, require_runtime_role=True))
        for field in ("can_create", "can_read_auth_users"):
            with self.subTest(field=field):
                snapshot = safe_snapshot()
                snapshot["runtime"][field] = True
                self.assertTrue(security_violations(snapshot, require_runtime_role=True))

    def test_inspector_only_queries_catalogs_and_permissions(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {"public_execute": False}
        inspect_database_security(connection)
        for call in connection.execute.call_args_list:
            query = " ".join(call.args[0].lower().split())
            self.assertTrue(query.startswith("select "))
            self.assertNotIn("from gmail_accounts", query)
            self.assertNotIn("from public.gmail_accounts", query)
            self.assertNotIn("from emails", query)
            self.assertNotIn("access_token_encrypted", query)
            self.assertNotIn("refresh_token_encrypted", query)

    @patch("app.database_security.load_dotenv")
    @patch("app.database_security.get_connection")
    def test_cli_sanitizes_connection_errors(self, get_connection, load_environment):
        get_connection.side_effect = RuntimeError("postgresql://user:private-password@host")
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 1)
        self.assertNotIn("private-password", output.getvalue())

    @patch("app.database_security.load_dotenv")
    @patch("app.database_security.inspect_database_security")
    @patch("app.database_security.get_connection")
    def test_cli_is_read_only_and_reports_strict_failure(self, get_connection, inspect, load_environment):
        inspect.return_value = self.snapshot
        self.snapshot["runtime"]["elevated"] = True
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--require-runtime-role"]), 1)
        conn = get_connection.return_value.__enter__.return_value
        conn.execute.assert_called_once_with("set transaction read only")


class PermissionMigrationTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2]
        self.migration = (root / "backend/db/migrations/202609300001_harden_client_permissions.sql").read_text()
        self.schema = (root / "backend/db/schema.sql").read_text()

    def test_migration_and_fresh_schema_revoke_every_application_table(self):
        for source in (self.migration, self.schema):
            with self.subTest(source="migration" if source is self.migration else "schema"):
                block = source.split("revoke all privileges on table", 1)[1].split(";", 1)[0]
                for name in APPLICATION_TABLES:
                    self.assertIn(f"public.{name}", block)
                self.assertIn("from public, anon, authenticated", block)

    def test_migration_changes_permissions_only_not_rows_or_keys(self):
        statements = "\n".join(line for line in self.migration.splitlines()
                               if not line.lstrip().startswith("--")).lower()
        for forbidden in ("delete from", "truncate table", "drop table", "insert into",
                          "update public.", "disable row level security", "password"):
            self.assertNotIn(forbidden, statements)
        self.assertTrue(statements.strip().startswith("begin;"))
        self.assertTrue(statements.strip().endswith("commit;"))

    def test_future_table_grants_and_auth_trigger_are_hardened(self):
        for source in (self.migration, self.schema):
            normalized = " ".join(source.split())
            self.assertIn("revoke all privileges on tables from public, anon, authenticated", normalized)
            self.assertIn("grant execute on function public.handle_new_user() to supabase_auth_admin", normalized)
            self.assertIn("revoke execute on functions from public", normalized)
        self.assertIn("set search_path = ''", self.schema)


if __name__ == "__main__":
    unittest.main()
