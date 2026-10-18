# Security Policy

## Supported versions

Security fixes go to the latest release on the current major version (4.x).
Pre-releases (`-beta`, `-rc`) are fixed in the next pre-release or final.

## Reporting a vulnerability

Please do not open a public issue. Report privately through GitHub:
**Security → Report a vulnerability** on
<https://github.com/PACE-1/shepherd/security/advisories/new>.

Include the version or image tag, what you did, and what you expected. Shepherd
holds API keys and health data, so anything that exposes them (authentication
bypass, path traversal out of the data folder, injection) is in scope.

This is a small project run in spare time. Expect an acknowledgement within a
week; fixes for confirmed issues ship in a patch release and are credited in the
release notes unless you prefer otherwise.

## Dependency monitoring

Dependabot proposes weekly updates for Python, the web UI, GitHub Actions and
Docker base images, and the `Audit` workflow runs `pip-audit` and `pnpm audit`
on every pull request and weekly.
