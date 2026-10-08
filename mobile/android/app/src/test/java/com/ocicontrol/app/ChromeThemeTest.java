package com.ocicontrol.app;

import static org.junit.Assert.*;
import org.junit.Test;

public class ChromeThemeTest {
    @Test public void lightThemePreservesOpaqueWebColor() {
        ChromeTheme theme = ChromeTheme.parse("light", "#F7f9Fc");
        assertTrue(theme.light);
        assertEquals(0xfff7f9fc, theme.background);
    }

    @Test public void darkThemePreservesOpaqueWebColor() {
        ChromeTheme theme = ChromeTheme.parse("dark", "#101418");
        assertFalse(theme.light);
        assertEquals(0xff101418, theme.background);
    }

    @Test public void bridgeRequiresAnExplicitResolvedTheme() {
        for (String theme : new String[] { null, "system", "auto", "LIGHT", "" }) {
            assertThrows(IllegalArgumentException.class, () -> ChromeTheme.parse(theme, "#123456"));
        }
    }

    @Test public void rejectsMissingAlphaAndNonHexColors() {
        for (String color : new String[] { null, "", "#fff", "#00123456", "red", "123456",
                "#gggggg", "#123456\n", "#123456;display:none" }) {
            assertThrows(IllegalArgumentException.class, () -> ChromeTheme.parse("light", color));
        }
    }
}
