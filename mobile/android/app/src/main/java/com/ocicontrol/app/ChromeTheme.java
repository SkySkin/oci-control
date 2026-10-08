package com.ocicontrol.app;

/** Validated, resolved web appearance. Never changes Android's system night mode. */
final class ChromeTheme {
    final boolean light;
    final int background;

    private ChromeTheme(boolean light, int background) {
        this.light = light;
        this.background = background;
    }

    static ChromeTheme parse(String theme, String backgroundColor) {
        if (!("light".equals(theme) || "dark".equals(theme))
                || backgroundColor == null || !backgroundColor.matches("#[0-9a-fA-F]{6}")) {
            throw new IllegalArgumentException("无效的系统外观");
        }
        return new ChromeTheme("light".equals(theme),
                0xff000000 | Integer.parseInt(backgroundColor.substring(1), 16));
    }
}
