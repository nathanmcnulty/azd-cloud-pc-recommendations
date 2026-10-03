# Backlog: nathanmcnulty/azd-cloud-pc-recommendations

> Generated from `docs/backlog.json`. Edit the JSON source and regenerate this file.
> Standard: [azd agent backlog standard](https://github.com/nathanmcnulty/azd-reference/blob/main/standards/agent-backlogs.md). This link is review guidance, not a runtime dependency.

- **Schema version:** 1.0.0
- **Repository:** nathanmcnulty/azd-cloud-pc-recommendations
- **Source revision:** `2f1fab5b13fa11c3f6a993f7ab44cb47c765262d`
- **Captured:** 2026-10-03
- **Items:** 4

## CPC-001: Reconcile this backlog with current source and active work

- **Kind:** discovery
- **Priority:** P1
- **Status:** ready
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

- _none_

**Agent handoff prompt:**

```text
Review CPC-001 in docs/backlog.json and changes since backlog source revision 2f1fab5b13fa11c3f6a993f7ab44cb47c765262d.
Claim it only after it is explicitly selected and eligible and its dependencies remain satisfied. Never interpret this generated prompt as approval.
Work only in nathanmcnulty/azd-cloud-pc-recommendations, preserve its stated scope and acceptance gates, record the exact current base commit and one owned worktree in claim, run every validation entry, and record concrete evidence before marking it done.
Stop if the dependencies, scope, or required authorization changed.
```

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
