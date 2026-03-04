# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report them privately via GitHub's built-in Security Advisories:

1. Go to the **Security** tab of this repo
2. Click **Report a vulnerability**
3. Fill in as much detail as you can

You can also email the maintainer directly if you prefer — check the profile linked in CODEOWNERS.

We'll acknowledge your report within **72 hours** and aim to ship a fix or mitigation within **14 days** for critical issues.

## Scope

Things we care most about:

- Prompt injection that bypasses Sophia's consequence engine or risk classifier
- Auth bypasses in the API key middleware
- Tenant isolation failures (cross-tenant data access)
- Dependency vulnerabilities with a credible exploit path

## Out of scope

- Theoretical attacks with no practical exploit
- Issues in dependencies that have no available fix yet
- Bugs in example Hats that don't affect the core framework
