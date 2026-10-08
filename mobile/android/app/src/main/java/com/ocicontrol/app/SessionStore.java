package com.ocicontrol.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/** Ciphertext stays in private storage; non-exportable encryption key stays in Android Keystore. */
final class SessionStore {
    private static final String ALIAS = "com.ocicontrol.app.secure-session.v1";
    private final SharedPreferences preferences;

    SessionStore(Context context) {
        preferences = context.getSharedPreferences("secure_session_v1", Context.MODE_PRIVATE);
    }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .setKeySize(256)
            .build());
        return generator.generateKey();
    }

    synchronized void set(String entry, String value) throws Exception {
        byte[] envelope = SessionCipher.encrypt(key(), entry, value);
        if (!preferences.edit().putString(entry, Base64.encodeToString(envelope, Base64.NO_WRAP)).commit()) {
            throw new GeneralSecurityException("Storage failed");
        }
    }

    synchronized String get(String entry) throws Exception {
        String encoded = preferences.getString(entry, null);
        if (encoded == null) return null;
        try {
            return SessionCipher.decrypt(key(), entry, Base64.decode(encoded, Base64.NO_WRAP));
        } catch (Exception error) {
            // Key loss or corruption must require a fresh login, never return ciphertext as a token.
            preferences.edit().remove(entry).commit();
            throw new GeneralSecurityException("Session unavailable");
        }
    }

    synchronized void remove(String entry) throws Exception {
        if (!preferences.edit().remove(entry).commit()) throw new GeneralSecurityException("Storage failed");
    }
}
