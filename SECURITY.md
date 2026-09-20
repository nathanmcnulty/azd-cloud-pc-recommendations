# Security

## Reporting a vulnerability

This is a private work-in-progress repository. Use GitHub's private vulnerability reporting channel when available, or contact the repository owner privately. Do not disclose tokens, tenant identifiers, credentials, or other sensitive data in an issue or pull request.

## Scope

This template reads Cloud PC and Intune operational data and stores alert state and compact audit exports in its own Azure resources. It must not be used to bypass Intune, Windows 365, Microsoft Graph, or tenant administrator approval boundaries.

Never commit credentials, signing keys, webhook URLs, access tokens, connection strings, tenant exports, or production configuration. The default deployment is dry-run and the first milestone contains no remediation implementation.

Report behavior that could expose Cloud PC inventory, user identifiers, audit exports, or notification destinations privately. Include the affected commit and a sanitized reproduction; do not attach secrets or live tenant data.
