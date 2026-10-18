"""Execute the real PowerShell adapter/report writer against CLI wire fixtures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/Test-Deployment.ps1"
TENANT = "00000000-0000-0000-0000-000000000001"
SUB = "00000000-0000-0000-0000-000000000002"
PRINCIPAL = "00000000-0000-0000-0000-000000000003"
PREFIX = f"/subscriptions/{SUB}/resourceGroups/rg-test/providers/"
FUNCTION = PREFIX + "Microsoft.Web/sites/func-test"
STORAGE = PREFIX + "Microsoft.Storage/storageAccounts/sttest"
SECRET = "synthetic-provider-secret-never-export"
ROLES = ["b7e6dc6d-f1e8-4753-8033-0f276bb0955b", "974c5e8b-45b9-4653-ba55-5f855dd0fb88", "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3"]
CREDENTIAL_ENV = ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_CLIENT_CERTIFICATE_PATH", "AZURE_CLIENT_CERTIFICATE_PASSWORD", "AZURE_CLIENT_SEND_CERTIFICATE_CHAIN", "AZURE_FEDERATED_TOKEN_FILE", "AZURE_AUTHORITY_HOST", "AZURE_USERNAME", "AZURE_PASSWORD")


def healthy():
    return {
        "account": {"tenantId": TENANT, "id": SUB, "state": "Enabled", "environmentName": "AzureCloud"},
        "function": {"id": FUNCTION, "kind": "functionapp,linux", "identity": {"type": "SystemAssigned", "principalId": PRINCIPAL}, "properties": {"functionAppConfig": {"runtime": {"name": "python", "version": "3.11"}, "deployment": {"storage": {"type": "blobContainer", "value": "https://sttest.blob.core.windows.net/deployment", "authentication": {"type": "SystemAssignedIdentity"}}}}}},
        "storage": {"id": STORAGE, "properties": {"allowSharedKeyAccess": False, "allowBlobPublicAccess": False, "supportsHttpsTrafficOnly": True, "minimumTlsVersion": "TLS1_2"}},
        "settings": [{"name": "AzureWebJobsStorage__accountName", "value": "sttest"}, {"name": "AzureWebJobsStorage__credential", "value": "managedidentity"}] + [{"name": f"AzureWebJobsStorage__{s}ServiceUri", "value": f"https://sttest.{s}.core.windows.net"} for s in ("blob", "queue", "table")] + [{"name": "TEAMS_WEBHOOK_URL", "value": SECRET}],
        "roles": [{"principalId": PRINCIPAL, "scope": STORAGE, "roleDefinitionId": f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{r}", "condition": None} for r in ROLES],
        "audit": {"PartitionKey": "run", "RowKey": "latest"},
    }


STUB = '''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
data = json.loads(Path(os.environ["CPC_WIRE_FIXTURE"]).read_text())
assert not any(name in os.environ for name in data["credentialEnv"])
assert os.environ.get("AZURE_CONFIG_DIR") == data["configDir"]
with open(os.environ["CPC_WIRE_CALLS"], "a") as log:
    log.write(json.dumps({"args": args, "storageEnv": [k for k in os.environ if k.startswith("AZURE_STORAGE_")]}) + "\\n")
if args[:2] == ["account", "show"]: key = "account"
elif args[:2] == ["resource", "show"]:
    assert args[args.index("--include-response-body") + 1] == "true"
    key = "function" if "/Microsoft.Web/sites/" in args[args.index("--ids") + 1] else "storage"
elif args[:4] == ["functionapp", "config", "appsettings", "list"]: key = "settings"
elif args[:3] == ["role", "assignment", "list"]:
    assert "--assignee-object-id" in args and "--assignee" not in args
    assert "--include-inherited" not in args and "--all" not in args
    for name in ("--fill-principal-name", "--fill-role-definition-name"):
        assert args[args.index(name) + 1] == "false"
    key = "roles"
elif args[:3] == ["storage", "entity", "show"]:
    assert args[args.index("--auth-mode") + 1] == "login"
    assert args[args.index("--select") + 1:args.index("--subscription")] == ["PartitionKey", "RowKey"]
    assert args[args.index("--row-key") + 1] == "latest"
    assert args[args.index("--table-endpoint") + 1] == "https://sttest.table.core.windows.net"
    key = "audit"
else: raise AssertionError("unexpected command")
if key != "account": assert args[args.index("--subscription") + 1] == data["account"]["id"]
if data.get("fail") == key:
    print("synthetic-provider-secret-never-export", file=sys.stderr); sys.exit(7)
if data.get("malformed") == key: print("{synthetic-provider-secret-never-export"); sys.exit(0)
print(json.dumps(data[key]))
'''


class DeploymentWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pwsh = shutil.which("pwsh")
        if not cls.pwsh: raise RuntimeError("PowerShell 7.6+ is required")

    def run_wrapper(self, fixture=None, mode="verify", table=False, override=None):
        with tempfile.TemporaryDirectory(prefix="cpc wire ") as directory:
            temp = Path(directory)
            fixture = fixture or healthy()
            fixture["credentialEnv"] = CREDENTIAL_ENV
            fixture["configDir"] = str(temp / "cached-cli-profile")
            (temp / "fixture.json").write_text(json.dumps(fixture))
            (temp / "wire.py").write_text(STUB)
            launcher = temp / ("az.cmd" if os.name == "nt" else "az")
            if os.name == "nt":
                launcher.write_text(f'@echo off\n"{sys.executable}" "{temp / "wire.py"}" %*\n', encoding="utf-8")
            else:
                launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{temp / "wire.py"}" "$@"\n'); launcher.chmod(0o700)
            env = os.environ.copy()
            env.update(PATH=str(temp) + os.pathsep + env.get("PATH", ""), CPC_WIRE_FIXTURE=str(temp / "fixture.json"), CPC_WIRE_CALLS=str(temp / "calls.jsonl"))
            for key in ("KEY", "CONNECTION_STRING", "SAS_TOKEN", "ACCOUNT", "SERVICE_ENDPOINT", "AUTH_MODE"):
                env["AZURE_STORAGE_" + key] = SECRET
            for key in CREDENTIAL_ENV: env[key] = SECRET
            env["AZURE_CONFIG_DIR"] = fixture["configDir"]
            relative = "reports/wire-" + uuid.uuid4().hex + ".json"
            args = [self.pwsh, "-NoLogo", "-NoProfile", "-File", str(SCRIPT), "-OutputPath", relative]
            if mode == "verify":
                params = {"TenantId": TENANT, "SubscriptionId": SUB, "ResourceGroup": "rg-test", "FunctionAppName": "func-test", "StorageAccountName": "sttest"}
                params.update(override or {})
                for key, value in params.items(): args.extend(["-" + key, value])
                if table: args.extend(["-TableName", "AuditState"])
            else: args.append("-" + mode)
            report_path = ROOT / relative
            try:
                result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
                report = json.loads(report_path.read_text()) if report_path.exists() else None
                log = temp / "calls.jsonl"
                calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
                self.assertNotIn(SECRET, result.stdout + result.stderr + json.dumps(report))
                return result, report, calls
            finally: report_path.unlink(missing_ok=True)

    def test_plan_and_delivery_refusal_make_zero_cli_calls(self):
        for mode, code, outcome in (("Plan", 0, "planned"), ("TestDelivery", 1, "failed")):
            with self.subTest(mode=mode):
                result, report, calls = self.run_wrapper(mode=mode)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(report["outcome"], outcome); self.assertEqual(calls, [])

    def test_healthy_full_sequence_and_opt_in_audit_use_only_reads(self):
        result, report, calls = self.run_wrapper(table=True)
        self.assertEqual(result.returncode, 0, result.stderr + json.dumps(report))
        self.assertEqual(report["outcome"], "passed"); self.assertEqual(len(calls), 6)
        self.assertTrue(all(c["status"] == "pass" for c in report["checks"]))
        self.assertTrue(all(not c["storageEnv"] for c in calls))

    def test_audit_requires_explicit_table(self):
        result, report, calls = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["checks"][-1]["status"], "skipped"); self.assertEqual(len(calls), 5)

    def test_context_mismatch_disabled_and_cloud_gate_all_target_reads(self):
        for field, value in (("tenantId", SUB), ("id", TENANT), ("state", "Disabled"), ("environmentName", "AzureUSGovernment")):
            fixture = healthy(); fixture["account"][field] = value
            result, report, calls = self.run_wrapper(fixture, table=True)
            self.assertEqual(result.returncode, 1); self.assertEqual(report["checks"][0]["status"], "fail")
            self.assertEqual(len(calls), 1)

    def test_cli_denial_and_malformed_json_produce_safe_failed_reports(self):
        for failure in ("fail", "malformed"):
            for target in ("account", "function", "storage", "settings", "roles", "audit"):
                with self.subTest(failure=failure, target=target):
                    fixture = healthy(); fixture[failure] = target
                    result, report, _ = self.run_wrapper(fixture, table=True)
                    self.assertEqual(result.returncode, 1, result.stdout); self.assertEqual(report["outcome"], "failed")

    def test_bad_runtime_identity_storage_and_resource_ids_fail(self):
        variants = []
        for target in ("function", "storage"):
            fixture = healthy(); fixture[target]["id"] += "-other"; variants.append(fixture)
        fixture = healthy(); fixture["function"]["properties"]["functionAppConfig"]["runtime"]["version"] = "3.10"; variants.append(fixture)
        fixture = healthy(); fixture["function"]["identity"]["principalId"] = "not-an-object-id"; variants.append(fixture)
        fixture = healthy(); fixture["function"]["kind"] = "functionapp,linux,container"; variants.append(fixture)
        for field, value in (("allowSharedKeyAccess", True), ("allowSharedKeyAccess", "false"), ("allowBlobPublicAccess", True), ("supportsHttpsTrafficOnly", False), ("minimumTlsVersion", "TLS1_0")):
            fixture = healthy(); fixture["storage"]["properties"][field] = value; variants.append(fixture)
        for fixture in variants:
            result, report, _ = self.run_wrapper(fixture)
            self.assertEqual(result.returncode, 1); self.assertEqual(report["outcome"], "failed")

    def test_endpoint_spoofing_connection_string_and_identity_override_fail(self):
        for key, value in (("AzureWebJobsStorage__blobServiceUri", "https://sttest.blob.evil.example"), ("AzureWebJobsStorage", SECRET), ("AzureWebJobsStorage__clientId", PRINCIPAL)):
            fixture = healthy(); fixture["settings"] = [s for s in fixture["settings"] if s["name"] != key] + [{"name": key, "value": value}]
            result, report, _ = self.run_wrapper(fixture)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(next(c for c in report["checks"] if c["id"] == "configuration.host-storage")["status"], "fail")
        for url in ("https://sttest.blob.evil.example/deployment", "https://sttest.blob.core.windows.net/deployment?sig=" + SECRET):
            fixture = healthy(); fixture["function"]["properties"]["functionAppConfig"]["deployment"]["storage"]["value"] = url
            result, _, _ = self.run_wrapper(fixture); self.assertEqual(result.returncode, 1)

    def test_conditional_wrong_scope_principal_and_missing_role_fail(self):
        for key, value in (("condition", "conditional"), ("scope", STORAGE + "/blobServices/default"), ("principalId", TENANT), ("roleDefinitionId", "wrong-role")):
            fixture = healthy(); fixture["roles"][0][key] = value
            result, _, _ = self.run_wrapper(fixture); self.assertEqual(result.returncode, 1)

    def test_missing_role_condition_is_unconditional_and_nonstring_condition_fails(self):
        fixture = healthy()
        for role in fixture["roles"]:
            role.pop("condition")
        result, report, _ = self.run_wrapper(fixture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(next(c for c in report["checks"] if c["id"] == "identity.storage-roles")["status"], "pass")

        for unconditional in ("", " \t"):
            with self.subTest(unconditional=unconditional):
                fixture = healthy()
                for role in fixture["roles"]:
                    role["condition"] = unconditional
                result, report, _ = self.run_wrapper(fixture)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(next(c for c in report["checks"] if c["id"] == "identity.storage-roles")["status"], "pass")

        for malformed in (7, False, [], [""], [None], [" "], {"operator": "StringEquals"}):
            with self.subTest(malformed=malformed):
                fixture = healthy(); fixture["roles"][0]["condition"] = malformed
                result, report, _ = self.run_wrapper(fixture)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(next(c for c in report["checks"] if c["id"] == "identity.storage-roles")["status"], "fail")

    def test_invalid_inputs_rejected_before_cli(self):
        for key, value in (("TenantId", "not-guid"), ("ResourceGroup", "%COMSPEC%"), ("FunctionAppName", "x&whoami"), ("StorageAccountName", "bad/account")):
            result, _, calls = self.run_wrapper(override={key: value})
            self.assertNotEqual(result.returncode, 0); self.assertEqual(calls, [])

    def test_vendor_files_match_immutable_lock_hashes(self):
        lock = json.loads((ROOT / "azd-components.lock.json").read_text())
        for component in lock["components"]:
            for file in component["files"]:
                self.assertEqual(hashlib.sha256((ROOT / file["target"]).read_bytes()).hexdigest(), file["sha256"])


if __name__ == "__main__": unittest.main()
