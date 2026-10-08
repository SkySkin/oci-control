package com.ocicontrol.app;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;

public class MainActivity extends BridgeActivity {
    private NativeChrome chrome;

    @Override public void onCreate(Bundle savedInstanceState) {
        registerPlugin(SecureSessionPlugin.class);
        registerPlugin(NativeChromePlugin.class);
        super.onCreate(savedInstanceState);
        if (getBridge() != null) {
            chrome = new NativeChrome(this, getBridge().getWebView());
        }
    }

    void applyChromeTheme(ChromeTheme theme) {
        if (chrome != null) chrome.applyTheme(theme);
    }
}
