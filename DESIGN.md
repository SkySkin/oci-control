---
name: 云境 OCI Control
description: A restrained regional routing atlas for cloud operations.
colors:
  primary: "#a2dbee"
  secondary: "#88d7c1"
  canvas: "#0c1420"
  navigation: "#0a121c"
  surface: "#111d2b"
  raised-surface: "#162536"
  divider: "#28394c"
  foreground: "#e8f0f7"
  secondary-text: "#9bacbf"
  warning: "#eac18b"
  danger: "#f0a3a9"
typography:
  headline:
    fontFamily: "Manrope Variable, PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif"
    fontSize: "28px"
    fontWeight: 640
    lineHeight: 1.4
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Manrope Variable, PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.5
  body:
    fontFamily: "Manrope Variable, PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.75
rounded:
  control: "7px"
  panel: "12px"
  dialog: "15px"
spacing:
  compact: "8px"
  group: "16px"
  panel: "24px"
  page: "36px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#102330"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "44px"
  button-secondary:
    backgroundColor: "#132131"
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.panel}"
---

## Overview

**Creative North Star: "Regional routing atlas"**

A calm, Chinese-language operational surface. Restrained navy planes, precise connector lines and aligned resource rows make regional inventory understandable. Expression belongs to the region diagram and the quiet cyan/teal accents. Runtime resource data supplies the content.

**Key Characteristics:**
- Dark slate planes with meaningful borders and no ambient glow.
- Clear selected context, consistent icon strokes and tabular numerals.
- Explicit timestamps and visibly distinct offline, demo and unavailable states.

## Colors

Primary ice blue identifies navigation, focus and confirmation controls. Teal indicates successful or healthy state. Amber identifies uncertainty and incomplete information; red identifies failed or risky actions. Status always includes words as well as color.

**The Data State Rule.** Styling must distinguish actual zero, unavailable values, sampled monitoring and Oracle raw measurement. Never turn unknown values into reassuring empty charts or totals.

## Typography

Manrope Variable is bundled locally for Latin lettering and measured numerals. Chinese uses the platform's readable CJK sans family. Headings are medium-weight and compact; numbers use tabular spacing. Long names wrap in details and shorten only in resource rows where the complete name remains available through selection.

Body copy and forms are larger than ancillary timestamps and chart ticks. Mobile password inputs are 16px to preserve browser usability. Metadata is intentionally compact in this first console version; do not reduce it further.

## Layout

Desktop uses a 212px navigation rail and a fluid content plane, capped at 1650px. Section spacing is generally 24px, with 36px page gutters. The primary inventory and secondary context have different proportions. Mobile at 760px replaces the rail with five bottom destinations, includes safe-area insets, and uses 18px gutters. Overview summary precedes resource rows on mobile.

**The Context Rule.** Region selection filters resources without inventing geographic coordinates. The topology is an inventory relationship diagram, not a map or live network visualization.

## Elevation & Depth

Main surfaces use one subtle border and a slightly raised background. Shadows are reserved for protected-focus dialogs and temporary notifications. No decorative blur, neon bloom or repeating grid wallpaper.

## Shapes

Panels use moderately rounded corners, with smaller radii for controls. Icon containers are compact squares; status indicators are small dots accompanied by words. Lucide icons use a consistent thin outline weight. The product mark is an authored geometric SVG.

## Components

Buttons expose focus, loading and disabled states. Primary controls use dark text on pale blue; destructive confirmation uses a separate red surface. Native HTML dialogs provide protected focus for two-phase operations and explicit local data removal.

Resource rows are semantic buttons with complete accessible names. Charts provide daily tables and break the line at missing days. NLB listener and backend topology uses server-returned names, protocols and health; unknown health remains unknown.

Offline banners always state the snapshot time and disabled operation state. Login retains an explicit entry into saved snapshots. Server onboarding requires a fresh HTTP opt-in when the address changes.

## Do's and Don'ts

- **Do** preserve stable alignment, Chinese control labels and keyboard focus.
- **Do** keep actual units and independent observation timestamps visible.
- **Do** respect reduced motion and native safe areas.
- **Don't** add fake telemetry, decorative mini-charts or geographic locations.
- **Don't** imply monitoring is billable traffic, or forecasts enforce hard caps.
- **Don't** remove the offline and demo provenance banners.
