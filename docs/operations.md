# Operations

## Safe rollout

1. Run local validation and the fixture command.
2. Create a dedicated azd environment and select the intended subscription, tenant, region, and resource group.
3. Keep `DRY_RUN=true`, `CLOUD_PC_RECOMMENDATIONS_ENABLED=false`, and `SEND_NOTIFICATIONS_IN_DRY_RUN=false` for the first deployment.
4. Review the Graph roles requested by the post-provision hook and complete tenant consent through the normal administrator process.
5. Run `azd provision` and inspect the Function identity, storage role assignments, app settings, and Application Insights resource.
6. Review the first audit report and Function logs. Confirm that the Cloud PC count is plausible and that collection warnings are understood.
7. Configure the Teams workflow and set `TEAMS_WEBHOOK_URL`. If a recipient-visible test is required, set `SEND_NOTIFICATIONS_IN_DRY_RUN=true` for one controlled run, then return it to `false`.
8. Only after the signal quality and destination are reviewed should an operator set `DRY_RUN=false`. This milestone still performs no remediation in either mode.

## Commands

```powershell
.\scripts\validate.ps1
.\scripts\Test-LocalFixtures.ps1
azd provision
azd deploy
azd hooks run postprovision
```

The post-provision hook is idempotent: existing Graph role assignments are detected and left unchanged. If it fails because the signed-in operator lacks tenant authority, resolve that authority explicitly and rerun the hook; do not add broader roles.

## What to inspect

- Function App logs for Graph HTTP status, retry, throttling, and collection warnings.
- The `CloudPcState` table for active fingerprints, first-seen timestamps, acknowledgements, and notification timestamps.
- The `reports` Blob container for one compact JSON report per invocation.
- Application Insights failures and dependency telemetry.
- Teams workflow run history and recipient-visible channel delivery. A successful HTTP response from the webhook is not by itself proof that an operator saw the message.

Graph throttling is handled with `Retry-After` when present and bounded exponential backoff for retryable 429/5xx responses. A report records partial collection warnings rather than converting a failed optional source into an empty success.

## Cleanup

`azd down` removes the Azure resources owned by the azd environment. Before cleanup, preserve any audit reports required by policy and verify the exact resource group. Review the Function service principal and Graph app-role assignments according to tenant policy; do not assume a resource cleanup operation is a substitute for tenant-side identity review.

The template does not delete Cloud PCs, managed devices, licenses, assignments, policies, Teams channels, or external workflow definitions.
