package com.ocicontrol.app;

import static org.junit.Assert.*;
import static androidx.test.espresso.Espresso.onView;
import static androidx.test.espresso.Espresso.pressBack;
import static androidx.test.espresso.action.ViewActions.click;
import static androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom;
import android.graphics.drawable.ColorDrawable;
import android.os.Build;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Synthetic window fixtures; no server connection, login, or cloud operation is required. */
@RunWith(AndroidJUnit4.class)
public class NativeChromeTest {
    @Test public void actualKeyboardShrinksWebViewAndBackRestoresIt() throws Exception {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            CountDownLatch loaded = new CountDownLatch(1);
            scenario.onActivity(activity -> {
                WebView web = activity.getBridge().getWebView();
                web.setWebViewClient(new WebViewClient() {
                    @Override public void onPageFinished(WebView view, String url) {
                        if ("https://localhost/native-ime-fixture".equals(url)) loaded.countDown();
                    }
                });
                // Local-only document: no scripts, URLs, server preference or authentication.
                web.loadDataWithBaseURL("https://localhost/native-ime-fixture",
                        "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                        + "</head><body style='margin:0'><input aria-label='合成键盘测试' "
                        + "style='position:fixed;inset:0;width:100%;height:100%;box-sizing:border-box'>"
                        + "</body></html>", "text/html", "UTF-8", "https://localhost/native-ime-fixture");
            });
            assertTrue("Synthetic input must load", loaded.await(10, TimeUnit.SECONDS));
            await(scenario, activity -> activity.getBridge().getWebView().getHeight() > 0);
            AtomicInteger fullHeight = new AtomicInteger();
            scenario.onActivity(activity -> fullHeight.set(activity.getBridge().getWebView().getHeight()));
            onView(isAssignableFrom(WebView.class)).perform(click());
            await(scenario, activity -> imeVisible(activity)
                    && activity.getBridge().getWebView().getHeight() < fullHeight.get());
            scenario.onActivity(activity -> {
                View content = activity.findViewById(android.R.id.content);
                WindowInsetsCompat insets = ViewCompat.getRootWindowInsets(content);
                assertNotNull(insets);
                int keyboardBottom = insets.getInsets(WindowInsetsCompat.Type.ime()).bottom;
                assertTrue(keyboardBottom > 0);
                assertEquals(keyboardBottom, content.getPaddingBottom());
            });
            pressBack(); // Android consumes the first Back to dismiss the IME.
            await(scenario, activity -> !imeVisible(activity)
                    && activity.getBridge().getWebView().getHeight() == fullHeight.get());
        }
    }

    @Test public void imeReplacesNavigationInsetAndHidingRestoresIt() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                View root = activity.findViewById(android.R.id.content);
                WindowInsetsCompat keyboard = fixture(Insets.of(0, 24, 0, 32), Insets.NONE, 300);
                assertTrue(ViewCompat.dispatchApplyWindowInsets(root, keyboard).isConsumed());
                assertEquals(24, root.getPaddingTop());
                assertEquals(300, root.getPaddingBottom());
                ViewCompat.dispatchApplyWindowInsets(root, keyboard);
                assertEquals(300, root.getPaddingBottom()); // repeated dispatch must not accumulate
                ViewCompat.dispatchApplyWindowInsets(root, fixture(Insets.of(0, 24, 0, 32), Insets.NONE, 0));
                assertEquals(32, root.getPaddingBottom());
                assertEquals(24, root.getPaddingTop());
                ViewGroup.MarginLayoutParams web = (ViewGroup.MarginLayoutParams)
                        activity.getBridge().getWebView().getLayoutParams();
                assertEquals(0, web.topMargin);
                assertEquals(0, web.bottomMargin);
            });
        }
    }

    @Test public void rotationCutoutsAndGestureNavigationRemainSingleInsets() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                View root = activity.findViewById(android.R.id.content);
                ViewCompat.dispatchApplyWindowInsets(root,
                        fixture(Insets.of(0, 24, 0, 16), Insets.of(44, 0, 0, 0), 0));
                assertEquals(44, root.getPaddingLeft());
                assertEquals(16, root.getPaddingBottom());
                ViewCompat.dispatchApplyWindowInsets(root,
                        fixture(Insets.of(0, 24, 0, 16), Insets.of(0, 0, 44, 0), 0));
                assertEquals(0, root.getPaddingLeft());
                assertEquals(44, root.getPaddingRight());
            });
        }
    }

    @Test public void resolvedThemeUpdatesChromeAndPluginsRemainAvailable() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                assertNotNull(activity.getBridge().getPlugin("App"));
                assertNotNull(activity.getBridge().getPlugin("NativeChrome"));
                assertNotNull(activity.getBridge().getPlugin("SecureSession"));
                View root = activity.findViewById(android.R.id.content);
                for (String theme : new String[] { "light", "dark", "light" }) {
                    boolean light = theme.equals("light");
                    int color = light ? 0xfff7f9fc : 0xff101418;
                    activity.applyChromeTheme(ChromeTheme.parse(theme, light ? "#F7F9FC" : "#101418"));
                    assertEquals(color, ((ColorDrawable) root.getBackground()).getColor());
                    assertEquals(light, WindowCompat.getInsetsController(activity.getWindow(), root)
                            .isAppearanceLightStatusBars());
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        assertEquals(light, WindowCompat.getInsetsController(activity.getWindow(), root)
                                .isAppearanceLightNavigationBars());
                    }
                }
            });
        }
    }

    private WindowInsetsCompat fixture(Insets bars, Insets cutout, int imeHeight) {
        return new WindowInsetsCompat.Builder()
                .setInsets(WindowInsetsCompat.Type.systemBars(), bars)
                .setInsets(WindowInsetsCompat.Type.displayCutout(), cutout)
                .setInsets(WindowInsetsCompat.Type.ime(), Insets.of(0, 0, 0, imeHeight))
                .setVisible(WindowInsetsCompat.Type.ime(), imeHeight > 0)
                .build();
    }

    private boolean imeVisible(MainActivity activity) {
        WindowInsetsCompat insets = ViewCompat.getRootWindowInsets(activity.findViewById(android.R.id.content));
        return insets != null && insets.isVisible(WindowInsetsCompat.Type.ime());
    }

    private void await(ActivityScenario<MainActivity> scenario, Predicate<MainActivity> condition)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        AtomicBoolean satisfied = new AtomicBoolean();
        do {
            scenario.onActivity(activity -> satisfied.set(condition.test(activity)));
            if (satisfied.get()) return;
            Thread.sleep(50);
        } while (System.nanoTime() < deadline);
        fail("Timed out waiting for native keyboard/layout state");
    }
}
