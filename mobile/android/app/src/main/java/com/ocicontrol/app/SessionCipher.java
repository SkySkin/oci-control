package com.ocicontrol.app;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Versioned AES-GCM envelope; the storage key is authenticated to prevent entry swapping. */
final class SessionCipher {
    private static final int IV_LENGTH = 12;
    private static final int TAG_BITS = 128;

    static byte[] encrypt(SecretKey key, String entry, String value) throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        cipher.updateAAD(entry.getBytes(StandardCharsets.UTF_8));
        byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        if (iv.length != IV_LENGTH) throw new GeneralSecurityException("Invalid IV");
        byte[] envelope = new byte[1 + IV_LENGTH + encrypted.length];
        envelope[0] = 1;
        System.arraycopy(iv, 0, envelope, 1, IV_LENGTH);
        System.arraycopy(encrypted, 0, envelope, 1 + IV_LENGTH, encrypted.length);
        return envelope;
    }

    static String decrypt(SecretKey key, String entry, byte[] envelope) throws GeneralSecurityException {
        if (envelope.length < 1 + IV_LENGTH + TAG_BITS / 8 || envelope[0] != 1) {
            throw new GeneralSecurityException("Invalid envelope");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, Arrays.copyOfRange(envelope, 1, 1 + IV_LENGTH)));
        cipher.updateAAD(entry.getBytes(StandardCharsets.UTF_8));
        return new String(cipher.doFinal(envelope, 1 + IV_LENGTH,
            envelope.length - 1 - IV_LENGTH), StandardCharsets.UTF_8);
    }
}
