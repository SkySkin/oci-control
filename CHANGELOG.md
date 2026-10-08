# Changelog

## 0.1.0 — 2026-10-08

- First self-hosted release: Chinese web console and Android client using one OCI backend.
- Region/resource inventory, instance metrics, NLB backend health, costs, monitored traffic and original Oracle outbound usage.
- Instance start/stop/reboot/rename and NLB backend drain/enable with preview, current-state checks, confirmation and durable audit.
- Persistent login, explicit logout/revocation, account-isolated local snapshots and offline access. No queued offline mutations.
- Native Keystore session encryption, disabled bridge logging, Docker/native installation and Chinese HTTPS/Cloudflare Tunnel documentation.

Usage data can arrive late. Account-specific free allowance and forecasts remain unavailable until supported by verified data. `GB Months` is displayed in the original Oracle unit when byte conversion is unverified. This release does not expose arbitrary OCI CLI commands or destructive resource deletion. Android hardware/Keystore behavior still warrants testing on supported physical devices.
