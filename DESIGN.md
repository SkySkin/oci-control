---
name: 云境 OCI Control
description: A Chinese cloud operations app with Fluxdo-inspired Material 3 tonal surfaces.
colors:
  primary: "#246580"
  primary-container: "#d4eaf6"
  canvas: "#f7f9fc"
  navigation: "#edf1f5"
  surface: "#ffffff"
  raised-surface: "#eaf0f5"
  divider: "#c4cdd5"
  foreground: "#18232c"
  secondary-text: "#52616d"
  success: "#216653"
  warning: "#78551c"
  danger: "#a02c3b"
  dark-primary: "#9ecfe6"
  dark-primary-container: "#244b5f"
  dark-canvas: "#101418"
  dark-navigation: "#191f24"
  dark-surface: "#1b2228"
  dark-raised-surface: "#252e36"
  dark-divider: "#53616c"
  dark-foreground: "#e2e8ee"
  dark-secondary-text: "#acbac5"
  dark-success: "#99d5bd"
  dark-warning: "#ebc17d"
  dark-danger: "#ffb2bb"
typography:
  headline:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Noto Sans, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "-0.02em"
  title:
    fontFamily: "system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 650
    lineHeight: 1.5
  body:
    fontFamily: "system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  supporting:
    fontFamily: "system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.75
rounded:
  field: "16px"
  row-edge: "16px"
  panel: "24px"
  compact-panel: "20px"
  dialog: "28px"
  control: "24px"
spacing:
  compact: "8px"
  group: "16px"
  panel: "24px"
  page: "36px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    padding: "11px 20px"
    height: "48px"
  button-secondary:
    backgroundColor: "{colors.primary-container}"
    textColor: "{colors.primary}"
    rounded: "{rounded.control}"
    padding: "11px 20px"
    height: "48px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.panel}"
---

## Overview

The user selected Fluxdo's native Material 3 direction. OCI Control applies its tonal hierarchy, grouped rows, readable system typography, clear AppBar and selected navigation capsules to the existing React interface. All browser and Android pages share this system. The reference was inspected read-only; no Flutter implementation, code or visual asset is copied.

The product remains an operational tool. Muted ocean accents carry selection, focus and primary actions; resource names, timestamps and operational state carry the screen. The existing geometric cloud mark remains the product identity.

## Colors

Theme defaults to the device preference. Settings offers **跟随系统 / 浅色 / 深色**, stored as a nonsecret local preference. Both themes use semantic CSS variables; the browser chrome and Android NativeChrome receive the resolved page background.

Canvas, navigation, panel and raised control surfaces form a restrained tonal stack. Selection uses the primary container, and status uses distinct success, warning and danger containers. Status always includes readable words.

**The Data State Rule.** An unavailable metric stays unavailable. Theme, charts and labels must distinguish actual zero, estimated monitoring and official raw measurement without implying a quota guarantee.

## Typography

Use built-in system fonts; no display-font download. Body and task instructions are 15–16px, page titles are 28px on desktop and 24px on mobile, and supporting metadata is 13px. Navigation labels are compact enough for five mobile destinations. Form controls use 16px to preserve mobile browser usability. Numeric data uses tabular figures.

Long resource names truncate in the resource list and wrap in the independent detail page. Prose stays within 75 characters where space permits. Do not reduce task text to fit small screens; rearrange the layout.

## Layout

The desktop shell uses a 232px navigation rail, a unified AppBar and fluid content capped at 1540px. A narrower desktop rail is 204px. The inventory is primary, with cost and runtime context beside it on wide screens. Settings uses a smaller readable maximum width.

At 760px the rail becomes an 80px bottom navigation bar. A selected icon sits in a tonal capsule above its label. The page title, back action and refresh control share one AppBar, which stays visible while scrolling a detail page. Phone region choices form a compact horizontal strip, and cost/runtime summaries precede resource rows. Mobile resource rows keep the name, type, state and disclosure; the independent detail page contains the full specification.

Resource details are a dedicated history route. Opening from overview returns to overview; opening from the filtered resource list restores its filter, scroll and focused row. Desktop details use the same navigation model, with facts and actions organized in two columns when space permits.

Browser safe-area insets are applied once. In Android the native container consumes system bars, cutout and IME; CSS safe-area values are zero. Dialog height follows the visible viewport and its content scrolls above the keyboard.

## Elevation & Depth

Tonal surfaces group the interface without a shadow on every container. Thin separators clarify rows and fields. Dialogs and temporary feedback are the only floating surfaces with shadows. There is no glow, glass wallpaper or decorative telemetry.

## Shapes

Rounded groups define the native feel: 24px panels, 20px compact groups, 16px fields and row edges, and 28px dialogs. Closely related resource rows have small internal joins and rounded outer edges. Buttons are 48px tall capsules; icon buttons have a 48px circular target.

Lucide line icons share a consistent stroke. The restrained brand mark is the only authored iconography. Small status chips remain visually subordinate to resource names and task controls.

## Components

**The Confirmation Rule.** Every cloud mutation requires server prepare, readable effect review and an explicit execute action. Dangerous operations require the exact resource name. Expired or offline confirmations cannot execute; retries retain their idempotency key. Closing or navigating never submits an operation.

Modal browser/Android back closes the top layer before leaving a resource. Busy prepare/execute cannot be dismissed. Dialogs trap focus through native HTML dialog behavior, lock document scrolling, and restore focus on closing. The detail page uses a short visible slide transition, disabled by reduced-motion preferences.

Refresh shows start, collection, completion and failure feedback, with an explicit retry path. Session expiry and malformed snapshots expose recovery; stale cross-server responses and responses from before an offline event cannot restore action availability. Resume only revalidates read-only state.

Settings confirms logout before revocation and states that offline snapshots are retained. Removing local snapshots has its own confirmation. Offline snapshots always show their timestamp and read-only state.

## Do's and Don'ts

- Use the same theme, component vocabulary and independent detail navigation in browser and Android.
- Keep readable task text, 48px targets, native-safe insets and reduced-motion behavior.
- Preserve explicit demo, offline, partial-error and unknown-result states.
- Do not reproduce Fluxdo content, assets or Flutter code.
- Do not imply snapshots are live, monitoring is exact billable traffic, or cost forecasts are hard spending caps.
