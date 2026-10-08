package com.ocicontrol.app;

import android.app.Activity;
import android.graphics.Color;
import android.os.Build;
import android.view.View;
import android.view.Window;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

/** Owns all native insets. The bundled Android web UI uses zero CSS safe-area padding. */
final class NativeChrome {
    private final Window window;
    private final View content;
    private final View webView;

    NativeChrome(Activity activity, View webView) {
        this.window = activity.getWindow();
        this.content = activity.findViewById(android.R.id.content);
        this.webView = webView;

        WindowCompat.setDecorFitsSystemWindows(window, false);
        ViewCompat.setOnApplyWindowInsetsListener(content, (view, insets) -> {
            // IME and the navigation bar overlap: take their union, never add heights.
            // Consuming here also prevents WebView/CSS from applying the same inset again.
            Insets safe = insets.getInsets(WindowInsetsCompat.Type.systemBars()
                    | WindowInsetsCompat.Type.displayCutout() | WindowInsetsCompat.Type.ime());
            view.setPadding(safe.left, safe.top, safe.right, safe.bottom);
            return WindowInsetsCompat.CONSUMED;
        });

        int initialColor = activity.getColor(R.color.chrome_background);
        boolean initialLight = activity.getResources().getBoolean(R.bool.chrome_light);
        applyTheme(ChromeTheme.parse(initialLight ? "light" : "dark",
                String.format(java.util.Locale.ROOT, "#%06X", initialColor & 0xffffff)));
        ViewCompat.requestApplyInsets(content);
    }

    @SuppressWarnings("deprecation")
    void applyTheme(ChromeTheme theme) {
        // The native area behind transparent bars is painted with the exact resolved web color.
        content.setBackgroundColor(theme.background);
        webView.setBackgroundColor(theme.background);
        window.setStatusBarColor(Color.TRANSPARENT);
        // Android 6/7 cannot draw dark navigation icons; preserve their contrast.
        window.setNavigationBarColor(Build.VERSION.SDK_INT < Build.VERSION_CODES.O
                ? Color.BLACK : Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            window.setNavigationBarDividerColor(Color.TRANSPARENT);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.setStatusBarContrastEnforced(false);
            window.setNavigationBarContrastEnforced(false);
        }
        WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(window, content);
        bars.setAppearanceLightStatusBars(theme.light);
        bars.setAppearanceLightNavigationBars(theme.light);
    }
}
