# Cloud PC operational recommendations and alerts

`azd-cloud-pc-recommendations` is a private work-in-progress repository for turning Windows 365 and Cloud PC operational signals into administrator actions. It is not intended to replace the recommendations experience already available in Intune.

## Status

This repository is a design placeholder. It does not yet contain an `azure.yaml`, Azure infrastructure, deployment hooks, or a supported monitoring service. **Do not run `azd init` or treat this repository as deployable.**

The first deployable milestone is intended to:

- alert on unused Cloud PCs, provisioning failures, and unhealthy or stale devices;
- apply configurable thresholds, grace periods, severity, routing, and deduplication;
- deliver Microsoft Teams notifications through an explicit supported integration;
- use managed identity and least-privilege Microsoft Graph permissions;
- operate in dry-run mode by default, with remediation separately gated and never destructive by default.

## Administrator safety goals

The future template must explain Windows 365 and Intune licensing, permissions, consent, throttling, storage, retention, cost, and cleanup before deployment. It must preserve existing Cloud PCs and tenant configuration unless a reviewed remediation is explicitly authorized.

## Development plan

The current product direction and initial implementation requirements are in [STARTING-PROMPT.md](STARTING-PROMPT.md). The repository will receive an administrator quickstart only after a complete template can be initialized and validated end to end.
