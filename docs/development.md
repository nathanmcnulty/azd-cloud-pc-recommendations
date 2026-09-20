# Development and validation

## Local checks

From the repository root:

```powershell
.\scripts\validate.ps1
.\scripts\Test-LocalFixtures.ps1
```

The validation script checks Bicep compilation, PowerShell syntax, Python compilation, and the standard-library unit tests. The fixture command evaluates four representative Cloud PCs across two passes so the provisioning and stale-device grace periods can activate, then prints the final report to stdout. It forces dry-run and notifications off, so it does not contact Azure, Graph, Teams, or Storage.

The Function project declares its runtime dependencies in [requirements.txt](../src/cloud-pc-monitor/requirements.txt). To run the Function locally, create a local-only `local.settings.json` from the example and install those dependencies into a virtual environment. Never commit that file or a real webhook URL.

## Fixture coverage

The fixtures cover:

- a provisioned Cloud PC with an old login;
- a failed Cloud PC with status detail;
- a provisioned Cloud PC with an old Intune sync;
- a healthy Cloud PC.

The rule tests run the same state through two observations so the provisioning and stale-device grace periods are exercised. The notification test verifies stable fingerprint deduplication.

## Live proof remains separate

Local tests prove parsing, rule behavior, retries, state transitions, and payload shape. They do not prove:

- tenant licensing or Microsoft Graph admin consent;
- the selected managed identity's application-role assignments;
- the current tenant's Graph response shape or throttling behavior;
- Teams workflow authorization or recipient-visible delivery;
- Azure RBAC propagation, Function deployment, or Blob/Table data-plane access.

Those require a deliberately scoped Azure environment and a human review of the selected tenant, subscription, resource group, identities, permissions, thresholds, and notification destination.
