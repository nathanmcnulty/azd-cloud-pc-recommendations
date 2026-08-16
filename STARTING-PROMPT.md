# Starting Prompt: azd-cloud-pc-recommendations

Build this repository into a private Azure Developer CLI (`azd`) template focused on Cloud PC automation, monitoring, and alerting. Intune already provides the recommendations dashboard, so do not rebuild that dashboard or position this project as a duplicate reporting UI.

## Product direction

Turn Cloud PC recommendations and operational signals into actionable automation. The solution should identify conditions such as underused or unused Cloud PCs, provisioning failures, license or assignment mismatches, stale devices, unhealthy connection status, capacity/cost anomalies, and recommendation changes that need operator attention.

## Reference material

- `nathanmcnulty/nathanmcnulty/Azure/Templates/cloud-pc-recommendations-report/` for the existing Bicep/template starting point.
- `nathanmcnulty/nathanmcnulty/Azure/Automation/Device-Cleanup.ps1` and `Device-Cleanup-v2.ps1` for cleanup, safeguards, and scheduled automation patterns.
- `nathanmcnulty/azd-device-cleanup` for an azd runbook deployment shape.
- `nathanmcnulty/azd-defender-reporting` for deployment modes, hosted automation, validation, and reporting patterns.
- `nathanmcnulty/azd-entra-health-monitoring` for Logic App alerting and Teams-oriented monitoring patterns.
- Microsoft Graph Cloud PC, Intune, Windows 365, Azure Monitor, and Teams documentation for current supported APIs and permissions.

## Expected implementation

Use `azure.yaml`, Bicep, and azd hooks. Build a scheduled, idempotent automation service using the simplest maintainable combination of Azure Automation, Functions, Logic Apps, or Container Apps Jobs. Include:

- Collection of Cloud PC inventory, usage, status, provisioning, assignment, and recommendation data through supported Microsoft Graph APIs.
- A configurable rules engine with severity, thresholds, grace periods, suppression, and ownership routing.
- Teams notifications using an explicit webhook/workflow/Logic App strategy, with actionable links and deduplication.
- Optional remediation actions behind separate flags and approval gates; never delete or reprovision Cloud PCs automatically by default.
- Durable state for baselines, alert fingerprints, acknowledged alerts, and notification history.
- Managed identity, least-privilege permissions, diagnostics, retry behavior, and clear handling of throttling.
- A compact operational report or export for audit purposes, but not a replacement for the Intune recommendations dashboard.

Start with three high-value alerts: unused Cloud PCs, provisioning failures, and unhealthy/stale devices. Add dry-run mode, test fixtures, and a safe validation command before implementing remediation.