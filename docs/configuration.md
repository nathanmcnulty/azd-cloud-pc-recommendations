# Configuration

The pre-provision hook writes safe defaults into the current azd environment. Change values with `azd env set` before `azd provision` or `azd up`; do not commit the generated `.azure` directory.

## Important settings

| azd value | Default | Purpose |
| --- | --- | --- |
| `DRY_RUN` | `true` | Suppresses outbound Teams delivery unless explicitly enabled; no remediation exists in this milestone. |
| `NOTIFICATIONS_ENABLED` | `true` | Enables the notification path when a webhook is configured. |
| `SEND_NOTIFICATIONS_IN_DRY_RUN` | `false` | Allows a deliberate recipient-visible notification test while keeping remediation disabled. |
| `TEAMS_WEBHOOK_URL` | empty | Teams Workflows callback URL. Treat it as a secret. |
| `GRAPH_API_VERSION` | `beta` | Graph version used for Cloud PC inventory. `v1.0` is more stable but may omit first-milestone status fields. |
| `CLOUD_PC_RECOMMENDATIONS_ENABLED` | `false` | Collects the optional usage-category recommendation report and requests `CloudPC.ReadWrite.All`. |
| `UNUSED_CLOUD_PC_DAYS` | `30` | Login age threshold for the unused rule. |
| `STALE_DEVICE_DAYS` | `14` | Intune `lastSyncDateTime` threshold for the stale-device rule. |
| `PROVISIONING_FAILURE_GRACE_MINUTES` | `60` | Time a failed Cloud PC must remain observed before notification. |
| `UNHEALTHY_DEVICE_GRACE_MINUTES` | `60` | Time an unhealthy/stale condition must remain observed before notification. |
| `NOTIFICATION_RENOTIFY_HOURS` | `24` | Minimum interval between notifications for an active fingerprint. |
| `GRAPH_ROLE_ASSIGNMENTS_ENABLED` | `true` | Lets the post-provision hook create the required Graph application-role assignments idempotently. |
| `REPORT_RETENTION_DAYS` | `30` | Blob lifecycle retention for JSON reports. |
| `INTUNE_CLOUD_PC_URL` | `https://intune.microsoft.com/` | Action link included in alert cards. Set a tenant-specific Cloud PC view if available. |
| `REMEDIATION_ENABLED` | `false` | Reserved for a future implementation; the current service never remediates. |

Example safe configuration:

```powershell
azd env set DRY_RUN true
azd env set CLOUD_PC_RECOMMENDATIONS_ENABLED false
azd env set GRAPH_ROLE_ASSIGNMENTS_ENABLED true
azd env set NOTIFICATIONS_ENABLED true
azd env set-secret TEAMS_WEBHOOK_URL
```

Do not paste the URL into `infra/main.parameters.json` or any tracked file. `azd env set-secret` keeps the value in the azd environment's secret store and renders it only for the secure Bicep parameter.

## Rule JSON

`CLOUD_PC_RULES_JSON` replaces the built-in rule array. It supports severity, threshold, grace period, an ownership route, and per-rule suppression:

```json
[
  {
    "id": "unused-cloud-pc",
    "enabled": true,
    "severity": "medium",
    "thresholdDays": 30,
    "gracePeriodMinutes": 0,
    "route": "cloud-pc-operations",
    "suppression": {
      "cloudPcIds": [],
      "userPrincipalNames": ["breakglass@example.com"]
    }
  },
  {
    "id": "provisioning-failure",
    "enabled": true,
    "severity": "high",
    "thresholdDays": 0,
    "gracePeriodMinutes": 60,
    "route": "cloud-pc-operations"
  },
  {
    "id": "unhealthy-stale-device",
    "enabled": true,
    "severity": "high",
    "thresholdDays": 14,
    "gracePeriodMinutes": 60,
    "route": "cloud-pc-operations"
  }
]
```

`ALERT_SUPPRESSIONS` is a simpler comma-separated suppression list. A value matching a rule ID suppresses that rule globally; a value matching a Cloud PC ID suppresses that device for all rules.

The Teams destination is one workflow URL. The `route` value is included in the card and audit record so a later routing adapter can distinguish ownership without changing detection or state semantics.

## Teams Workflows setup

1. In the target Teams channel, open **Workflows** from the channel menu.
2. Choose a template such as **Send webhook alerts to a channel**, or create a workflow with **When a Teams webhook request is received**.
3. Configure the workflow to post the incoming Adaptive Card to the channel, save it, and copy its callback URL.
4. Keep a co-owner on the workflow so the destination is not orphaned when the original owner leaves.
5. Set `TEAMS_WEBHOOK_URL` in the azd environment and keep `SEND_NOTIFICATIONS_IN_DRY_RUN=false` until collection is reviewed.

Microsoft is retiring new Microsoft 365 Connectors in favor of Workflows. This template does not create the Teams workflow or store a connector credential. See [Create an Incoming Webhook](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook) and the [Teams webhook trigger](https://learn.microsoft.com/en-us/connectors/teams/) for the current workflow behavior and limits.
