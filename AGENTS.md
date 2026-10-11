# Boflow agent operating guide

Read SCOPE.md before changing code or enrolling machines. Implement only what its
acceptance criteria require. Prefer existing tools and explicit configuration.
Do not add a service, abstraction, or dependency unless an acceptance criterion
requires it. Record extra ideas in BACKLOG.md without implementing them.

This public repo must never contain real household configuration, hostnames,
account names, tokens, keys, or personal data. Examples contain placeholders only.
The household repository must be private. Local account state is private to its
owner. Do not paste raw service logs or index.html into chat: they may contain tokens.

## Authority and starting checks

Use supported commands; do not rewrite OS service managers or package prefixes.
Inspect `status`, `doctor`, existing account state, Git changes, and platform first.
Run account commands as the participating account, never root. Native package
setup is an explicit administrator action. GitHub writes/publishing require the
user's task authorization; initialization explicitly requests creation of a
private repository. Credential entry and OS consent are human handoffs. Never
ask users to paste secrets into chat. Never disable host-key checking.

The installed command is `$HOME/.local/share/boflow/bin/boflow` (or the state
chosen at bootstrap). Commands below use `boflow` for that executable. Makefile
commands are equivalents from the product bootstrap checkout after `make bootstrap`.
The account updater fetches only household `main` and its pinned product commit.
The private Git deployment checkout is disposable; the maintainer working checkout
is separate and must never be reset by the updater.

Boflow-owned configuration uses the BOFLOW_ namespace: BOFLOW_STATE selects state,
BOFLOW_PORT_BASE selects initial ports, and Makefile inputs are BOFLOW_REPO,
BOFLOW_DIR, and BOFLOW_PYTHON. Preserve external-tool/OS environment names.
The CLI --port-base option takes precedence over BOFLOW_PORT_BASE.

## 1. Create a household (administrator)

Prerequisites: Git, make, uv, GitHub CLI with authenticated repository-creation
permission, and a product checkout. Inspect the intended local directory; do not
use one containing private material unrelated to the starter.

1. `make bootstrap` creates the locked product Python environment and launcher.
2. `make init-home BOFLOW_REPO=OWNER/NAME BOFLOW_DIR="$HOME/my-household"` populates starter files
   only when missing, pins this product commit, creates a PRIVATE repo, and pushes main.
3. Verify GitHub visibility is private, origin matches, starter lockfiles are present,
   and the product commit is published/retrievable. A local unpushed commit is not deployable.
4. Configure package lists and shared flows in the household working checkout.

Rerun: never overwrites existing files; resumes a private repo push. If authentication
or repository creation fails, keep local files, authenticate through gh's human
flow, inspect `git status`, and retry. Existing public repo: stop; do not push.
The web alternative is creating a private repo manually, checking visibility, then
pushing the explicitly reviewed starter files. No member needs a GitHub account.

## 2. Bootstrap and enroll an account (admin-assisted)

Prerequisites: macOS/Ubuntu, supported CPU, internet for initial setup, account-owned
product checkout. Mac needs Command Line Tools and a Homebrew owner; Ubuntu needs
Git/make/uv provisioned by the administrator. Use `make bootstrap` as this account.
If uv is absent, hand off installation using its official instructions; bootstrap
never silently executes a downloaded installer. Keep this checkout in place.

1. `boflow enroll --repo OWNER/NAME` generates an account-specific deploy key.
2. Admin registers the printed PUBLIC key at the settings URL as read-only.
3. The private key remains local; never copy it to household members or Git.
4. Initial native setup: `boflow native` fetches config without preparing applications.
   On Ubuntu the admin authorizes sudo. On Mac run it as the Homebrew owner, or have
   that owner install the listed packages separately. Members do not take over brew.

Verification: fetch succeeds using the deploy key; installed native prerequisites
exist. Rerun reuses the key and preserves configuration. Repo mismatch: inspect the
existing enrollment rather than replacing it. Permission/network failure: register
or repair read access and retry. SSH uses accept-new for the first github.com key,
then pins it; preprovision independently verified known_hosts if required.

## 3. Register a household member

Prerequisites: completed account enrollment, prerequisites, a graphical login.
Run `boflow register-user` from THAT account. It assigns a stable block
of ports, prepares applications, generates stable local secrets, installs login
startup, starts services, and verifies their HTTP endpoints.

Expected: `boflow status` reports three reachable services and applied household/
product commits; `boflow open` opens a private local link page. The empty initial
flow has no dashboard until nodes are published. Rerun preserves personal data,
extra palette packages, ports, credential keys, and notebooks.

Port conflict: stop, inspect listening ports, choose three unique ports in local
account.json, and rerun. For an existing registration, remove its services before
editing ports. Do not kill unrelated processes.
For initial explicit selection use `make register-user BOFLOW_PORT_BASE=11880` or
`boflow register-user --port-base 11880` (three consecutive ports).
The default block is 11880–11882; additional accounts on one machine need a
different free block.
Failed preparation: read update/service logs locally; install missing native prerequisites explicitly.
Partial registration can be resumed. Never claim completion if health checks fail.

Linux XDG graphical autostart invokes login with session environment, then starts
systemd user services. macOS uses LaunchAgents. An SSH-only initial session is not
supported for registration. No linger/boot services are installed.

## 4. Open and use tools (member)

`boflow open` launches the private local page. Personal Node-RED owns local flows
and palette additions. Managed Node-RED runs published flows; editor modifications
are temporary. Jupyter notebooks live in the local notebooks directory; household
pyproject changes configure its managed environment. Project-specific kernel
management is outside v1; normal notebook functionality remains available.

No extra login is entered locally. Node-RED is unauthenticated on loopback, which
is accessible to OTHER local accounts: household trust is required. index.html
contains the Jupyter token and must not be served publicly. Provider credentials
and optional agents CLIs (opencode/pi/gh/sandboxing, depending on package use)
are independent prerequisites. Never report these integrations usable just because
their Node-RED package installed.

Optional shell PATH (substitute the selected state path):
`$HOME/.local/share/boflow/tools-npm/node_modules/.bin`
`$HOME/.local/share/boflow/tools-python/bin`
`$HOME/.local/share/boflow/runtimes/node-VERSION/bin`
`$HOME/.local/bin` (uv and uvx)
Service PATH is configured automatically; member shell startup files are not rewritten.

## 5. Publish shared flows (maintainer)

The designated maintainer uses their PERSONAL Node-RED as the authoring source.
`boflow export-managed-flows --directory "$HOME/my-household"` exports flows into
that separate working checkout, strips inline credentials, and leaves local
credential storage alone. Review the diff, references to local secrets, stable IDs,
required modules, OS-specific shell commands, and duplicate scheduled side effects.
Export does NOT prove a flow will run elsewhere. Each node's credential support
must be checked; encrypted credentials are not propagated in v1.

Stage named files, commit, and push main when authorized. Do not automate publishing
from member accounts or give deploy keys write access. Verify the pushed commit;
other members receive it at next login/manual update. No always-on coordinator.

## 6. Change modules, tools, and product version

Edit the private repo's node-red/package.json (exact versions), jupyter/pyproject.toml,
tools/npm/package.json, or tools/python-tools.txt (`package==version` lines).
`boflow lock --directory "$HOME/my-household"` refreshes npm and Jupyter lockfiles
using npm/uv installed on the maintainer's PATH. Commit manifests AND lockfiles.
Baseline personal Node-RED dependencies follow these versions; extras remain local.
Python CLI tools use uv tool install in isolated release directories; uvx is for
one-off tools. CLI direct versions are pinned; their transitive dependencies are
resolved by uv at installation (not a fully locked Python project).

Changing home.yml product_ref upgrades the product; use a full published commit
SHA and keep schema 1. Node is an exact upstream version, Python is 3.12 in v1.
After publishing, test one account before updating the others. Unknown schema or
incompatible version: report it; no guessed migration. Native lists change only
when administrator runs native or native --upgrade, never in login updates.

## 7. Login and update

At graphical login installed services start first. Then `boflow login` checks
household main. `boflow update` checks immediately. Per-account lock rejects an
overlap; another account is independent. There is no periodic update job.

Update selects one household commit, validates it, fetches exact product commit,
prepares missing application releases, then stops/restarts only affected services.
Personal dependencies are merged with the baseline without dropping extras.
Unchanged healthy services are not restarted. Dependency preparation errors leave
services untouched; activation failure requires manual recovery. Status marks a
commit successful ONLY after health checks. Product preparation is not automatic
rollback. Caches retain previous releases and can consume substantial disk space.

Offline: login still starts installed services and records update failure; retry
next login or manually. A fresh account cannot bootstrap offline. Background jobs
do not display interactive password prompts. Desktop/session-specific scripts
remain flow responsibilities, not management-product policies.

## 8. LAN administration

Use OS SSH, explicitly enabled by the admin, plus tunnels to the account's ports.
Read `status`; `ssh -L LOCALPORT:127.0.0.1:REMOTEPORT account@IP` forwards one tool.
No mandatory DNS, public app ports, gateway, or single sign-on. If Jupyter needs
its token, obtain it privately from the account's jupyter-token file; never print
it in shared logs. Remote editing permits code execution as that account.
Run remote updates as that account; registration needs its graphical session.

## 9. Secrets, permissions, and backup

Optional local secrets.env uses uppercase KEY=value, no quotes/expansion/execution.
Only the owner should read it. Keep generated credential-key and jupyter-token
stable. Never rotate a Node-RED credential key without re-entering credentials.
OS Accessibility/Automation permissions are per-user human consent steps for
flows needing them; do not attempt to bypass OS consent.

Backup personal/, notebooks/, managed runtime context, secrets.env, account.json,
and credential keys separately from Git. Stop services while backing up mutable
state or use an appropriate consistent backup tool. Repo backups alone cannot
restore personal work or secrets. Restore permissions and test decryption/access.

## 10. Diagnose, repair, recover

`boflow status`, `boflow doctor`, and `boflow logs` reveal commits, ports, platform,
and recent update output. Linux service logs: `journalctl --user -u boflow-managed`
(or personal/jupyter). macOS service logs are in account state. Raw service logs
can include tokens; redact before sharing. Inspect attempt.json and last_success.

Preparation failure: fix missing dependency/access/config and rerun update.
Service failure: inspect native logs, ports, settings, and external integrations.
Restart via native manager, then verify endpoints. To recover bad shared config,
revert it in the household working repo, publish the revert to main, and update.
If product itself is broken, use the retained bootstrap checkout to correct the
product pin and publish; cached application pointers/data are retained. There is
no automated rollback. Do not delete state to troubleshoot.

## 11. Remove member / retire machine

As member: `boflow remove-user` unloads services/startup, marks account unregistered,
and preserves ALL files. `make uninstall` is the equivalent Makefile target.
Administrator separately revokes this deploy key in
GitHub. Repeat for each enrolled account when retiring a machine. Revocation stops
future fetches, not local services or previously downloaded data. Offline machines
cannot be remotely cleaned. Delete personal data only with explicit authorization
and after offering backup; do not turn removal into blanket home-directory cleanup.

To re-enroll in a different household, archive the retained state and bootstrap
with a new BOFLOW_STATE path, then register fresh. Do not silently repurpose an
existing deployment checkout/key. Local port selections must remain nonconflicting.

## 12. Validate a release

Run `uv sync --locked`, `make check`, and Ansible syntax-check. CI runs Linux/macOS
orchestration tests, not actual login enrollment. Then execute tests/acceptance.md
on target machines with disposable accounts. Record actual OS/CPU versions and
results. No production-ready or waterproof claim without those checks.

`make acceptance BOFLOW_PORT_BASE=11880` runs the real Ubuntu service roundtrip
with disposable local Git repositories, pinned runtimes, and application checks.
It refuses existing service files/loaded units, validates ports, invokes
`make uninstall`, verifies retained data, and deletes only its own test state.
Requires a working systemd user manager. It does not test macOS native sessions,
actual logout/reboot, simultaneous accounts, GitHub authorization, or native package
consent. Report these boundaries rather than marking unexercised checklist items done.
