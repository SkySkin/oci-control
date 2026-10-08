package com.ocicontrol.app;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONObject;

@CapacitorPlugin(name = "SecureSession")
public class SecureSessionPlugin extends Plugin {
    private SessionStore store;

    @Override public void load() { store = new SessionStore(getContext()); }

    private String entry(PluginCall call) {
        String key = call.getString("key");
        if (key == null || !key.startsWith("oci-control.session.") || key.length() > 8192) {
            call.reject("无效的会话存储键", "INVALID_KEY");
            return null;
        }
        return key;
    }

    @PluginMethod public void set(PluginCall call) {
        String key = entry(call);
        if (key == null) return;
        String value = call.getString("value");
        if (value == null || value.isEmpty() || value.length() > 16384) {
            call.reject("无效的会话凭证", "INVALID_VALUE");
            return;
        }
        try {
            store.set(key, value);
            call.resolve();
        } catch (Exception ignored) {
            call.reject("无法安全保存会话，请重新登录", "SECURE_STORAGE_ERROR");
        }
    }

    @PluginMethod public void get(PluginCall call) {
        String key = entry(call);
        if (key == null) return;
        try {
            String value = store.get(key);
            JSObject result = new JSObject();
            result.put("value", value == null ? JSONObject.NULL : value);
            call.resolve(result);
        } catch (Exception ignored) {
            call.reject("安全会话已不可用，请重新登录", "SECURE_STORAGE_ERROR");
        }
    }

    @PluginMethod public void remove(PluginCall call) {
        String key = entry(call);
        if (key == null) return;
        try {
            store.remove(key);
            call.resolve();
        } catch (Exception ignored) {
            call.reject("无法移除安全会话，请重试", "SECURE_STORAGE_ERROR");
        }
    }
}
