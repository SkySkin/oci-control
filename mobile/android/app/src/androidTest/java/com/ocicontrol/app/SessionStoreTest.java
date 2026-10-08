package com.ocicontrol.app;

import static org.junit.Assert.*;
import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class SessionStoreTest {
    @Test public void keystorePersistsAcrossStoreInstancesAndRemovalIsScoped() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        String a = "oci-control.session.synthetic-a";
        String b = "oci-control.session.synthetic-b";
        SessionStore first = new SessionStore(context);
        try {
            first.set(a, "synthetic-bearer-a");
            first.set(b, "synthetic-bearer-b");
            String ciphertext = context.getSharedPreferences("secure_session_v1", Context.MODE_PRIVATE).getString(a, "");
            assertFalse(ciphertext.contains("synthetic-bearer-a"));
            SessionStore restarted = new SessionStore(context);
            assertEquals("synthetic-bearer-a", restarted.get(a));
            restarted.remove(a);
            assertNull(first.get(a));
            assertEquals("synthetic-bearer-b", first.get(b));
        } finally {
            first.remove(a);
            first.remove(b);
        }
    }
}
