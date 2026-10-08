# Console surface brief

## Scope and mode

web/; Operate. Shared React Chinese OCI console for desktop browsers, phone browsers and bundled Android. The user explicitly selected Fluxdo's native Material 3 visual direction, with default system theme and manual light/dark selection. This replaces the former dark atlas identity; no additional design approval or schema migration is needed.

## Reference and translation

Read-only reference: Fluxdo `theme_provider.dart`, `adaptive_navigation.dart` and `screenshots/preview.png` in the provided research checkout. Transfer the Material 3 tonal surfaces, rounded row groups, built-in system fonts, AppBar hierarchy, selected navigation capsules and adaptive rail/bottom navigation. Keep OCI Control's own Chinese content, brand mark, data semantics and confirmed operations. No Flutter rewrite and no copied code or assets.

## First viewport and hierarchy

Unified title/back/refresh AppBar with connection state, compact region selection, then cost/runtime summary before resource rows on phones. Wide screens retain resource-first columns with secondary context beside them. The detail AppBar stays visible while scrolling. Wide screens use the rail and responsive multi-column content; phones use five bottom destinations and readable stacked groups. Details replace the resource listing and show full facts and supported actions.

## Navigation and state contract

Detail routes include the resource identity, with a validated in-app source entry. Return restores the source list filters, scroll and focus, or returns to overview when entered there. Missing/deep-linked resources offer a safe list return. Browser history and Android back close modal layers first; Android minimizes only at the app root. Resume and reconnect never replay mutations.

Protected dialogs cover cloud confirmations, logout and local snapshot removal. Busy cloud requests block dismissal; normal cancel, close, completion and browser back consume their history layer. Loading, errors, retry, no-data, malformed snapshots, expired sessions and offline timestamps remain explicit.

## Verification ownership

Frontend owns synthetic navigation, confirmation, cache, theme, native-lifecycle and cross-server regression tests, production build to `/tmp/oci-control-v020-web-dist`, dependency audit and design documentation. Root owns the single combined screenshot round (390×844 and 1440×1000, light/dark), keyboard checks, independent review, integration and publication. No live OCI mutation is permitted for tests. The live `web/dist` is untouched until root authorizes integration.
