# OCI Control

Independent open-source project. Do not copy credentials, account OCIDs, real resource IPs, private deployment reports, password hashes, session tokens or signing keys into the repository. Runtime data lives outside checkout (`OCI_CONTROL_DATA_DIR`). Never print secrets.

Read AGENT_HANDOFF.md and docs/IMPLEMENTATION_CONTRACT.md before edits. Shared checkout: edit only assigned files, no git commits/pushes by delegated agents. Root integrates and publishes. Use synthetic fixtures for tests; never mutate live cloud resources for tests. Supported operations must be explicitly allowlisted, authorized, confirmed against current resource state, idempotent and audited. Never implement arbitrary CLI/shell execution endpoints.

UI language Chinese. Distinctive restrained sci-fi, accessible responsive operational UI. Offline snapshots must be clearly timestamped, never imply live data. Logout revokes auth but preserves account-scoped snapshots; offer separate local-data removal. Cloud/API credentials never go to browser or Android. Browser auth cookie; Android bearer credential in native Keystore. Never promise budget hard caps or exact real-time billable traffic.

Version SemVer; tests/build/secret audit before public push. Update handoff with evidence and next action. New-project rules do not inherit fund-v2 release procedures.
