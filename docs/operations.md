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

Teams failures log only the successful alert count and one fixed diagnostic:
`http_rejected`, `http_retry_exhausted`, `transport_timeout`,
`transport_connection_failed`, `transport_request_failed`, `transport_failed`,
or `session_unavailable`. Provider response text, exception messages/traceback
causes, webhook URLs and destination settings are not copied into those logs or
aggregate results. Inspect the authorized workflow run history for additional
provider diagnostics; do not paste bearer URLs or raw errors into reports.

The aggregate keeps its existing `failed` / `webhook_request_failed` outcome
and successful partial-batch count. Retryable HTTP statuses still get at most
four attempts with bounded existing backoff; transport exceptions return a safe
failure immediately without adding a new retry policy. Only successful chunks
update notification state. Acknowledgement and deduplication semantics, skipped
destinations, lack of remediation, and the HTTP-versus-recipient proof boundary
remain unchanged. Offline safety tests use an in-process Requests adapter and
actual monitor/timer handler; no Teams messages are sent.

## Cleanup

`azd down` removes the Azure resources owned by the azd environment. Before cleanup, preserve any audit reports required by policy and verify the exact resource group. Review the Function service principal and Graph app-role assignments according to tenant policy; do not assume a resource cleanup operation is a substitute for tenant-side identity review.

The template does not delete Cloud PCs, managed devices, licenses, assignments, policies, Teams channels, or external workflow definitions.

## Exact alert acknowledgement

From `src/cloud-pc-monitor`, use `python -m cloudpc_monitor.ack_cli` with the
selected storage account name, tenant GUID and existing table name. This command
uses cached Azure CLI credentials for that tenant; it never logs in, grants a
role, creates a table, collects Graph data, sends notifications or changes a
Cloud PC. The operator must already have authorized read/write access to the
selected Table. No new identity, scope or automatic role assignment is added.

```powershell
# PowerShell 7.6+. Supply the intended existing account/tenant/table.
$target = @('--account-name', $accountName, '--tenant-id', $tenantId,
    '--table', $tableName)
python -m cloudpc_monitor.ack_cli @target show --fingerprint $fingerprint
# Copy the exact episode and ackRevision from show. Keep this request UUID for replay.
$requestId = [guid]::NewGuid().ToString()
python -m cloudpc_monitor.ack_cli @target acknowledge --fingerprint $fingerprint `
    --episode $episode --revision $ackRevision --request-id $requestId `
    --actor $operatorLabel --expires-at $expiresAtUtc
python -m cloudpc_monitor.ack_cli @target history --fingerprint $fingerprint --limit 20
# If history returns a cursor, pass --cursor $cursor to get the next page.
```

The fingerprint is the exact SHA-256 alert identity, not a device name or a
wildcard. The episode identifies its current activation; acknowledgement revision
changes with acknowledgement, expiry and reopening, rather than each ordinary
timer update. Missing/inactive alerts, wrong episodes/revisions and malformed
inputs fail with a finite diagnostic. New acknowledgement expiry must be a future,
timezone-qualified timestamp supplied explicitly; acknowledgement time comes from
the command's UTC clock. Actor labels are **operator-asserted**, never proof of the
Azure CLI account, tenant identity or authenticated human. Do not put secrets in
an operator label. Legacy acknowledgement rows keep their existing indefinite
suppression with `legacy_unknown` provenance until explicitly replaced; historical
actor/time information is not fabricated.

Acknowledgement suppresses notification eligibility until `now >= expiresAt`.
The existing renotification interval still applies after expiry. Ordinary repeated
observations retain the episode and acknowledgement; observed resolution followed
by reactivation opens a new episode without inheriting suppression. Historical
acknowledgement, expiry, resolution and reopen events remain immutable and are
returned in bounded pages ordered by event key, not chronological order. There is
no automatic history deletion or invented retention policy. Old alert row keys,
notification timestamps/counts and unrelated state fields are retained.

The alert update and acknowledgement audit insert form a same-partition Table
transaction with the observed opaque ETag. Timer synchronization, resolution and
notification bookkeeping use conditional updates too. Each acknowledged send in
the same episode increments its count, while the recorded success timestamp stays
at the latest qualified UTC time even if older requests finish later. A prior
episode cannot update a newly activated alert; malformed input or stored timestamps
are refused without a state write. Only confirmed 409/412
conflicts may recompute against current state, up to four attempts. SDK mutation
retries are disabled; a lost response is an unknown outcome, never proof of a
failed write. An acknowledgement rereads its exact request event to resolve an
ambiguous result. Even after a successful transaction response, missing, malformed
or mismatched audit readback remains unqualified and returns a closed failure; it
does not trigger a second transaction. Identical request replay is idempotent; reusing a UUID with
changed inputs is refused. The Python transition supports replay after the recorded
expiry; the CLI deliberately rejects expired command input before constructing a
credential/store, so use bounded history to inspect an older request outcome.

Health ordering uses captured observation/resolution timestamps, never the
operator's acknowledgement time. Older snapshots cannot resolve or overwrite a
newer observation, clear its acknowledgement or reopen its episode. Equal-time
contradictory transitions and legacy rows without usable health timestamps are
refused; repeated identical active observations remain valid. Notification
candidates must still match the current active episode and observation at the
eligibility check and immediately before dispatch.

An active episode retains its durable first-seen time if an overlapping older
snapshot deletes grace observation state, so this cannot delay an already active
alert or defeat acknowledgement suppression. Post-resolution grace cannot reuse
an observation from before resolution. Observation rows themselves retain the
existing non-transactional monitor behavior: overlapping snapshots before an
alert exists can still delay first activation. This is not an acknowledgement,
exactly-once collection or live concurrency guarantee.

Acknowledgement committed before the notifier's eligibility decision suppresses
the send. It cannot recall an already dispatched HTTP request. A successful webhook
response remains HTTP acknowledgement, not recipient-visible delivery or an
exactly-once guarantee. Fixtures exercise the real rules/state/notifier and SDK
wire interfaces with synthetic transports; live Table concurrency and actual
recipient visibility remain CPC-002 validation gates.

`azd-permissions.json` is a partial source-backed inventory with explicit gaps,
not authority to grant permissions. The acknowledgement feature uses the existing
Table access boundary; shared deployment/notification contracts do not provide
these alert-episode/concurrency semantics and are not adopted here.

## Optional read-only deployment validation

PowerShell 7.6+ users may run `scripts/Test-Deployment.ps1` to inspect the
selected deployment through the cached Azure CLI session. `-Plan` is offline
and performs no CLI or authentication call. Verification requires explicit
`TenantId`, `SubscriptionId`, `ResourceGroup`, `FunctionAppName`, and
`StorageAccountName`; it checks exact resource IDs, Python 3.11/system identity,
identity-only storage settings, deployment storage binding, host endpoints, and
direct unconditional storage roles. `-TableName` opts into one bounded
`run/latest` Table read. `-TestDelivery` is intentionally unsupported and fails
before any CLI or authentication call.

The wrapper is control-plane evidence only. Passing checks do not establish
Graph collection, Function execution, report generation, runtime telemetry, or
recipient-visible Teams delivery. Use `-OutputPath reports/deployment-validation.json`
to write a schema-validated local report (also the default); reports are gitignored.

```powershell
./scripts/Test-Deployment.ps1 -Plan
./scripts/Test-Deployment.ps1 -TenantId $env:AZURE_TENANT_ID `
    -SubscriptionId $env:AZURE_SUBSCRIPTION_ID -ResourceGroup $env:AZURE_RESOURCE_GROUP `
    -FunctionAppName $env:AZURE_FUNCTION_APP_NAME -StorageAccountName $env:STORAGE_ACCOUNT_NAME
```

Verification requires the currently selected CLI context to match the supplied
enabled tenant/subscription in public Azure. The checker does not switch accounts
or start login. A missing session requires normal `az login`; no device-code
authentication is used. Checks have a 30-second CLI timeout and fail with safe
diagnostics when reads are denied or malformed. Read-only errors never trigger
repair or grant operations.

The caller needs resource/role-assignment read authority plus
`Microsoft.Web/sites/config/list/action` to read Function settings; ordinary
Reader alone does not authorize that action. Optional `-TableName` requires
existing Table data read authority. No permission is granted by the checker or
its partial permission inventory. The single `run/latest` key read proves only
that an existing summary row is accessible; it does not establish freshness,
payload validity, or runtime health. Inherited or conditional RBAC assignments
are not accepted as the template's expected direct unconditional assignments.

The vendored engine and schema are pinned in `azd-components.lock.json` to
`azd-reference` revision `2b2e784ba11822272c0e4b8389976f95afafa9b9`
(`deployment-validation` 2.0.0). Deployment never downloads or depends on the
reference repository. This optional command is not an automatic lifecycle hook.
