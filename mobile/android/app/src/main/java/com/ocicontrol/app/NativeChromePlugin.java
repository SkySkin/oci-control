package com.ocicontrol.app;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "NativeChrome")
public class NativeChromePlugin extends Plugin {
    @PluginMethod public void setTheme(PluginCall call) {
        final ChromeTheme theme;
        try {
            theme = ChromeTheme.parse(call.getString("theme"), call.getString("backgroundColor"));
        } catch (IllegalArgumentException ignored) {
            call.reject("无效的系统外观", "INVALID_THEME");
            return;
        }
        getActivity().runOnUiThread(() -> {
            ((MainActivity) getActivity()).applyChromeTheme(theme);
            call.resolve();
        });
    }
}
