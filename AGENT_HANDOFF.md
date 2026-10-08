# OCI Control handoff

## 0.2.0 interface and interaction release — 2026-10-08

- Fluxdo/Material 3 inspired shared Web/Android interface; user confirmed system/light/dark themes. Dedicated resource pages, preserved source route/filter/scroll/focus, persistent detail AppBar and adaptive desktop/mobile navigation.
- All cloud actions retain preview/explicit confirmation, dangerous-name entry and backend authorization. Fixed cross-server async races, offline state races, malformed caches and refresh feedback. Independent review's F1 nullable NLB data, F2 resume refresh latch and F3 dismissed-overlay forward history were fixed and regressed.
- Validation: 78 backend + 4 script tests, 41 Web tests, 7 mobile config tests, 7 Java unit tests; root reran 11 independent regression cases and 6 browser journeys. Nonzero scroll restored 2803→2803 with focus/filter preserved; all six actions keep two-stage confirmation. Tests use synthetic cloud only.
- Root mobile/desktop light/dark screenshots and browser cold-offline/theme/logout journeys passed without JS errors or unintended execute requests. New assets index-CSzCXrRj.js/index-BIMUsZvL.css published; previous immutable assets remain for open old tabs. Public screenshots are synthetic.
- Native App 7.1.2 back/resume and NativeChrome theme/inset bridge; sensitive logs/debugging stay disabled. CI now builds Android and runs API35 emulator Keystore/inset/real-IME tests; execution pending. No physical-device validation claimed.
- Capacitor sync completed: all six final Web files match Android copies; App plugin is registered and generated Gradle dependencies are tracked. Public HTTPS health reports 0.2.0 and references final asset hashes.
- Next action: push source to CI, verify emulator/build results, locally sign with existing key and publish v0.2.0 APK; record final receipt separately. Runtime/signing material remains outside checkout.

## 0.1.0 implementation — 2026-10-08

- Python/FastAPI service, Chinese React web, Capacitor Android app, Docker/native installers and Chinese deployment docs are complete. OCI adapters scan authorized regions/compartments, retrieve cost/monitoring/official outbound usage, and support six confirmed operations.
- API keys remain server-side; browser HttpOnly cookie, native Keystore token, persisted/revocable sessions, account-scoped timestamped offline snapshots. Android bridge logs and WebView debugging disabled. Confirmation is bound to session/current resource ETag; audit intent and execution claim are atomic, interrupted outcomes remain visible as unknown.
- Official `GB Months` usage remains in its original unit when byte conversion is not verified; no assumption about account-specific free allowance. Empty/partial results are explicit. No live cloud mutations were used for verification.
- Verification: 82 Python tests, 20 frontend tests, 4 mobile configuration tests and 3 crypto unit tests passed. Desktop/mobile browser inspection and cold offline reload passed; dependency/public-source audits passed. Real authorized read-only collection and action preview succeeded without publishing account identifiers or snapshots.
- Four independent-review findings were corrected: Android debug logging, stale cross-server login completion, cross-account settings fallback, and interrupted-operation audit durability. Regression tests are included.
- Released `v0.1.0` from `93b76ab4653330744d9437cc8550224d4930f409`. CI run `37811019095` passed checks, Android debug/release builds with alignment verification, crypto tests and Docker build/demo authentication smoke. Android setup explicitly installs `platform-tools` rather than the retired upstream `tools` default.
- Signed release APK is published on GitHub Releases, 3,136,145 bytes; v1/v2/v3 signatures and 7 bundled web assets verified. Public download SHA-256: `4be2d94ef397c53d2318f5b25f56ad395826a9093b9aa261417b7fd5f07531ef`. Signing key never left the deployment host. Metadata: `docs/releases/0.1.0.json`.
- Deployed service passed HTTPS anonymous/authenticated boundaries, actual resource preview without execution, persistent session across restart and official-usage rendering. Temporary verification session was revoked. No remaining build blocker; Android physical-device installation/Keystore/network behavior remains untested.
- Next action: install the signed Android release on a physical device and validate first connection, background return and airplane-mode snapshot access. Keep signing material and deployment receipts outside the repository.
