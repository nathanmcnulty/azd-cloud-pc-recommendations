# Cloud PC operational recommendations and alerts

This private Azure Developer CLI (`azd`) template turns Windows 365 and Cloud PC operational signals into administrator actions. It complements the recommendations experience in Intune; it does not rebuild that dashboard.

The first milestone is a scheduled, dry-run-by-default monitor for:

- unused or underutilized Cloud PCs;
- Cloud PCs stuck in a provisioning failure state;
- unhealthy or stale Cloud PCs and their Intune managed-device state.

It keeps durable alert fingerprints, observation grace periods, acknowledgements, notification history, and compact JSON audit exports. Remediation is deliberately not implemented in this milestone, and no Cloud PC is deleted, reprovisioned, resized, or otherwise changed.

## What is deployed

- A Python 3.11 Azure Function with a timer trigger.
- A system-assigned managed identity.
- A dedicated Storage account using identity-based Function host storage, Table Storage state, and private Blob audit exports.
- Application Insights backed by Log Analytics.
- A post-provision bootstrap that can grant only the Microsoft Graph application roles required by the selected collection mode.

Teams delivery uses the supported Microsoft Teams Workflows **When a Teams webhook request is received** trigger. Create the workflow separately, then provide its URL as the sensitive `TEAMS_WEBHOOK_URL` azd value. See [configuration](docs/configuration.md).

## Safe local validation

The repository includes deterministic fixtures and a validation command that does not contact Azure or Microsoft Graph:

```powershell
.\scripts\validate.ps1
.\scripts\Test-LocalFixtures.ps1
```

The fixture run is always dry-run and never sends a webhook.

## Deploy

Install Azure Developer CLI 1.23 or later, Azure CLI, and PowerShell 7. Use a normal cached Azure CLI/azd or browser sign-in. Do not put a Teams URL, token, or production configuration in source control.

```powershell
# From a clone of this repository, skip `azd init`. Use `azd init -t ...` only
# when starting from an empty directory and selecting this template.
azd auth login
azd env new cloud-pc-monitor
azd env set AZURE_LOCATION eastus
azd env set DRY_RUN true
azd up
```

The post-provision hook assigns `CloudPC.Read.All` and `DeviceManagementManagedDevices.Read.All` to the Function identity when `GRAPH_ROLE_ASSIGNMENTS_ENABLED=true`. Microsoft Graph administrator consent and the operator's authority to create those assignments remain tenant decisions; see [identity and authentication](docs/identity-and-authentication.md).

The optional recommendation report is disabled by default. Enabling `CLOUD_PC_RECOMMENDATIONS_ENABLED=true` requests the documented `CloudPC.ReadWrite.All` application role because the current report action requires it, even though this template only reads the returned report. Enable it only after reviewing that expanded permission.

## Documentation

| Guide | Purpose |
| --- | --- |
| [Configuration](docs/configuration.md) | Defaults, rules JSON, Teams setup, and azd values |
| [Architecture](docs/architecture.md) | Data flow, state model, and alert lifecycle |
| [Identity and authentication](docs/identity-and-authentication.md) | Managed identity, Graph roles, consent, and trust boundaries |
| [Operations](docs/operations.md) | Deployment checks, logs, dry-run rollout, and cleanup |
| [Development](docs/development.md) | Fixtures, tests, Bicep validation, and live-proof boundaries |

## Current boundaries

This template does not create or modify Cloud PCs, Intune policies, licenses, assignments, groups, or Teams channels. It does not replace Intune recommendations, provide cost billing data, or claim that local tests prove tenant permissions or recipient-visible delivery. Those are separate live validation gates.
