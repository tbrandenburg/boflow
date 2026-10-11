# Boflow

**Shared household automation. Personal tools on each account.**

[![Check](https://github.com/tbrandenburg/boflow/actions/workflows/check.yml/badge.svg)](https://github.com/tbrandenburg/boflow/actions/workflows/check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](/LICENSE)

Boflow installs and updates **Node-RED, JupyterLab, and CLI tools** for individual
accounts on Ubuntu and macOS. Keep shared flows and pinned dependencies in one
**private household GitHub repository**; each account keeps its own work and secrets.
Updates run at graphical login or on demand, without an always-on coordinator.

[Get started](#get-started) · [Daily commands](#daily-commands) ·
[Configuration](#configuration) · [Publish changes](#publish-household-changes) ·
[Operating guide](/AGENTS.md) · [Validation](#development-and-validation)

## What you get

| Tool | Purpose | Default loopback port |
| --- | --- | --- |
| Managed Node-RED | Runs published household flows | `11880` |
| Personal Node-RED | Your flows, credentials, and extra palette modules | `11881` |
| JupyterLab | Your notebooks and a managed Python 3.12 environment | `11882` |
| npm / Python CLI tools | Household-selected tools in account-local releases | — |

The initial palette includes Telegram, `@tbrandenburg/node-red-agents`, and
`@flowfuse/node-red-dashboard`. Publish dashboard nodes to create a dashboard;
the starter flow is empty. Provider credentials, bot configuration, and optional
agent CLIs are separate prerequisites.

### How it fits together

```text
Public Boflow product          Private household repository
  Python orchestrator           Flows + manifests + lockfiles
  Native package playbook       Exact product commit pin
             \                  /
              Login / manual update
                       |
              Each participating account
              ├── Managed Node-RED
              ├── Personal Node-RED + local credentials
              ├── JupyterLab + local notebooks
              └── Account-local runtimes and CLI tools
```

Dependencies are prepared before running services are interrupted. Unchanged
healthy services keep running; a shared-flow change restarts managed Node-RED
only. Login updates never run sudo or Homebrew. Application activation recovery
is manual; previous release caches are retained.

## Get started

### Requirements

- **Ubuntu x86_64/ARM64** or **macOS Intel/Apple Silicon**, with a graphical login.
- Git, `make`, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Internet access for initial setup and updates.
- Administrator: authenticated GitHub CLI for private repository creation.
- macOS: Command Line Tools and a designated Homebrew owner.
- Ubuntu: administrator-provisioned prerequisites and a running systemd user manager.

Run account commands as the participating account. Keep its product checkout in
place: the installed launcher references the bootstrap Python environment.

### 1. Create the household repository — administrator

```sh
git clone https://github.com/tbrandenburg/boflow.git
cd boflow
make bootstrap
make init-home BOFLOW_REPO=OWNER/HOUSEHOLD BOFLOW_DIR="$HOME/my-household"
```

This copies missing starter files, pins the current product commit, creates a
**private** repository, and pushes `main`. Existing public repositories are
refused. Review the [starter configuration](/examples/household) before adding
real household settings. Keep the authoring checkout separate from deployment.

### 2. Enroll each account — member with administrator assistance

From an account-owned product checkout, run `make bootstrap`, then:

```sh
make enroll BOFLOW_REPO=OWNER/HOUSEHOLD
```

The administrator adds the printed **public** key at the printed GitHub settings
URL as a **read-only deploy key**. Leave “Allow write access” unchecked. The private
key stays on this account; members do not need GitHub accounts. SSH accepts the
first GitHub host key and pins it locally; preverified keys can be provisioned
before enrollment where required.

### 3. Install prerequisites and register — participating account

```sh
make native          # Explicit admin authorization; Ubuntu prompts for sudo
make register-user   # Ports 11880, 11881, 11882 by default
make status
make open
```

On macOS, run native maintenance as the Homebrew owner. If another account owns
Homebrew, have that owner install the declared packages separately and skip
`make native` for the member. Do not change Homebrew ownership or run brew as root.

Registration prepares applications, installs login startup, starts three services,
and checks their HTTP endpoints. `make status` should report them reachable and
show the applied household/product commits. `make open` opens a private local
link page, including authenticated Jupyter access.

**Another account or a port conflict?** Choose a free block before registration:

```sh
make register-user BOFLOW_PORT_BASE=11980
```

Ports are preserved on reruns. The installed command is
`$HOME/.local/share/boflow/bin/boflow`; it also accepts
`register-user --port-base 11980`, overriding `BOFLOW_PORT_BASE`.

## Daily commands

Run these from the retained product checkout, or use the installed `boflow` CLI.

| Make target | What it does |
| --- | --- |
| `make open` | Open the private local tool page |
| `make status` | Show commits, update status, and reachable ports |
| `make doctor` | Inspect platform and prerequisite availability |
| `make update` | Fetch household `main` and apply its pinned product |
| `make logs` | Show recent update output; inspect service logs privately |
| `make native` | Explicitly install missing declared native packages |
| `make update-system-tools` | Explicitly upgrade declared native packages |
| `make uninstall` | Remove services/login startup and retain account data |

At graphical login, installed services start before the update check. Offline
login retains the installed services and records the failed check for diagnosis.
There is no periodic updater or OS upgrade job.

## Configuration

| Input | Role |
| --- | --- |
| `BOFLOW_STATE` | Account state location; default `$HOME/.local/share/boflow` |
| `BOFLOW_PORT_BASE` | First of three registration ports; default `11880` |
| `BOFLOW_REPO` | Makefile household repository input: `OWNER/NAME` |
| `BOFLOW_DIR` | Makefile household working-checkout input |
| `BOFLOW_PYTHON` | Makefile interpreter override; defaults to the local venv if present |

Boflow-owned inputs use `BOFLOW_`. External tools and the OS retain their required
environment names. Set `BOFLOW_STATE` consistently when using a custom installation.

The private repository contains `home.yml`, Node-RED/npm manifests and lockfiles,
Jupyter's `pyproject.toml`/`uv.lock`, and `tools/python-tools.txt`. Use exact direct
versions and a full published product commit SHA. Python is 3.12 in v1. Python CLI
tools pin direct versions; uv resolves their transitive dependencies at install time.
Optional account-local `local.yml` overrides native package lists only.

## Publish household changes

Author shared flows in the maintainer's **personal** Node-RED, then export into
the separate private household working checkout:

```sh
make export-managed-flows BOFLOW_DIR="$HOME/my-household"
# Edit manifests/tool lists as needed, then refresh locks.
make lock BOFLOW_DIR="$HOME/my-household"
```

In that household checkout, review `git diff`, stage named files, commit, and push
`main`. Publish manifests **with** their lockfiles. Members receive the change at
next login or manual update. Test one account before updating the others.

Export strips inline credentials; encrypted credentials remain local. Verify
secret references, required nodes, platform-specific commands, and scheduled
side effects before publishing. Managed-editor changes may be replaced by a
later shared-flow update. See the [publishing guide](/AGENTS.md#5-publish-shared-flows-maintainer).

## Access, backup, and removal

Services bind to `127.0.0.1`. Node-RED is unauthenticated and reachable by other
local accounts: this is a trusted-household setup. The private local page contains
the Jupyter token; do not publish it or paste raw service logs into shared channels.

For remote administration, explicitly enable OS SSH and forward the relevant
account port, for example `ssh -L 11880:127.0.0.1:11880 ACCOUNT@IP`. Remote notebook
or flow editing executes code as that account. No LAN gateway or SSO is provided.

Back up `personal/`, `notebooks/`, managed runtime context, `account.json`,
`secrets.env`, and credential keys separately from Git. Stop services or use a
consistent backup tool. Preserve credential keys to keep stored credentials usable.

`make uninstall` (alias for `make remove-user`) removes services and login startup,
**preserving data, secrets, runtimes, and account state**. The administrator revokes
the deploy key separately. Native packages remain installed. Release-cache cleanup
and bad-release recovery are manual; use the [operating guide](/AGENTS.md#10-diagnose-repair-recover).

## Development and validation

```sh
uv sync --locked
make check
.venv/bin/ansible-playbook --syntax-check -i localhost, ansible/native.yml
make acceptance BOFLOW_PORT_BASE=11880
```

CI checks orchestration and application startup on Linux/macOS. The Ubuntu native
roundtrip has been exercised with real user services: registration, authenticated
application checks, unchanged updates, managed-only restart, offline login, and
uninstall. `make acceptance` uses disposable local Git repositories and removes
its test state; it requires no existing Boflow service files and a working user manager.

Actual logout/reboot, macOS native sessions, simultaneous accounts, GitHub key
authorization, and administrator package consent need separate target-machine
checks. Follow [tests/acceptance.md](/tests/acceptance.md) before unattended deployment.

Contributions should follow [SCOPE.md](/SCOPE.md) and [AGENTS.md](/AGENTS.md).
Open an [issue](https://github.com/tbrandenburg/boflow/issues) for bugs or scope
proposals; keep private configuration and logs out of reports. Extra ideas live
in [BACKLOG.md](/BACKLOG.md).

## License

[MIT](/LICENSE).
