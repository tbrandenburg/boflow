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
commands are equivalents from the product bootstrap checkout after `make setup`.
The account updater fetches only household `main` and its pinned product commit.
The private Git deployment checkout is disposable; the maintainer working checkout
is separate and must never be reset by the updater.

## Command choices

Start with `make setup`. Do not walk users through bootstrap/enroll/native/register
as separate steps. Everyday Make commands: `setup`, `approve`, `open`, `status`,
`update`, and `help`. Diagnostics: `doctor`, `logs`. Administrator/maintainer:
`native` (`BOFLOW_UPGRADE=1` for upgrades), `remove-user`, `export-managed-flows BOFLOW_DIR=...`,
`lock BOFLOW_DIR=...`. Development: `check`. Removed Make wrappers: bootstrap, init-home,
enroll, register-user, login, update-system-tools, and the redundant uninstall alias. The corresponding installed CLI
commands remain for repair/internal startup; they are not an alternative onboarding.
Boflow inputs use BOFLOW_: BOFLOW_STATE, BOFLOW_DIR, BOFLOW_PYTHON.
BOFLOW_PORT_BASE/CLI --port-base remain for explicit low-level registration tests;
guided setup chooses free ports automatically. Preserve OS/external-tool names.
For developer environment setup without native changes: `uv sync --locked`.

## 1. Create a household (administrator)

Prerequisites: product checkout owned by the participating account, Git/make,
supported macOS/Ubuntu graphical session, initial internet access. A fresh Mac
may need Apple's Command Line Tools prompt completed before Git/make work.

1. Run `make setup`, choose create, enter GitHub URL or OWNER/NAME.
2. Wizard offers missing uv/uvx installation in ~/.local/bin without editing shell
   files. It offers Homebrew if needed and gh through apt/Homebrew. Each installer
   needs user consent; system password and GitHub browser/device sign-in are human
   handoffs. Do not ask for passwords/tokens in chat.
3. Confirm the private repository and separate household working directory. Starter
   files only are copied; public existing repositories are refused. Existing dirty
   household checkouts must be reviewed/committed explicitly, never auto-published.
   Missing Git identity is set locally from the administrator's GitHub identity;
   gh configures administrator HTTPS Git authentication. Product is pinned to this
   checkout's full published commit. Do not use an unpushed local product commit.
4. Confirm the account label and the displayed public-key fingerprint. The wizard
   registers a read-only deploy key using the admin's GitHub access.
5. Wizard offers missing native packages, registers startup/services, selects a free
   port block, checks all endpoints, and opens the private tools page.

Verification: repository PRIVATE, matching origin, committed manifest/lockfiles,
three reachable services, appropriate product pin. Rerun setup resumes; no key,
personal data or secrets are discarded. Failed creation preserves starter files;
rerun and choose the same repo/directory. Permission failure: authenticate with
repository-administrator permissions and retry, never make the repo public.

## 2. Join another account (member and administrator)

Run `make setup` in THAT account's graphical terminal, choose join, paste the
household URL, and choose a short account label. No member GitHub account needed.
Wizard generates an Ed25519 key, retains its private half locally, and prints a
one-line PUBLIC `boflow1:` request containing repo, label, and public key only.
Share the request through the household's normal communication channel.

Administrator runs `make approve` in their configured product checkout, pastes the
request, verifies the household/member label/fingerprint with the member, and
confirms. A request targeting another household or public repo is refused. An
already approved read-only key is reused; an existing write-enabled key is refused.
This command can install missing gh with consent and guide admin sign-in.
Do not auto-approve requests from an unverified source; labels are user supplied.

Member setup retries access for up to ten minutes, then continues. Ctrl-C pauses;
`make setup` resumes with the same key and repo. A timeout is not authorization:
check approval, network, SSH host key and repository identity, then retry. Never
copy private keys or administrator tokens to members. GitHub CLI authorization
revocation may remove keys created through it; preserve admin authorization or
register existing public keys manually through PRIVATE repo settings when changing
it. If access is revoked later, use `boflow enroll --repo OWNER/NAME` to display
existing public key, register it read-only again, then rerun setup/update.

SSH accepts a new github.com host key on first connection and pins it afterward.
Use independently verified preprovisioned known_hosts when required; never disable
host-key checking. Private deployment checkout is disposable, not authoring source.

## 3. Finish setup, resume, and verify

Wizard detects native prerequisites from the fetched household config. Ubuntu
installation requests consent and sudo. Mac checks Command Line Tools and Homebrew
formulae. Already installed native packages need no installation or ownership
handoff. Missing packages under another Homebrew owner pause with that owner's
exact `brew install` command; owner runs it, member reruns setup. Never change
prefix ownership or use sudo brew. These permissions cannot be bypassed by an agent.

Registration chooses free account-local ports automatically, prepares applications,
generates stable secrets, installs login startup, starts services, checks HTTP,
and opens tools. Expected: `make status` shows three reachable services and applied
commits. Empty initial flow has no dashboard until dashboard nodes are published.
Rerunning preserves extra palette packages, flows, notebooks, ports, and keys.
Saved ports are stable: later conflict requires inspecting listeners and explicitly
removing services and choosing a free block in account.json; never kill unrelated processes. Initial
port selection is a best-effort socket probe; a racing listener can still conflict.

Failed preparation: inspect local diagnostics, correct access/dependency/config,
and rerun setup. Never claim completion if health checks fail. Enrollment and native
installations already performed are retained after interruption, not rolled back.
Linux graphical autostart invokes login with session environment and systemd user
services; macOS uses LaunchAgents. No linger or boot services are installed.
An SSH-only initial session is unsupported. setup checks the graphical session.

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
incompatible version: report it; no guessed migration. Native lists change during explicit setup or administrator native maintenance,
never during login updates. `make native BOFLOW_UPGRADE=1` explicitly upgrades them.

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
and preserves ALL files. Administrator separately revokes this deploy key in
GitHub. Repeat for each enrolled account when retiring a machine. Revocation stops
future fetches, not local services or previously downloaded data. Offline machines
cannot be remotely cleaned. Delete personal data only with explicit authorization
and after offering backup; do not turn removal into blanket home-directory cleanup.

To re-enroll in a different household, archive the retained state and bootstrap
with a new BOFLOW_STATE path, then register fresh. Do not silently repurpose an
existing deployment checkout/key. Local port selections must remain nonconflicting.

## 12. Validate a release

Run `uv sync --locked`, `make check`, and Ansible syntax-check.
`make check` never installs OS packages, startup jobs, or account services.
Unit tests use temporary state; application smoke tests use temporary data and
stop their processes. Native setup tests require disposable accounts/VMs; Docker
can isolate applications but cannot validate macOS/Ubuntu graphical login services. CI runs Linux/macOS
orchestration tests, not actual login enrollment. Then execute tests/acceptance.md
on target machines with disposable accounts. Record actual OS/CPU versions and
results. No production-ready or waterproof claim without those checks.

`make acceptance BOFLOW_PORT_BASE=11880` runs the real Ubuntu service roundtrip
with disposable local Git repositories, pinned runtimes, and application checks.
It refuses existing service files/loaded units, validates ports, invokes low-level
registration/removal, verifies retained data, and deletes only its own test state.
Requires a working systemd user manager. It does not test macOS native sessions,
actual logout/reboot, simultaneous accounts, GitHub authorization, or native package
consent. Report these boundaries rather than marking unexercised checklist items done.
This target installs native account service files temporarily; run explicitly in
an otherwise unused disposable account. It is never part of make check or CI.
