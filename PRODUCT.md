# OCI Control / 云境

## Product
Independent open-source OCI operations console. Chinese-speaking cloud account owners inspect regional resources, monitoring estimates, billing data and audit history, and execute explicitly supported operations after a server-validated preview.

## Audience and usage
An account operator checks a desktop dashboard during normal work, and uses the bundled Android app to inspect or respond while away. The first view must answer where resources are, which data is current, and what needs attention. Assume a single operator per configured server until an account model is explicitly introduced.

## Required behavior
- Chinese interface; React TypeScript Vite, Android bundled through Capacitor 7.
- Real API contract in docs/IMPLEMENTATION_CONTRACT.md. Demo content comes only from an explicitly configured demo server.
- Browser cookie session with CSRF; Android bearer credential only in native Keystore through SecureSession.
- Region and resource exploration, details, supported instance/NLB actions, traffic/cost, activity and setup.
- Snapshot cache scoped to server identity. Offline view explicitly chosen after logout; timestamps and unavailable metrics remain visible. Logout retains snapshots; separate removal deletes local data.
- Never imply monitoring estimates are exact billable traffic or budget hard caps. Cloud credentials remain on the server.

## Design constraints
Restrained sci-fi operational UI, charcoal/navy slate with ice blue and teal. Clear Chinese typography, precise resource diagrams, accessible contrast, keyboard use and mobile safe areas. No neon clutter. Honest empty, stale, partial-error and reconnect states are first-class.

## Working assumptions
The explicit implementation brief supplies the product context and authorizes proceeding without an additional interview or agent delegation. No marketing claims, fake telemetry, account identifiers or public IP fixtures belong in shipped UI.
