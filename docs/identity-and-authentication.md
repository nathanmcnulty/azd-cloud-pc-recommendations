# Identity and authentication

The deployed Function uses a system-assigned managed identity. No app registration client secret is created by the template.

## Required Graph roles

The post-provision hook can assign these Microsoft Graph application roles to the Function service principal:

| Mode | Application roles | Why |
| --- | --- | --- |
| Default inventory and first-milestone alerts | `CloudPC.Read.All`, `DeviceManagementManagedDevices.Read.All` | Read Cloud PC inventory/status and Intune managed-device sync/compliance data. |
| Optional recommendation report | `CloudPC.ReadWrite.All`, `DeviceManagementManagedDevices.Read.All` | The current recommendation-report action documents `CloudPC.ReadWrite.All` as its least-privileged application permission. The code still performs no Cloud PC write operation. |

The Graph role assignment is a tenant-side mutation. The operator must already be authorized to assign application roles and the tenant must grant the required admin consent. If the post-provision hook cannot complete this step, it stops with the role and tenant boundary; it does not weaken permissions or switch authentication methods.

The hook uses the normal Azure CLI cached/browser session selected for the azd environment. It does not use device-code authentication, print tokens, or persist token material.

## Azure resource roles

Bicep assigns the Function identity data-plane access only to the dedicated storage account:

- Storage Blob Data Owner for the Function host and audit container lifecycle;
- Storage Queue Data Contributor for Function host queues;
- Storage Table Data Contributor for alert and observation state.

These roles are scoped to the template-owned Storage account. The Function identity receives no subscription Contributor role and no access to unrelated storage accounts.

## Teams boundary

Teams Workflows is configured by an operator outside the template. The webhook URL is supplied as a secure Bicep parameter and stored as an encrypted Function App setting. It is a bearer-style destination secret: anyone who obtains it may submit a message to the workflow. Rotate the workflow URL if it is exposed.

## Data and trust boundaries

- Cloud PC and Intune data crosses from Microsoft Graph into the Function process.
- Alert state and audit reports remain in the dedicated Azure Storage account.
- A compact report includes Cloud PC identifiers, display names, user principal names when Graph returns them, status evidence, and notification outcome. Restrict storage readers and review retention before production use.
- Teams receives only the alert card fields and evidence needed for operator triage; the webhook URL is never included in a report or log message.

Review the Microsoft Graph permission grant, Windows 365 licensing, Intune licensing, Graph throttling limits, Teams workflow ownership, and data-retention requirements with the tenant administrator before enabling a live environment.
