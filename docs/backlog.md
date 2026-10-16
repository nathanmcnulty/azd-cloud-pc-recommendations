# Backlog: nathanmcnulty/azd-cloud-pc-recommendations

> Generated from `docs/backlog.json`. Edit the JSON source and regenerate this file.
> Standard: [azd agent backlog standard](https://github.com/nathanmcnulty/azd-reference/blob/main/standards/agent-backlogs.md). This link is review guidance, not a runtime dependency.

- **Schema version:** 1.0.0
- **Repository:** nathanmcnulty/azd-cloud-pc-recommendations
- **Source revision:** `285113a76bd1cdf177de5a49e806a8327066be22`
- **Captured:** 2026-10-16
- **Items:** 7

## CPC-001: Reconcile this backlog with current source and active work

- **Kind:** discovery
- **Priority:** P1
- **Status:** done
- **Wave:** 0
- **Authorization:** local-only
- **Blocker:** _none_
- **Claim:** _none_

**Problem:**

Plans and implementation evidence are spread across files; the captured source can change while other tasks work.

**Scope:**

- docs/backlog.json
- docs/backlog.md
- Existing roadmap, execution status, open issues and pull requests &lpar;read-only&rpar;

**Acceptance:**

- Classify each candidate as implemented, still open, superseded or awaiting evidence; retain source links and reasons.
- Inspect dirty state, remotes, worktrees and local environment presence without reading secrets; avoid duplicate work with active owners.
- Resolve the actual offline validation commands and record exact current default-branch/working-tree provenance; do not copy historical live passes to newer code.

**Validation:**

- git status --short
- git remote -v
- git worktree list --porcelain
- Read the applicable instructions and validation workflow; read gh issue list and gh pr list for the named repository using nathanmcnulty. Do not create or modify issues/PRs.

**Dependencies:**

- _none_

**Components:**

- _none_

**Sources:**

- README.md

**Evidence:**

- 2026-10-04 read-only reconciliation against current main 2e247dc0895e7b4822ed74ffe58c0f5924ba5824&colon; inspected canonical dirty state, remotes, worktrees and environment-path presence without reading values; active/unowned branches remain untouched. Reviewed current issue/PR inventory, roadmap/TODO task sources and .github/workflows/validate.yml; kept live and optional-feature gates proposed.
- scripts/validate.ps1 passed Bicep/PowerShell/Python compilation and 12 unittest cases; Test-LocalFixtures.ps1 passed deterministic dry-run reporting. Validation used offline fixtures only; no cloud, tenant, recipient or endpoint action was performed.

**Review and authorization note:**

Review CPC-001 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.

## CPC-005: Collect every Cloud PC recommendation report page

- **Kind:** maintenance
- **Priority:** P1
- **Status:** done
- **Wave:** 0
- **Authorization:** local-only
- **Blocker:** _none_
- **Claim:** _none_

**Problem:**

Read-only reconciliation identified a resolved current-main defect missing from the captured task inventory.

**Scope:**

- src/cloud-pc-monitor/cloudpc&lowbar;monitor/graph&lowbar;client.py
- tests/test&lowbar;graph&lowbar;client.py

**Acceptance:**

- Record exact merged source and regression coverage for the linked issue.
- Preserve live-service and deployment acceptance as separate gates.

**Validation:**

- ./scripts/validate.ps1
- ./scripts/Test-LocalFixtures.ps1

**Dependencies:**

- _none_

**Components:**

- _none_

**Sources:**

- https&colon;//github.com/nathanmcnulty/azd-cloud-pc-recommendations/issues/5
- https&colon;//github.com/nathanmcnulty/azd-cloud-pc-recommendations/pull/6

**Evidence:**

- Merged PR &num;6 resolves issue &num;5 at 2e247dc0895e7b4822ed74ffe58c0f5924ba5824; implementation is present in current main 2e247dc0895e7b4822ed74ffe58c0f5924ba5824.
- scripts/validate.ps1 passed Bicep/PowerShell/Python compilation and 12 unittest cases; Test-LocalFixtures.ps1 passed deterministic dry-run reporting. This is source/fixture evidence only; no live authentication, deployment, tenant mutation, device action or delivery is claimed.

**Review and authorization note:**

Review CPC-005 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.

## CPC-006: Remove raw Teams provider errors from logs

- **Kind:** maintenance
- **Priority:** P1
- **Status:** done
- **Wave:** 1
- **Authorization:** local-only
- **Blocker:** _none_
- **Claim:** _none_

**Problem:**

TeamsNotifier includes raw provider response text in NotificationError and logs it; a reflected webhook bearer URL or credential can leak into telemetry. Transport exceptions can also escape without a safe classified result.

**Scope:**

- src/cloud-pc-monitor/cloudpc&lowbar;monitor/notifications.py
- tests/test&lowbar;notifications.py
- tests/test&lowbar;component&lowbar;assessment.py
- docs/operations.md

**Acceptance:**

- Remove raw provider body/exception/URL values from notification logs and return only stable allowlisted status/failure codes; do not echo destination configuration.
- Replace the CPC-004 characterization with negative receipt/log probes containing synthetic callback URLs, authorization values and reflected provider secrets, including nonretryable/retry-exhausted/transport-exception cases.
- Preserve retry, acknowledgement, deduplication, partial-batch success and non-remediating behavior; do not broaden Graph permissions or imply recipient-visible delivery from HTTP acceptance.

**Validation:**

- ./scripts/validate.ps1
- ./scripts/Test-LocalFixtures.ps1
- python -m unittest tests.test&lowbar;notifications tests.test&lowbar;component&lowbar;assessment -v

**Dependencies:**

- _none_

**Components:**

- notification-contracts

**Sources:**

- https&colon;//github.com/nathanmcnulty/azd-cloud-pc-recommendations/blob/f035b101ebe9c5928dae058ad871979a23b56e1e/src/cloud-pc-monitor/cloudpc&lowbar;monitor/notifications.py
- docs/component-compatibility-assessment.md

**Evidence:**

- CPC-004 source review and synthetic partial-batch 400 response fixture show response.text enters NotificationError and deliver logs the exception. The aggregate status result omits the body, but that is not end-to-end log safety. Runtime source is unchanged by the assessment.
- Completed by independently reviewed PR &num;9 &lpar;https&colon;//github.com/nathanmcnulty/azd-cloud-pc-recommendations/pull/9&rpar;, reviewed head b3b59f206a64c16c16927a5ea51427c2e4ffa6cd, merged main adb48c20e0e57101d608f8735b4b5cb051f89a58 and tree 3cbe37dddbc3be2093ef2599ad37cdf81112cc91. All six committed source blobs were bound to frozen evidence; independent review SHA BAD9565CC06FAFE092F0C87D31576AC5179C68A9854CF6D8FEFFEB57BD8EFEC0. Post-main runs 38115876557, 38115876555 and 38115876719 succeeded on the merged source.
- TeamsNotifier now uses allowlisted failure codes, never reads provider response text, and removes raw transport exception cause/context before logging a safe classified result. Arbitrary error values collapse to a fixed code. The CPC-004 log characterization is a negative leak regression; retry/backoff, acknowledgement, deduplication, partial-batch state and non-remediating delivery semantics are preserved.
- PowerShell 7.6.6 registered scripts/validate.ps1 passed Bicep, PowerShell syntax, Python compilation and 24 unittest cases; Test-LocalFixtures.ps1 passed deterministic dry-run reporting. Thirteen focused notification/component/safety methods cover arbitrary provider secrets, nonretryable and exhausted retries, Requests transport exception types, partial batches, and the actual timer/monitor/notifier logging flow through isolated HTTP adapters. Fixtures prove local source behavior only&colon; no real recipient-visible delivery, hosted telemetry, Graph/Azure mutation, deployment or remediation is claimed. CPC-002 retains live pilot acceptance.

**Review and authorization note:**

Review CPC-006 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.

## CPC-004: Evaluate shared notification and deployment contracts

- **Kind:** discovery
- **Priority:** P2
- **Status:** done
- **Wave:** 1
- **Authorization:** local-only
- **Blocker:** _none_
- **Claim:** _none_

**Problem:**

Python/identity-only hosting is not automatically compatible with the reference Flex pilot.

**Scope:**

- infra/
- scripts/
- docs/
- azd-components.lock.json

**Acceptance:**

- Map deployment-validation and notification-contracts to Python output without duplicating the event engine.
- Compare Flex storage/RBAC and Python runtime shape; prefer current identity-only design when the pilot regresses it.
- Keep remediations absent and Teams bearer URLs out of receipts.

**Validation:**

- From the solution root run ./scripts/validate.ps1
- Run focused tests for changed behavior from tests/; fixtures do not prove live-service or endpoint behavior.

**Dependencies:**

- _none_

**Components:**

- deployment-validation
- notification-contracts
- flex-scheduled-poller-host

**Sources:**

- README.md
- docs/component-compatibility-assessment.md

**Evidence:**

- Assessed fresh main f035b101ebe9c5928dae058ad871979a23b56e1e against immutable Reference 277584b33fcae7d47113718aad6428abdc4bc50f. Full source/field/trust mapping is in docs/component-compatibility-assessment.md; no component lock/adoption or infrastructure/runtime/permission change was made.
- Defer Flex 0.1.0 because Node 22/shared-key connection strings/Blob-only roles regress Python 3.11, disabled shared keys, managed-identity host/package storage and Blob Owner/Queue/Table roles. Adapt notification contracts only through the existing Python delivery boundary; aggregate counts cannot become per-event/per-route receipts. An optional PS 7.6+ management wrapper can orchestrate bounded read-only checks without duplicating the event engine; its implementation is deferred.
- Five new executable actual-consumer fixtures prove aggregate report/state binding and absent remediation, partial-batch successful state, acknowledgement/dedup ambiguity, missing destination, HTTP acceptance/renotification and absence of a synthetic bearer URL from aggregate results. The logging probe reproduces an unsafe raw provider-text path; CPC-006 tracks that separate defect, so no end-to-end safe logging or canonical receipt adoption is claimed.
- Registered scripts/validate.ps1 passed Bicep 0.46.1, PowerShell syntax, Python compilation and 17 unittest cases under PowerShell 7.6.6/Python 3.14.6. Existing Test-LocalFixtures.ps1 dry-run report and canonical backlog/export validation passed. No Graph/Azure mutation, delivery, remediation or deployment was performed; CPC-002/003 retain their original gates.

**Review and authorization note:**

Review CPC-004 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.

## CPC-002: Prove a non-remediating Cloud PC monitor pilot

- **Kind:** verification
- **Priority:** P1
- **Status:** proposed
- **Wave:** 2
- **Authorization:** azure-deployment
- **Blocker:** _none_
- **Claim:** _none_

**Problem:**

Deterministic fixtures establish logic but not Windows 365 collection, state retention or real notification routing.

**Scope:**

- docs/validation.md
- docs/operations.md
- scripts/Test-LocalFixtures.ps1

**Acceptance:**

- Record collection mode, read permissions, grace periods, durable fingerprints and acknowledgement suppression.
- Pilot stays dry-run first; any real Teams send is separately authorized with recipient-visible evidence.
- No delete, resize or reprovision occurs; unsupported/stale API data remains a visible gap.

**Validation:**

- From the solution root run ./scripts/validate.ps1
- Run focused tests for changed behavior from tests/; fixtures do not prove live-service or endpoint behavior.
- After separate authorization, retain redacted exact-target live evidence and cleanup results outside public Git. Do not execute live operations from this backlog alone.

**Dependencies:**

- _none_

**Components:**

- _none_

**Sources:**

- README.md
- docs/configuration.md

**Evidence:**

- _none_

**Review and authorization note:**

Review CPC-002 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.

## CPC-003: Add a controlled alert acknowledgement interface

- **Kind:** feature
- **Priority:** P2
- **Status:** done
- **Wave:** 2
- **Authorization:** local-only
- **Blocker:** _none_
- **Claim:** _none_

**Problem:**

Durable acknowledgement state exists; the documented operator workflow can be improved without adding remediation.

**Scope:**

- src/
- docs/operations.md
- tests/

**Acceptance:**

- Acknowledge only an exact alert identity with actor/time provenance and expiry/reopen rules.
- Fixtures prove acknowledgement suppresses delivery while preserving audit history and repeat-state behavior.
- Never change a Cloud PC or broaden collection permissions as part of acknowledgement.

**Validation:**

- From the solution root run ./scripts/validate.ps1
- Run focused tests for changed behavior from tests/; fixtures do not prove live-service or endpoint behavior.

**Dependencies:**

- _none_

**Components:**

- _none_

**Sources:**

- docs/architecture.md

**Evidence:**

- Implemented exact fingerprint/episode/acknowledgement-revision operator interface with asserted actor provenance, UTC time, explicit finite expiry, observed-resolution reopening and append-only audit history. Existing legacy acknowledgements retain suppression with unknown provenance. This is a source-level/local feature implementation; source and local feature acceptance passed independent R3 review; live-service acceptance remains separate. CPC-002 remains proposed for live Table, Graph and recipient qualification.
- Alert updates and audit insertion use same-partition conditional transactions with observed non-wildcard ETags. Shared bounded CAS preserves concurrent acknowledgement during timer synchronization, resolution and notification bookkeeping. Mutation SDK retries are disabled; ambiguous outcomes are not blindly retried. Identical request-event replay resolves acknowledgement ambiguity, while different reuse/stale identity is refused. Existing notification interval/retries/HTTP-versus-recipient boundary remain.
- PowerShell 7.6.6 R2 registered validation passed Bicep 0.46.1, PowerShell parsers, Python compilation and 59 unittest methods &lpar;24 existing plus 35 feature/regression methods&rpar;. Actual rules/state/notifier/CLI and production Table SDK fake-wire tests cover exact suppression/expiry/reopen/history, 409/412 races, atomic audit refusal, replay/lost response, HTTP500/no retry, strict ETag/row binding, bounded history and safe projections. Twelve repair methods additionally cover stale health snapshots, captured episode resolution, equal-time ambiguity, dispatch requalification, active grace-row deletion and post-resolution grace, absent legacy health clocks and six missing/malformed/wrong exact audit readbacks. Local deterministic fixture reporting and canonical backlog/partial permission checks passed; no live service, authentication, recipient send, Graph mutation or Cloud PC change occurred.
- Preserved existing deployment, collection, package/runtime dependency and permission-grant source. Added a partial source-hashed permission inventory with explicit baseline/operator/live gaps; it authorizes no grant. Hosted validation selects hash-pinned PowerShell 7.6.6 before any pwsh execution; no lower-version validation is qualified.
- Independent R1 review found stale resolution could resolve a newer acknowledged health observation after CAS retry, and a successful transaction with absent audit readback could return complete/null. R1 and failed/reproduction evidence are preserved. R2 orders synchronization/resolution by captured health timestamps and episode, returns only current candidates, rechecks before dispatch and requires exact validated successful audit readback without a second transaction. Equal-time conflicting or unknown legacy health ordering fails closed. Active episodes keep durable firstSeen even if older snapshots delete grace observations; post-resolution grace excludes pre-resolution observations. Pre-activation observation rows retain non-transactional monitor behavior and can still delay first activation under overlaps; no live concurrency or exactly-once guarantee is claimed.
- Independent R2 review reproduced same-episode out-of-order successful sends rolling lastNotifiedAt backward despite notificationCount2. R3 preserves the latest parsed UTC successful timestamp while counting both acknowledgements, retains captured-episode refusal and no ambiguous mutation replay, and rejects malformed input/stored times without writing. Six new actual rules/notifier/production Table SDK fake-wire methods cover both completion orders, the 24-hour repeat boundary, reactivation during an old in-flight request, timezone normalization and malformed timestamps. PowerShell 7.6.6 full registered validation passed 65/65 methods with Bicep 0.46.1/parser/Python compilation/deterministic fixture/schema/view/source-permission/protected-baseline checks. R2 and independent failed evidence remain preserved; the R3 candidate was held for independent review before publication, with no live service or recipient acceptance claim.
- Independent R3 review passed the exact source after all three reproduced defects were repaired. A fresh private PowerShell 7.6.6 replay passed 65 tests; independent actual Table SDK/full notifier overlap counted both acknowledged sends, retained the latest UTC success timestamp and proved the exact 24-hour repeat boundary. All three original acceptance statements have source/offline evidence. This done status covers the local acknowledgement feature only; CPC-002 remains open for live Table, Graph and recipient qualification.

**Review and authorization note:**

Review CPC-003 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.

## CPC-007: Add optional read-only deployment-validation wrapper

- **Kind:** feature
- **Priority:** P2
- **Status:** done
- **Wave:** 2
- **Authorization:** local-only
- **Blocker:** _none_
- **Claim:** _none_

**Problem:**

The completed component assessment mapped management checks but left no executable shared deployment-validation interface.

**Scope:**

- scripts/Test-Deployment.ps1
- scripts/vendor/Azd.DeploymentValidation/
- azd-components.lock.json
- tests/test&lowbar;deployment&lowbar;wrapper.py
- docs/operations.md
- azd-permissions.json

**Acceptance:**

- Plan and unsupported delivery make no CLI/authentication calls; verification requires exact explicit targets and gates resource reads on matching enabled public-Azure cached context.
- Check exact Function runtime/system identity, identity-only storage and deployment/host configuration, direct unconditional expected RBAC roles and optionally one existing audit row using login; never run the monitor, send notifications, grant permissions or mutate resources.
- Write schema-validating safe reports using an immutable hash-locked engine; exercise the complete healthy subprocess sequence and negative boundary cases without claiming live runtime or delivery acceptance.

**Validation:**

- ./scripts/validate.ps1
- ./scripts/Test-LocalFixtures.ps1
- ./scripts/Test-Deployment.ps1 -Plan

**Dependencies:**

- CPC-004

**Components:**

- deployment-validation

**Sources:**

- docs/component-compatibility-assessment.md
- docs/operations.md

**Evidence:**

- Source implementation vendors deployment-validation 2.0.0 at immutable reviewed reference main 2b2e784ba11822272c0e4b8389976f95afafa9b9. Includes exact context/dependency gates, bounded read-only native CLI checks, secret-free report projection and optional key-only run/latest read. This done status covers source/offline feature acceptance only; CPC-002 live pilot remains proposed.
- PowerShell 7.6.6 focused subprocess fixtures passed ten methods, including the complete healthy sequence and malformed/denied provider cases. Actual installed Windows MSI CLI reached the expected wrong-subscription context failure with all target reads skipped; CLI default subscription remained unchanged. Independent review and exact-head hosted checks accompany the draft change; no deployment, target resource read, permission grant or delivery occurred.

**Review and authorization note:**

Review CPC-007 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.
