# Native acceptance checklist

Record OS version, CPU, desktop/session type, product commit, and household commit.
Run in disposable accounts before deploying to household accounts.

`make acceptance BOFLOW_PORT_BASE=11880` exercises a disposable Ubuntu roundtrip with
real Git fetches, pinned Node/application installs, and systemd user services.
It checks registration, repeated registration/update, stable ports/data/secrets,
managed-only restart, offline login, and low-level account removal, then deletes its test
state. Native package consent, GitHub key authorization, macOS sessions,
simultaneous accounts, and logout/reboot remain separate checklist items below.

- [ ] Create private household repo; verify visibility; rerun without overwrites.
- [ ] Attempt initialization against public repo; verify push is refused.
- [ ] Fresh make setup on Intel Mac, Apple Silicon Mac, Ubuntu without uv; document prompts.
- [ ] Create journey installs gh when missing and sets local Git identity when absent.
- [ ] Join needs no GitHub login; admin make approve verifies request and grants read-only access.
- [ ] Interrupt while awaiting approval; rerun setup reuses the same key/label/repo.
- [ ] Repeat approval reuses key; cross-household/public/write-enabled keys refused.
- [ ] Mac non-owner reuses installed packages; missing packages print owner handoff.
- [ ] Occupy preferred initial port; setup selects another block without touching listener.
- [ ] Enroll deploy key; verify denied access before authorization and success after.
- [ ] Explicit native setup works under correct owner; login never requests sudo.
- [ ] Register account in graphical session; all endpoints pass checks.
- [ ] Personal palette loads all baseline modules; external CLI help is accurate.
- [ ] Add personal module/flow/credentials/notebook; unchanged update preserves all.
- [ ] Change managed flow; only managed service process restarts.
- [ ] Change Node-RED baseline; personal extra module remains installed.
- [ ] Change Jupyter lock; Jupyter restarts and notebook files remain.
- [ ] Concurrent accounts use different ports and own their files/processes.
- [ ] Log out/reboot/login; installed services start and update runs once.
- [ ] Offline login starts installed services; attempt marked failed, success retained.
- [ ] Publish invalid dependencies; preparation fails without stopping services.
- [ ] Publish bad activation config; failure is visible and manual revert recovers.
- [ ] Kill service; native supervisor restarts it without leftover child processes.
- [ ] SSH tunnel works by IP; application ports cannot be reached directly on LAN.
- [ ] Jupyter launcher enters no token manually; token absent from shared page/logs.
- [ ] Retire member; startup removed, data retained; admin revokes correct key.
- [ ] Follow every AGENTS.md journey with an assisting agent and record ambiguities.
