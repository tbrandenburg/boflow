# First release contract

Boflow installs and maintains native, account-local household tools on macOS Intel,
macOS Apple Silicon, and Ubuntu x86_64/ARM64. Support is capability checked; no
claim of compatibility with every OS release. Unsupported platforms fail clearly.

## Included

- Public product repo; easy creation of a separate private household repo.
- Exact product commit pin; schema 1 household configuration.
- One guided setup command, resumable enrollment, and reviewed administrator
  approval of read-only deploy keys without member GitHub accounts.
- Explicit Ansible native package installation/upgrade; no unattended sudo.
- Pinned account-local Node distribution with HTTPS checksum verification.
- Managed/personal Node-RED, Jupyter Python 3.12, npm and Python CLI tool lists.
- Login/manual updates, bounded commands, per-account lock, loopback-only services.
- Personal data preservation, local navigation, status/logs, documented manual recovery.

## Acceptance criteria

1. A fresh supported account registers, starts all three services, and opens tools.
2. Repeated registration/update preserves ports, secrets, flows, notebooks, and extra personal modules.
3. Unchanged configuration does not restart healthy services.
4. A managed flow change restarts managed Node-RED only.
5. Dependency preparation failure leaves running services untouched.
6. Two accounts can operate concurrently without shared mutable application state.
7. Offline login starts installed services and records a failed update check.
8. No native package manager or interactive password prompt runs during login updates.
9. Private repo creation refuses public existing repositories.
10. Removing services retains data and documents deploy-key revocation.
11. All setup/removal/recovery journeys are documented and exercised.
12. Guided setup handles missing prerequisites with consent and chooses free ports;
    repeated approval never duplicates keys or grants write access.

Automated tests cover orchestration and failure boundaries; real native session,
permission, hardware, and application checks are required on target machines.

## Explicitly excluded

Fleet dashboards, HTTP gateways, SSO, periodic checks, flow merging, custom storage
plugins, automated rollback, secret synchronization/rotation, shared Telegram receiver
coordination, OS upgrades, monitoring/enforcement policies, provider/agent CLI setup,
automatic cache garbage collection, and distribution support beyond Ubuntu.

One implementation path per platform. No discovery server, plugins, or generic
framework. Stop once acceptance checks pass. Additional work requires an observed
manual burden and a separate scope decision; record it in BACKLOG.md first.
