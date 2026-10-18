# Shared component compatibility assessment

This CPC-004 discovery assessment evaluates Cloud PC main
[`f035b101ebe9c5928dae058ad871979a23b56e1e`](https://github.com/nathanmcnulty/azd-cloud-pc-recommendations/tree/f035b101ebe9c5928dae058ad871979a23b56e1e)
against immutable azd-reference
[`277584b33fcae7d47113718aad6428abdc4bc50f`](https://github.com/nathanmcnulty/azd-reference/tree/277584b33fcae7d47113718aad6428abdc4bc50f).
These are evaluation pins, not component adoption or permission approval. No
component lock, deployment, runtime, infrastructure or permissions are changed.

| Component | Decision | Reason |
| --- | --- | --- |
| `flex-scheduled-poller-host` 0.1.0 pilot | Defer | Node-only runtime, shared-key host/package storage and Blob-only role boundary regress this Python/identity-only consumer. Retain the current host. |
| `notification-contracts` 1.0.0 pilot | Adapt in a future delivery-boundary change; no adoption now | Existing Python alerts can supply domain data, but the aggregate notifier result lacks per-event/per-route evidence and several outcomes have different semantics. Do not rename the run report into a canonical receipt. |
| `deployment-validation` 1.1.1 stable | Adapt as an optional PowerShell 7.6+ management wrapper; defer implementation here | The shared management engine can orchestrate bounded checks around existing Python outputs. It must not become a second collector, evaluator or event engine. |

## Preserve the Python storage boundary

The consumer's [Bicep](https://github.com/nathanmcnulty/azd-cloud-pc-recommendations/blob/f035b101ebe9c5928dae058ad871979a23b56e1e/infra/main.bicep)
defines Python 3.11, system-assigned identity, identity-based deployment storage,
`allowSharedKeyAccess: false`, and `AzureWebJobsStorage__credential: managedidentity`
with Blob, Queue and Table endpoints. It assigns scoped Storage Blob Data Owner,
Storage Queue Data Contributor and Storage Table Data Contributor roles. The
Python [state store](https://github.com/nathanmcnulty/azd-cloud-pc-recommendations/blob/f035b101ebe9c5928dae058ad871979a23b56e1e/src/cloud-pc-monitor/cloudpc_monitor/state.py)
persists observations, fingerprints, acknowledgements and notification history
in Table Storage. The [exporter](https://github.com/nathanmcnulty/azd-cloud-pc-recommendations/blob/f035b101ebe9c5928dae058ad871979a23b56e1e/src/cloud-pc-monitor/cloudpc_monitor/report.py)
writes private Blob JSON using managed identity.

The evaluated [Flex module](https://github.com/nathanmcnulty/azd-reference/blob/277584b33fcae7d47113718aad6428abdc4bc50f/components/bicep/flex-scheduled-poller-host/flex-scheduled-poller-host.bicep)
hardcodes Node 22, enables shared-key access, uses `listKeys()` to construct
`AzureWebJobsStorage` and deployment connection strings, and configures
`StorageAccountConnectionString` package authentication. Its runtime role is
Storage Blob Data Contributor for state/dead-letter containers; it does not
preserve this consumer's Queue/Table host and state requirements. An adapter
would need explicit Python and identity-only host/package/storage contracts,
compatible state/RBAC, packaging and negative shared-key probes before migration.
This assessment neither reduces the current Blob Owner role nor grants new roles.

## Notification field and trust mapping

The actual [service](https://github.com/nathanmcnulty/azd-cloud-pc-recommendations/blob/f035b101ebe9c5928dae058ad871979a23b56e1e/src/cloud-pc-monitor/cloudpc_monitor/service.py)
produces one operational run report, not a delivery receipt. Its `schemaVersion`
`1.0` is a consumer version and does not establish compatibility with either
reference schema. `runId`, `observedAt`, `dryRun`, `graphApiVersion`, collection
counts, alerts, warnings, compact Cloud PC records and optional `reportUri` have
different authority and privacy boundaries from administrator-facing receipts.

The immutable [envelope](https://github.com/nathanmcnulty/azd-reference/blob/277584b33fcae7d47113718aad6428abdc4bc50f/schemas/notification-envelope.schema.json)
and [route-result schema](https://github.com/nathanmcnulty/azd-reference/blob/277584b33fcae7d47113718aad6428abdc4bc50f/schemas/notification-delivery-result.schema.json)
require the following mapping, with gaps retained rather than invented:

| Canonical field | Existing Python evidence / missing contract |
| --- | --- |
| Envelope `schemaVersion` | Explicit adapter version; do not reuse the aggregate version as proof. |
| `eventId` | Alert fingerprint is a stable rule/Cloud-PC identity, not yet an occurrence identity covering resolution/reopen and scheduled renotification. Define that boundary in existing state/delivery processing before adoption. |
| `eventType`, envelope `source` | Rule IDs and Graph collection mode exist, but namespaced values need consumer registration; no automatic string renaming is adopted. |
| `correlationId` | Run UUID can correlate one run; it is not a stable source-event identity. Canonical fallback to event identity requires that identity first. |
| Envelope `occurredAt`, `severity`, `data` | `detectedAt` is evaluation time, not necessarily source occurrence time; alert severity is available. Locally validated alert data may contain PII and must remain access controlled. Do not copy the alert/card into a receipt. |
| `isTest`, `environment` | `dryRun` is not a test-event flag. Tenant and environment context are not bound in this aggregate report; supply verified operator/runtime context at the adapter boundary, never infer it from an audit row. |
| Result `idempotencyKey` | Current SHA-256 fingerprint is `ruleId:cloudPcId`; canonical SHA-256 is `tenantId + newline + eventType + newline + eventId + newline + route.id`. They are not interchangeable. Preserve current grace, acknowledgement and renotification behavior when defining occurrences. |
| `route.id`, `route.audience`, `route.transport` | Alert `route` is a configured business label; the notifier sends all due alerts to one webhook, not separate destinations per label. Keep a non-PII logical route ID and resolve its destination internally. Audience requires explicit routing context. Actual transport is the registered `teams.workflowWebhook`, not generic HTTP or a Teams bot. |
| Result `status`, `skipReason`, `failure` | Current `sent`, `none`, `skipped`, `failed` aggregate statuses cannot be mechanically converted; see outcome gaps below. |
| `attempt`, `recordedAt`, optional `durationMs` | Evaluation timestamp exists, but per-route attempt/time/duration evidence is not returned. Instrument the existing notifier boundary instead of reconstructing it after a batch. |
| Result `evidence` | Copy only allowlisted opaque codes/identifiers and verified HTTP status at that boundary. Do not copy `reportUri`, provider text, cards, PII, settings or the complete Python report. |

The current [notifier](https://github.com/nathanmcnulty/azd-cloud-pc-recommendations/blob/f035b101ebe9c5928dae058ad871979a23b56e1e/src/cloud-pc-monitor/cloudpc_monitor/notifications.py)
returns only `status`, `candidateCount`, `sentCount`, and `reason`. The following
gaps prevent current adoption:

- Any 2xx response is treated as `sent`; this proves workflow HTTP acceptance,
  not a Teams message displayed to its recipient.
- A batch can send ten alerts and fail the next chunk. Successful state is
  retained, but one aggregate `failed` outcome has no per-event result list.
- `deduplicated_or_acknowledged` conflates a completed delivery with policy
  suppression. It cannot become `alreadyDelivered` for every candidate.
- Selected-but-missing webhook configuration currently yields a skip. The
  reference requires `destinationUnavailable` failure for an unusable selected
  destination. Disabled policy/dry-run semantics also need explicit mapping;
  only the canonical three skip reasons are allowed.
- Retry count, final HTTP evidence, per-route failure classification and
  destination context are not returned in the aggregate. CPC-006 now classifies
  transport exceptions internally and returns the existing failed aggregate.

**Historical security gap, reproduced and repaired by CPC-006:** the assessed
`f035b101ebe9c5928dae058ad871979a23b56e1e` `_send` included up to 300 characters
of raw provider response text in `NotificationError`; `deliver` logs that error.
A reflected callback URL or credential could therefore enter logs. The original
synthetic failure fixture reproduced this and is now a negative receipt/log
regression. The repaired boundary does not read response text, does not log or
chain raw transport errors, and uses a closed diagnostic code. Tests cover real
Requests prepared requests and the timer/monitor flow through an in-process
adapter; they do not prove hosted telemetry or live Teams delivery. No component
contract or hosting decision changes. Never emit webhook/bearer URLs, SAS URLs,
raw exceptions, headers, response bodies or rendered cards in canonical receipts.

## Optional deployment-validation wrapper mapping

**Implementation update (CPC-007):** the optional PowerShell 7.6+ wrapper is now
implemented in `scripts/Test-Deployment.ps1` using immutable hash-locked
`deployment-validation` 2.0.0. See [operations](operations.md#optional-read-only-deployment-validation)
for explicit target arguments, required existing read authority and exact check
boundaries. Plan is offline, verification is read-only, and delivery is refused.
An optional key-only `run/latest` Table read proves row accessibility only.
CPC-002 still owns deployed runtime, Graph, audit payload/freshness and recipient
qualification. The original mapping below records the assessment and wider
contract constraints; its future-tense language is historical design context.

The [shared management standard](https://github.com/nathanmcnulty/azd-reference/blob/277584b33fcae7d47113718aad6428abdc4bc50f/standards/deployment-validation.md)
can wrap Python output while Python retains collection, rules, state and delivery.
The wrapper would use `New-AzdValidationReport`/check definitions, not copy the
Python report as the canonical [management schema](https://github.com/nathanmcnulty/azd-reference/blob/277584b33fcae7d47113718aad6428abdc4bc50f/schemas/deployment-validation.schema.json).

| Management contract | Mapping / guard |
| --- | --- |
| `schemaVersion`, `reportType`, `template`, `mode` | New wrapper-owned identities/version/mode; the Python aggregate lacks them. Optional 1.1 management binding requires a complete verified source/project/target/operation tuple; do not fabricate it. |
| `startedAt`, `completedAt`, `durationMs` | Wrapper check timing. `observedAt` is an observation time, not the management operation interval. |
| `requirements` | Selected tools/modules/permissions as prerequisites, not permission approval. Retain current Python requirements and PS 7.6+ for the optional wrapper. |
| `checks`, `outcome`, `summary`, `nextSteps` | Context-gated management checks and allowlisted outcomes. Counts/`dryRun` do not imply a passing deployment or delivery check. Do not import arbitrary warnings, expected/actual objects or complete report contents into evidence. |
| Optional `environment` | Exact validated context, not inferred from report URLs or Graph rows. Blob `reportUri` stays outside closed receipt evidence. |

`-Plan` must perform no authentication, cloud calls or Python event run. Default
verification must be read-only: verify selected context first, then runtime,
identity-only storage settings/RBAC, package/runtime and bounded existing audit
state. Calling `MonitorService.run()` as a deployment check would collect,
write state/reports and potentially send notifications, so it is not a safe
default validation shortcut. The existing fixture CLI remains an offline logic
check; it is not deployed-state proof. `-TestDelivery` needs separate exact
destination authorization and recipient-visible evidence, with secrets supplied
internally rather than command-line/report arguments. No automatic hook may
send messages. Do not implement another Python evaluator in PowerShell.

## Acceptance and limits

`tests/test_component_assessment.py` executes the actual `MonitorService`,
`FixtureCollector`, `TeamsNotifier`, alert/state types and exporters with fake
in-process HTTP responses. It checks aggregate report/state binding, grace-pass
behavior, currently absent remediation even when a reserved setting is true,
partial-batch state, acknowledgement ambiguity, missing destination, HTTP
acceptance/renotification and receipt/log URL absence. Additional
`tests/test_notification_safety.py` cases cover provider body refusal, Requests
transport classification, exhausted retries, partial success and actual timer/
monitor report persistence. It does not implement or claim canonical envelope/
result validation.

Run `./scripts/validate.ps1` and `./scripts/Test-LocalFixtures.ps1` with PowerShell
7.6+. The former compiles Bicep and Python, parses PowerShell and discovers all
tests; the latter runs the existing dry-run report path. No live Graph,
Azure deployment, Teams delivery, remediation, permission grant or storage
migration is needed to complete this discovery assessment. CPC-002 live pilot
and CPC-003 acknowledgement work remain separate.

## Native read-only verification update (2026-10-18)

Verification against the existing `sub-mvp` deployment passed six checks:
exact enabled context, Linux Python 3.11/system identity, hardened storage,
identity-only deployment and host storage, and the three direct unconditional
storage roles. Native role assignments omitted optional `condition`; the wrapper
now handles that response while rejecting malformed non-string conditions.
Subprocess fixtures cover missing/null/blank conditions and malformed arrays,
objects, booleans and numbers, alongside wrong role/scope/principal failures.

The explicitly selected key-only `CloudPcState` `run/latest` read failed. A
separate bounded diagnostic confirmed the testing account lacks required table
data permissions. The full verification report remains failed; no additional
access was granted. This proves selected control-plane configuration only.
Runtime execution, Graph collection, audit payload/freshness and recipient-visible
delivery remain open under CPC-002. No monitor invocation, state write,
notification or resource mutation was performed.
