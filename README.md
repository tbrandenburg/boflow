# Boflow

A small product for keeping household computers useful without visiting each one.
Boflow runs native Node-RED and JupyterLab services per account on macOS (Intel and
Apple Silicon) and Ubuntu. A **private household GitHub repository** declares your
shared flows and tools; this public repository contains only the product.

**First release: implementation for review and machine validation.** Automated
checks run locally and in CI. macOS login behavior and Ubuntu desktop sessions
must be verified on your actual machines before treating this as unattended production setup.

## What each account gets

- Managed Node-RED flows and a centrally selected module list.
- Separate personal Node-RED flows and palette additions that updates preserve.
- JupyterLab, a Python kernel, and configurable Python packages.
- Managed npm CLI tools and isolated Python CLI tools; uvx remains available.
- Local access page, status, logs, and manual recovery procedures.

Initial Node-RED modules: Telegram, `@tbrandenburg/node-red-agents`, and
`@flowfuse/node-red-dashboard`. No bot receiver or monitoring policy is enabled
by default. The agents module's optional external CLIs and provider credentials
are configured separately. The empty initial flow means a dashboard page appears
only after you publish dashboard nodes.

## Start as administrator

Install Git, `make`, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
On Mac install Apple's Command Line Tools (`xcode-select --install`) and Homebrew
as the account designated to maintain it. Ubuntu's administrator installs these
prerequisites with apt. Do not run Boflow bootstrap as root.

```sh
git clone https://github.com/tbrandenburg/boflow.git
cd boflow
make bootstrap
# GitHub CLI must be installed and authenticated for this admin command.
make init-home REPO=YOUR-NAME/my-household DIR="$HOME/my-household"
```

`init-home` creates a **private** repository, copies starter configuration, pins
the product to this checkout's exact commit, commits it, and pushes `main`.
It refuses to push to an existing public repo. Review starter content before
publishing any real configuration. Repo creation is an explicit command, never a
side effect of member registration.

## Enroll each participating account

Run bootstrap from a checkout owned by that account. Then:

```sh
make enroll REPO=YOUR-NAME/my-household
```

An administrator adds the printed **public** key at the printed GitHub settings
URL. Leave **Allow write access** unchecked. The private key stays on that account.
No member GitHub account is required. GitHub's SSH host key is accepted on first
connection and then pinned in the account's known_hosts file; environments needing
preverified host keys can provision that file before connecting.

Once authorized, perform explicit native setup as the administrator/package owner:

```sh
make native            # Ubuntu prompts for sudo; Homebrew runs without sudo
make register-user     # run as the participating member in a desktop session
make open
```

On a Mac where a different account owns Homebrew, that owner installs the native
packages listed in `home.yml` once; members skip `make native`. Never change the
Homebrew prefix ownership or run brew under sudo to accommodate a member.

The installed command is `~/.local/share/boflow/bin/boflow`. Add that directory
and the paths printed in [AGENTS.md](AGENTS.md) to your shell PATH if desired.
Keep the bootstrap checkout in place: the launcher references its Python environment.

## Updates

After each graphical login, installed services start, then an update check runs
in the background. It fetches household `main` and the product commit pinned in
`home.yml`, validates configuration, prepares dependencies, and restarts affected
services. No periodic checks or OS upgrades run. Offline login leaves services
using their installed configuration. Run `make update` for an immediate check.

Native packages require `make native` (missing packages) or
`make update-system-tools` (explicit upgrades). Login updates never invoke sudo
or Homebrew. Native dependencies discovered during application preparation are
reported through the failed preparation log; install them explicitly and retry.

Each account is independent and has its own deploy key and update lock. No service
runs as root. Personal data is outside both Git checkouts.

## Publishing household changes

Use the **personal** Node-RED instance on your designated authoring account.
Export its flows into your separate household working checkout:

```sh
make export-managed-flows DIR="$HOME/my-household"
# Edit node-red/package.json, jupyter/pyproject.toml, or tools lists as needed.
make lock DIR="$HOME/my-household"
cd "$HOME/my-household"
git diff
# Stage named files; never indiscriminately add secrets or personal data.
git add node-red/flows.json node-red/package.json node-red/package-lock.json
git commit -m "Update shared automation"
git push origin main
```

Publishing is the release decision. Export does not copy encrypted credentials;
verify local secret references and all required node types before publishing.
Managed-editor changes are temporary and may be replaced by the next flow update.

## Access and privacy

Applications bind only to `127.0.0.1`. The local access page includes a private
Jupyter token so members do not enter a login. Do not share that file. Local
Node-RED editors are unauthenticated: other users on the same machine can reach
them. This is a cooperative, mutually trusted household setup, not user isolation
or tamper-resistant enforcement.

Remote administration uses SSH tunnels. Enable OS SSH access explicitly, discover
ports through `make status`, and forward them (example port only):

```sh
ssh -L 23000:127.0.0.1:23000 alice@PC-IP
```

Open localhost port 23000 on your admin computer. For Jupyter retrieve its token
privately from that account or use Jupyter's password setup. Remote notebook/flow
editing grants execution as the target account. There is no LAN gateway or SSO.

## Configuration and data

Household config is `home.yml` plus manifests/lockfiles in `node-red/`, `jupyter/`,
and `tools/`. Optional account-local `~/.local/share/boflow/local.yml` overrides
**native package lists only**; no host inventory is required. See the examples.

State resides at `~/.local/share/boflow/` (mode 0700), configurable via
`BOFLOW_STATE` when bootstrapping. `account.json` holds stable ports, repo identity,
and update status. `personal/`, `managed/`, and `notebooks/` hold account data;
`secrets.env` contains optional `KEY=value` values without shell expansion.
Jupyter token and Node-RED credential keys are generated once and retained.

Back up personal data, notebooks, and credential keys separately from Git.
Application release caches are retained for diagnosis; monitor disk space and
remove unused releases manually only after stopping services and inspecting
current symlink targets. Automatic cache pruning is outside v1.

## Maintenance

`make status`, `make doctor`, `make logs`, `make update`, and `make remove-user`
cover normal operation. Removal stops startup/services and **retains all data**;
the administrator revokes the deploy key separately. Recovery is manual, not
automatic rollback.

[AGENTS.md](AGENTS.md) documents all journeys, expected results, recovery, and
human handoffs. [SCOPE.md](SCOPE.md) defines the finish line. For development:

```sh
uv sync --locked
make check
.venv/bin/ansible-playbook --syntax-check -i localhost, ansible/native.yml
```
