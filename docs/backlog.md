# Backlog: nathanmcnulty/azd-cloud-pc-recommendations

> Generated from `docs/backlog.json`. Edit the JSON source and regenerate this file.
> Standard: [azd agent backlog standard](https://github.com/nathanmcnulty/azd-reference/blob/main/standards/agent-backlogs.md). This link is review guidance, not a runtime dependency.

- **Schema version:** 1.0.0
- **Repository:** nathanmcnulty/azd-cloud-pc-recommendations
- **Source revision:** `2e247dc0895e7b4822ed74ffe58c0f5924ba5824`
- **Captured:** 2026-10-04
- **Items:** 5

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

## CPC-004: Evaluate shared notification and deployment contracts

- **Kind:** discovery
- **Priority:** P2
- **Status:** proposed
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

**Evidence:**

- _none_

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
- **Status:** proposed
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

- _none_

**Review and authorization note:**

Review CPC-003 against the current repository state. Its status or authorization class is not eligible for an actionable generated handoff. Do not claim or execute it without explicit selection, satisfied dependencies, and every required authorization. Never interpret this generated view as approval.
