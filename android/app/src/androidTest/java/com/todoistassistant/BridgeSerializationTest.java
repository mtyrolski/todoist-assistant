package com.todoistassistant;

import static org.junit.Assert.*;

import android.app.AlertDialog;
import android.content.Context;
import android.content.DialogInterface;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.lifecycle.Lifecycle;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public class BridgeSerializationTest {
  @Test
  public void accountCanSyncAndRecoverFromOfflineRefreshThroughTheWebView() throws Exception {
    Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    new SnapshotStore(context).clear();
    new TokenStore(context).clear();
    AtomicBoolean offline = new AtomicBoolean();
    AtomicInteger requests = new AtomicInteger();
    String secret = "fixture-token-never-in-state";
    java.time.Instant now = java.time.Instant.now();
    ApiTransport transport =
        new ApiTransport() {
          @Override
          public JSONObject get(String path) throws java.io.IOException, org.json.JSONException {
            requests.incrementAndGet();
            if (offline.get()) throw new java.net.UnknownHostException("fixture offline");
            if (path.equals("user"))
              return new JSONObject()
                  .put("id", "fixture-user")
                  .put("joined_at", now.minusSeconds(60).toString());
            JSONArray results = new JSONArray();
            if (path.startsWith("projects?"))
              results.put(
                  new JSONObject().put("id", "fixture-project").put("name", "Fixture project"));
            if (path.startsWith("tasks?"))
              results.put(
                  new JSONObject()
                      .put("id", "fixture-task")
                      .put("project_id", "fixture-project")
                      .put("content", "Fixture active task"));
            if (path.startsWith("activities?"))
              results.put(
                  new JSONObject()
                      .put("id", "fixture-event")
                      .put("object_id", "finished-task")
                      .put("object_type", "item")
                      .put("event_type", "completed")
                      .put("event_date", now.minusSeconds(10).toString())
                      .put("parent_project_id", "fixture-project")
                      .put(
                          "extra_data", new JSONObject().put("content", "Fixture completed task")));
            return new JSONObject().put("results", results).put("next_cursor", JSONObject.NULL);
          }

          @Override
          public void cancel() {}
        };
    var field = MainActivity.class.getDeclaredField("model");
    var stateField = MainActivity.class.getDeclaredField("state");
    var publish = MainActivity.class.getDeclaredMethod("publish", boolean.class);
    field.setAccessible(true);
    stateField.setAccessible(true);
    publish.setAccessible(true);
    AtomicReference<DashboardViewModel> testModel = new AtomicReference<>();
    CountDownLatch testModelReady = new CountDownLatch(1);
    try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
      awaitJavascript(scenario, "!!document.querySelector('input[type=password]')");
      awaitJavascript(scenario, "!document.querySelector('input[type=password]').disabled");
      scenario.onActivity(
          activity -> {
            try {
              // The original model must not publish state after the fixture takes over.
              ((DashboardViewModel) field.get(activity)).state().removeObservers(activity);
              DashboardViewModel injected =
                  new DashboardViewModel(
                      activity.getApplication(),
                      token -> {
                        if (!secret.equals(token))
                          throw new AssertionError("Unexpected fixture credential");
                        return transport;
                      });
              testModel.set(injected);
              field.set(activity, injected);
              injected
                  .state()
                  .observe(
                      activity,
                      state -> {
                        try {
                          stateField.set(activity, state);
                          publish.invoke(activity, false);
                          if (!state.loading) testModelReady.countDown();
                        } catch (ReflectiveOperationException error) {
                          throw new AssertionError(error);
                        }
                      });
            } catch (ReflectiveOperationException error) {
              throw new AssertionError(error);
            }
          });
      // The old WebView can still show an enabled form while the injected model
      // loads; submitting then is ignored by sync() and the test never recovers.
      assertTrue("Fixture model did not initialize", testModelReady.await(30, TimeUnit.SECONDS));
      awaitJavascript(scenario, "!document.querySelector('input[type=password]').disabled");
      evaluateJavascript(
          scenario,
          "window.__capturedStates=[];window.addEventListener('todoist-state',e=>window.__capturedStates.push(e.detail));"
              + "let input=document.querySelector('input[type=password]');"
              + "Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,"
              + JSONObject.quote(secret)
              + ");input.dispatchEvent(new Event('input',{bubbles:true}));");
      awaitJavascript(
          scenario,
          "document.querySelector('input[type=password]').value===" + JSONObject.quote(secret));
      evaluateJavascript(scenario, "document.querySelector('form button[type=submit]').click()");
      awaitJavascript(scenario, "document.body.innerText.includes('Sync complete.')");
      assertTrue("The account journey must make requests", requests.get() > 0);
      assertEquals(
          "true",
          evaluateJavascript(
              scenario,
              "!JSON.stringify(window.__capturedStates).includes("
                  + JSONObject.quote(secret)
                  + ")"));
      assertFalse(
          new String(
                  new android.util.AtomicFile(
                          new java.io.File(context.getFilesDir(), "dashboard-v1.json"))
                      .readFully(),
                  java.nio.charset.StandardCharsets.UTF_8)
              .contains(secret));
      evaluateJavascript(
          scenario,
          "[...document.querySelectorAll('nav button')].find(b=>b.innerText.trim()==='Activity').click()");
      awaitJavascript(scenario, "document.body.innerText.includes('Fixture completed task')");
      offline.set(true);
      evaluateJavascript(
          scenario,
          "[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='Refresh').click()");
      awaitJavascript(scenario, "document.body.innerText.includes('Saved data is unchanged')");
      assertEquals(
          "true",
          evaluateJavascript(
              scenario, "document.body.innerText.includes('Fixture completed task')"));
      offline.set(false);
      evaluateJavascript(
          scenario,
          "[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='Refresh').click()");
      awaitJavascript(scenario, "document.body.innerText.includes('Sync complete.')");
      assertEquals(
          "true",
          evaluateJavascript(
              scenario, "document.body.innerText.split('Fixture completed task').length===2"));
    } finally {
      if (testModel.get() != null)
        InstrumentationRegistry.getInstrumentation()
            .runOnMainSync(() -> testModel.get().onCleared());
      new SnapshotStore(context).clear();
      new TokenStore(context).clear();
    }
  }

  private static String evaluateJavascript(ActivityScenario<MainActivity> scenario, String script)
      throws Exception {
    var webField = MainActivity.class.getDeclaredField("web");
    webField.setAccessible(true);
    CountDownLatch received = new CountDownLatch(1);
    AtomicReference<String> value = new AtomicReference<>();
    scenario.onActivity(
        activity -> {
          try {
            ((WebView) webField.get(activity))
                .evaluateJavascript(
                    script,
                    result -> {
                      value.set(result);
                      received.countDown();
                    });
          } catch (IllegalAccessException error) {
            throw new AssertionError(error);
          }
        });
    assertTrue("WebView evaluation timed out", received.await(30, TimeUnit.SECONDS));
    return value.get();
  }

  private static void awaitJavascript(ActivityScenario<MainActivity> scenario, String condition)
      throws Exception {
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(90);
    while (System.nanoTime() < deadline) {
      if ("true".equals(evaluateJavascript(scenario, "Boolean(" + condition + ")"))) return;
      Thread.sleep(200);
    }
    fail("WebView condition timed out: " + condition);
  }

  @Test
  public void newerDashboardReplacesSlowAttentionCalculation() throws Exception {
    var clock = java.time.Clock.systemDefaultZone();
    JSONObject large = DemoData.create(clock);
    JSONArray tasks = new JSONArray();
    for (int i = 0; i < 3000; i++)
      tasks.put(
          new JSONObject()
              .put("id", "old-" + i)
              .put("project_id", "missing")
              .put("content", "Old task")
              .put("labels", new JSONArray().put("old-only")));
    large.put("tasks", tasks);
    DashboardModel oldModel = new DashboardModel(large, clock);
    JSONObject small = DemoData.create(clock);
    small.put(
        "tasks",
        new JSONArray()
            .put(
                new JSONObject()
                    .put("id", "new")
                    .put("project_id", "missing")
                    .put("content", "New task")
                    .put("labels", new JSONArray().put("new-only"))));
    DashboardModel newModel = new DashboardModel(small, clock);
    AlertRules rules = new AlertRules();
    rules.fireLabels = "new-only";
    rules.priority = rules.due = rules.deadline = false;
    assertEquals(
        1,
        MainActivity.dashboardDetails(
                newModel, rules, java.time.LocalDate.now(clock), clock.getZone())
            .getJSONObject("alert")
            .getInt("matches"));
    rules.enabled = false;
    assertEquals(
        0,
        MainActivity.dashboardDetails(
                newModel, rules, java.time.LocalDate.now(clock), clock.getZone())
            .getJSONObject("alert")
            .getInt("matches"));
    var readyField = MainActivity.class.getDeclaredField("ready");
    var stateField = MainActivity.class.getDeclaredField("state");
    var webField = MainActivity.class.getDeclaredField("web");
    var publish = MainActivity.class.getDeclaredMethod("publish", boolean.class);
    readyField.setAccessible(true);
    stateField.setAccessible(true);
    webField.setAccessible(true);
    publish.setAccessible(true);
    try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
      AtomicReference<Boolean> ready = new AtomicReference<>(false);
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
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
      assertTrue("The WebView must be ready", ready.get());
      CountDownLatch installed = new CountDownLatch(1);
      scenario.onActivity(
          activity -> {
            try {
              ((WebView) webField.get(activity))
                  .evaluateJavascript(
                      "window.__attentionEvents=[];window.addEventListener('todoist-state',"
                          + "e=>window.__attentionEvents.push(e.detail.preferences.labels));",
                      ignored -> installed.countDown());
            } catch (IllegalAccessException failure) {
              throw new AssertionError(failure);
            }
          });
      assertTrue(installed.await(30, TimeUnit.SECONDS));
      scenario.onActivity(
          activity -> {
            try {
              stateField.set(
                  activity,
                  new DashboardViewModel.State(oldModel, false, true, false, true, "Old"));
              publish.invoke(activity, false);
              stateField.set(
                  activity,
                  new DashboardViewModel.State(newModel, false, false, false, true, "New"));
              publish.invoke(activity, false);
            } catch (ReflectiveOperationException failure) {
              throw new AssertionError(failure);
            }
          });
      AtomicReference<String> events = new AtomicReference<>("");
      deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
      while (!events.get().contains("new-only") && System.nanoTime() < deadline) {
        CountDownLatch received = new CountDownLatch(1);
        scenario.onActivity(
            activity -> {
              try {
                ((WebView) webField.get(activity))
                    .evaluateJavascript(
                        "JSON.stringify(window.__attentionEvents)",
                        value -> {
                          events.set(value);
                          received.countDown();
                        });
              } catch (IllegalAccessException failure) {
                throw new AssertionError(failure);
              }
            });
        assertTrue(received.await(30, TimeUnit.SECONDS));
        if (!events.get().contains("new-only")) Thread.sleep(200);
      }
      assertTrue("The new account details must arrive", events.get().contains("new-only"));
      assertFalse("Old account details must not overwrite them", events.get().contains("old-only"));
    }
  }

  @Test
  public void javascriptConfirmationUsesNativeActionsAndClosesWithTheActivity() throws Exception {
    var field = MainActivity.class.getDeclaredField("confirmation");
    field.setAccessible(true);
    try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
      awaitJavascript(scenario, "!!document.querySelector('header h1')");
      // Exercise the real dialog callbacks and WebView result without routing
      // input through whatever window currently owns emulator focus.
      AlertDialog previous = null;
      for (int action :
          new int[] {DialogInterface.BUTTON_NEGATIVE, DialogInterface.BUTTON_POSITIVE, 0}) {
        var answer = requestConfirmation(scenario);
        AlertDialog dialog = waitForConfirmation(scenario, field, previous);
        scenario.onActivity(
            activity -> {
              if (action == 0) {
                dialog.cancel();
              } else {
                var button = dialog.getButton(action);
                assertTrue(
                    "The native action must be visible and enabled",
                    button.isShown() && button.isEnabled());
                assertTrue("The native action must have a click handler", button.performClick());
              }
            });
        assertEquals(
            Boolean.toString(action == DialogInterface.BUTTON_POSITIVE),
            answer.get(30, TimeUnit.SECONDS));
        previous = dialog;
      }

      requestConfirmation(scenario);
      AlertDialog dialog = waitForConfirmation(scenario, field, previous);
      scenario.moveToState(Lifecycle.State.DESTROYED);
      assertFalse("Closing the activity must dismiss its confirmation", dialog.isShowing());
    }
  }

  private static CompletableFuture<String> requestConfirmation(
      ActivityScenario<MainActivity> scenario) throws Exception {
    var field = MainActivity.class.getDeclaredField("web");
    field.setAccessible(true);
    var answer = new CompletableFuture<String>();
    scenario.onActivity(
        activity -> {
          try {
            ((WebView) field.get(activity))
                .evaluateJavascript("window.confirm('Confirm test action?')", answer::complete);
          } catch (IllegalAccessException error) {
            throw new AssertionError(error);
          }
        });
    return answer;
  }

  private static AlertDialog waitForConfirmation(
      ActivityScenario<MainActivity> scenario, java.lang.reflect.Field field, AlertDialog previous)
      throws Exception {
    AtomicReference<AlertDialog> visible = new AtomicReference<>();
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(45);
    while (System.nanoTime() < deadline) {
      scenario.onActivity(
          activity -> {
            try {
              AlertDialog dialog = (AlertDialog) field.get(activity);
              if (dialog == null || dialog == previous || !dialog.isShowing()) return;
              android.widget.TextView message = dialog.findViewById(android.R.id.message);
              if (message != null && message.isShown() && message.getWidth() > 0) {
                assertEquals("Confirm test action?", message.getText().toString());
                visible.set(dialog);
              }
            } catch (IllegalAccessException error) {
              throw new AssertionError(error);
            }
          });
      if (visible.get() != null) return visible.get();
      Thread.sleep(200);
    }
    throw new AssertionError("The WebView must show its message in the native confirmation");
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
