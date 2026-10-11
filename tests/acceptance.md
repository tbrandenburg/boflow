# Native acceptance checklist

Record OS version, CPU, desktop/session type, product commit, and household commit.
Run in disposable accounts before deploying to household accounts.

- [ ] Create private household repo; verify visibility; rerun without overwrites.
- [ ] Attempt initialization against public repo; verify push is refused.
- [ ] Bootstrap Intel Mac, Apple Silicon Mac, and Ubuntu; document human prompts.
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
