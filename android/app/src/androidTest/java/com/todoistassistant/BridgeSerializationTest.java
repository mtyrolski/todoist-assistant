package com.todoistassistant;

import static org.junit.Assert.*;

import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public class BridgeSerializationTest {
  @Test
  public void javascriptConfirmationCanBeCancelledInTheNativeDialog() throws Exception {
    var instrumentation = InstrumentationRegistry.getInstrumentation();
    var automation = instrumentation.getUiAutomation();
    var serviceInfo = automation.getServiceInfo();
    serviceInfo.flags |=
        android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
    serviceInfo.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
    automation.setServiceInfo(serviceInfo);
    java.lang.reflect.Field webField = MainActivity.class.getDeclaredField("web");
    webField.setAccessible(true);
    java.lang.reflect.Field readyField = MainActivity.class.getDeclaredField("ready");
    readyField.setAccessible(true);
    AtomicReference<String> answer = new AtomicReference<>();
    CountDownLatch answered = new CountDownLatch(1);
    try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
      AtomicReference<Boolean> ready = new AtomicReference<>(false);
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(45);
      while (!ready.get() && System.nanoTime() < deadline) {
        scenario.onActivity(
            activity -> {
              try {
                ready.set(readyField.getBoolean(activity));
              } catch (IllegalAccessException failure) {
                throw new AssertionError(failure);
              }
            });
        if (!ready.get()) Thread.sleep(200);
      }
      assertTrue("The app must finish loading before confirmation", ready.get());
      scenario.onActivity(
          activity -> {
            try {
              WebView web = (WebView) webField.get(activity);
              web.evaluateJavascript(
                  "window.confirm('Confirm test action?')",
                  value -> {
                    answer.set(value);
                    answered.countDown();
                  });
            } catch (IllegalAccessException failure) {
              throw new AssertionError(failure);
            }
          });
      boolean visible = false;
      deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
      while (!visible && System.nanoTime() < deadline) {
        for (var window : automation.getWindows()) {
          var root = window.getRoot();
          if (root != null
              && !root.findAccessibilityNodeInfosByText("Confirm test action?").isEmpty())
            visible = true;
        }
        if (!visible && answered.getCount() != 0) Thread.sleep(500);
        else if (!visible) break;
      }
      assertTrue("The confirmation must be visible to the user", visible);
      assertTrue(
          automation.performGlobalAction(
              android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK));
      assertTrue(answered.await(10, TimeUnit.SECONDS));
      assertEquals("false", answer.get());

      CountDownLatch accepted = new CountDownLatch(1);
      scenario.onActivity(
          activity -> {
            try {
              WebView web = (WebView) webField.get(activity);
              web.evaluateJavascript(
                  "window.confirm('Confirm test action?')",
                  value -> {
                    answer.set(value);
                    accepted.countDown();
                  });
            } catch (IllegalAccessException failure) {
              throw new AssertionError(failure);
            }
          });
      android.view.accessibility.AccessibilityNodeInfo confirm = null;
      deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
      while (confirm == null && System.nanoTime() < deadline) {
        for (var window : automation.getWindows()) {
          var root = window.getRoot();
          if (root != null) {
            var buttons = root.findAccessibilityNodeInfosByViewId("android:id/button1");
            if (!buttons.isEmpty()) confirm = buttons.get(0);
          }
        }
        if (confirm == null && accepted.getCount() != 0) Thread.sleep(500);
        else if (confirm == null) break;
      }
      assertNotNull("The confirmation must offer an OK action", confirm);
      assertTrue(
          confirm.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK));
      assertTrue(accepted.await(10, TimeUnit.SECONDS));
      assertEquals("true", answer.get());

      java.lang.reflect.Field confirmationField =
          MainActivity.class.getDeclaredField("confirmation");
      confirmationField.setAccessible(true);
      scenario.onActivity(
          activity -> {
            try {
              ((WebView) webField.get(activity))
                  .evaluateJavascript("window.confirm('Close while open?')", null);
            } catch (IllegalAccessException failure) {
              throw new AssertionError(failure);
            }
          });
      AtomicReference<android.app.AlertDialog> open = new AtomicReference<>();
      deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
      while (open.get() == null && System.nanoTime() < deadline) {
        scenario.onActivity(
            activity -> {
              try {
                android.app.AlertDialog dialog =
                    (android.app.AlertDialog) confirmationField.get(activity);
                if (dialog != null && dialog.isShowing()) open.set(dialog);
              } catch (IllegalAccessException failure) {
                throw new AssertionError(failure);
              }
            });
        if (open.get() == null) Thread.sleep(500);
      }
      assertNotNull("A pending confirmation must be shown before closing", open.get());
      scenario.onActivity(android.app.Activity::finish);
      deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
      while (open.get().isShowing() && System.nanoTime() < deadline) Thread.sleep(200);
      assertFalse("Closing the activity must dismiss its confirmation", open.get().isShowing());
    }
  }

  @Test
  public void androidBackCanCloseTheAppBeforeTheWebBridgeIsReady() throws Exception {
    java.lang.reflect.Field ready = MainActivity.class.getDeclaredField("ready");
    ready.setAccessible(true);
    java.util.concurrent.atomic.AtomicBoolean finishing =
        new java.util.concurrent.atomic.AtomicBoolean();
    try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
      scenario.onActivity(
          activity -> {
            try {
              // Reproduce Back during startup even on a device that loads its assets quickly.
              ready.setBoolean(activity, false);
              activity.getOnBackPressedDispatcher().onBackPressed();
              finishing.set(activity.isFinishing());
            } catch (IllegalAccessException failure) {
              throw new AssertionError(failure);
            }
          });
      assertTrue("Back must close the app when no web page can handle it", finishing.get());
    }
  }

  @Test
  public void stateDispatchPreservesSpecialProjectNamesInWebView() throws Exception {
    char[] padding = new char[2_200_000];
    java.util.Arrays.fill(padding, 'x');
    JSONObject payload =
        new JSONObject()
            .put("counts", new JSONObject().put("__proto__", 17).put("constructor", 2))
            .put("mappings", new JSONObject().put("__proto__", "a \"quoted\" name\n </script>"))
            .put("padding", new String(padding));
    JSONObject status = new JSONObject().put("message", "cached data");
    String quotedModel = JSONObject.quote(payload.toString());
    CountDownLatch ready = new CountDownLatch(1), resultReady = new CountDownLatch(1);
    AtomicReference<WebView> view = new AtomicReference<>();
    AtomicReference<String> result = new AtomicReference<>();
    var instrumentation = InstrumentationRegistry.getInstrumentation();
    try {
      instrumentation.runOnMainSync(
          () -> {
            WebView web = new WebView(instrumentation.getTargetContext());
            view.set(web);
            web.getSettings().setJavaScriptEnabled(true);
            web.setWebViewClient(
                new WebViewClient() {
                  @Override
                  public void onPageFinished(WebView ignored, String url) {
                    ready.countDown();
                  }
                });
            web.loadDataWithBaseURL(
                "https://appassets.androidplatform.net/",
                "<!doctype html><html><script>window.addEventListener('todoist-state',"
                    + "e => window.captured = JSON.stringify(e.detail));</script></html>",
                "text/html",
                "UTF-8",
                null);
          });
      assertTrue(ready.await(10, TimeUnit.SECONDS));
      instrumentation.runOnMainSync(
          () ->
              view.get()
                  .evaluateJavascript(
                      MainActivity.stateEvent(status, quotedModel),
                      ignored ->
                          view.get()
                              .evaluateJavascript(
                                  "(() => { const event=JSON.parse(window.captured), d=event.model;"
                                      + " return JSON.stringify({counts:d.counts,mappings:d.mappings,"
                                      + "length:d.padding.length,message:event.message}); })()",
                                  value -> {
                                    result.set(value);
                                    resultReady.countDown();
                                  })));
      assertTrue(resultReady.await(30, TimeUnit.SECONDS));
      String captured = new JSONArray("[" + result.get() + "]").getString(0);
      JSONObject decoded = new JSONObject(captured);
      assertEquals(17, decoded.getJSONObject("counts").getInt("__proto__"));
      assertEquals(2, decoded.getJSONObject("counts").getInt("constructor"));
      assertEquals(padding.length, decoded.getInt("length"));
      assertEquals("cached data", decoded.getString("message"));
      assertEquals(
          payload.getJSONObject("mappings").getString("__proto__"),
          decoded.getJSONObject("mappings").getString("__proto__"));
    } finally {
      if (view.get() != null) instrumentation.runOnMainSync(() -> view.get().destroy());
    }
  }
}
