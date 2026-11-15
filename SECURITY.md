# Security Policy

## Supported Versions

The following table lists the security support status for versions of Banking Cells Architecture Lab — Community Edition:

| Version | Supported          |
| ------- | ------------------ |
| Pre-release Community Edition | Security fixes evaluated case by case; no published support commitment |

## Reporting a Vulnerability

Consulting RIOM S.A.S. takes the security and integrity of software implementations seriously.

If you identify a security vulnerability or sensitive information exposure in this repository, please disclose it responsibly:

1. **Do not create public GitHub issues or discussions** for suspected vulnerabilities.
2. Contact the project maintainers privately through the [Consulting RIOM corporate website](https://consultingriom.com/) or GitHub's private vulnerability reporting feature if enabled. Do not include exploit details in a public issue.
3. Include:
   - Detailed description of the vulnerability.
   - Minimal reproducible steps or proof of concept.
   - Impact assessment.
   - Affected files and components.

### Response Handling
Reports are assessed based on impact, reproducibility and available maintainer resources. No specific response-time guarantee is established for this Community Edition.

## Responsible Disclosure & Synthetic Data Scope
Banking Cells Architecture Lab — Community Edition is designed to operate **exclusively with synthetic data** in local or controlled development environments. The built-in HTTP server (`app/api.py`) binds strictly to `127.0.0.1` by default and is intended for demonstration, architecture evaluation, and educational testing. It does not provide multi-tenant authentication, authorization, or production TLS/SSL termination out of the box and must never be exposed directly to untrusted networks without appropriate reverse proxy and access control layers.
