package com.ocicontrol.app;

import static org.junit.Assert.*;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import org.junit.Test;

public class SessionCipherTest {
    private SecretKey key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        return generator.generateKey();
    }

    @Test public void roundTripAndFreshNonce() throws Exception {
        SecretKey key = key();
        String entry = "oci-control.session.https%3A%2F%2Fdemo.example";
        byte[] first = SessionCipher.encrypt(key, entry, "synthetic-session-测试");
        byte[] second = SessionCipher.encrypt(key, entry, "synthetic-session-测试");
        assertEquals("synthetic-session-测试", SessionCipher.decrypt(key, entry, first));
        assertFalse(Arrays.equals(first, second));
    }

    @Test public void tamperingWrongOriginAndWrongKeyFailClosed() throws Exception {
        SecretKey key = key();
        byte[] encrypted = SessionCipher.encrypt(key, "server-a", "synthetic-session");
        assertThrows(GeneralSecurityException.class, () -> SessionCipher.decrypt(key, "server-b", encrypted));
        assertThrows(GeneralSecurityException.class, () -> SessionCipher.decrypt(key(), "server-a", encrypted));
        encrypted[encrypted.length - 1] ^= 1;
        assertThrows(GeneralSecurityException.class, () -> SessionCipher.decrypt(key, "server-a", encrypted));
    }

    @Test public void malformedEnvelopeFailsClosed() throws Exception {
        SecretKey key = key();
        assertThrows(GeneralSecurityException.class, () -> SessionCipher.decrypt(key, "server", new byte[0]));
        byte[] encrypted = SessionCipher.encrypt(key, "server", "synthetic-session");
        encrypted[0] = 2;
        assertThrows(GeneralSecurityException.class, () -> SessionCipher.decrypt(key, "server", encrypted));
    }
}
