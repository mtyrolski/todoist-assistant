package com.todoistassistant;

import static org.junit.Assert.*;

import android.app.Application;
import android.content.Context;
import android.net.Uri;
import androidx.lifecycle.Observer;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.After;
import org.junit.Test;

public class SyncLifecycleTest {
  private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
  private DashboardViewModel model;
  private Observer<DashboardViewModel.State> observer;
  private final AtomicReference<DashboardViewModel.State> state = new AtomicReference<>();

  @After
  public void clean() {
    if (model != null)
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().removeObserver(observer);
                model.onCleared();
              });
    new SnapshotStore(context).clear();
    new TokenStore(context).clear();
    context.getSharedPreferences("rules", Context.MODE_PRIVATE).edit().clear().commit();
  }

  private void start(ApiTransport transport) throws Exception {
    new SnapshotStore(context).clear();
    new TokenStore(context).clear();
    CountDownLatch loaded = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model =
                  new DashboardViewModel(
                      (Application) context.getApplicationContext(), token -> transport);
              observer =
                  value -> {
                    state.set(value);
                    if (!value.loading) loaded.countDown();
                  };
              model.state().observeForever(observer);
            });
    assertTrue(loaded.await(10, TimeUnit.SECONDS));
  }

  private static class Fake implements ApiTransport {
    final CountDownLatch fetching = new CountDownLatch(1), release = new CountDownLatch(1);
    final AtomicBoolean cancelled = new AtomicBoolean();
    volatile boolean block;

    @Override
    public JSONObject get(String path) throws Exception {
      if (path.equals("user"))
        return new JSONObject()
            .put("id", "test-owner")
            .put("joined_at", java.time.Instant.now().minusSeconds(800L * 86400).toString());
      if (path.startsWith("activities")) {
        fetching.countDown();
        if (block) release.await(10, TimeUnit.SECONDS);
        if (cancelled.get()) throw new SyncCancelledException();
      }
      return new JSONObject().put("results", new JSONArray()).put("next_cursor", JSONObject.NULL);
    }

    @Override
    public void cancel() {
      cancelled.set(true);
      release.countDown();
    }
  }

  @Test
  public void startsDisconnectedWhenNoCredentialsAreSaved() throws Exception {
    start(new Fake());
    assertFalse(state.get().loading);
    assertFalse(state.get().syncing);
    assertFalse(state.get().connected);
    assertNull(state.get().model);
  }

  @Test
  public void unreachableTodoistReturnsToDisconnectedState() throws Exception {
    Fake offline =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            throw new java.net.UnknownHostException("offline");
          }
        };
    start(offline);
    CountDownLatch failure = new CountDownLatch(1);
    Observer<DashboardViewModel.State> failed =
        value -> {
          if (!value.syncing
              && (value.message.contains("unreachable") || value.message.contains("No network")))
            failure.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(failed);
                model.sync("example-token");
              });
      assertTrue(failure.await(10, TimeUnit.SECONDS));
      assertFalse(state.get().connected);
      assertNull(state.get().model);
      assertEquals("", new TokenStore(context).load());
      android.net.ConnectivityManager manager =
          context.getSystemService(android.net.ConnectivityManager.class);
      android.net.Network network = manager.getActiveNetwork();
      android.net.NetworkCapabilities capabilities =
          network == null ? null : manager.getNetworkCapabilities(network);
      boolean online =
          capabilities != null
              && capabilities.hasCapability(
                  android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET);
      assertTrue(state.get().message.contains(online ? "unreachable" : "No network"));
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(failed));
    }
  }

  @Test
  public void savedAccountSurvivesOfflineRestartAndRetry() throws Exception {
    class Flaky extends Fake {
      volatile boolean offline;

      @Override
      public JSONObject get(String path) throws Exception {
        if (offline) throw new java.net.UnknownHostException("private-test-token");
        return super.get(path);
      }
    }
    Flaky fake = new Flaky();
    start(fake);
    CountDownLatch saved = new CountDownLatch(1);
    Observer<DashboardViewModel.State> savedObserver =
        value -> {
          if (!value.syncing && value.model != null && value.message.startsWith("Sync complete"))
            saved.countDown();
        };
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().observeForever(savedObserver);
              model.sync("private-test-token");
            });
    assertTrue(saved.await(15, TimeUnit.SECONDS));
    fake.offline = true;
    CountDownLatch offline = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(savedObserver);
              model.state().removeObserver(observer);
              model.onCleared();
              model =
                  new DashboardViewModel(
                      (Application) context.getApplicationContext(), token -> fake);
              observer =
                  value -> {
                    state.set(value);
                    if (!value.syncing
                        && (value.message.contains("unreachable")
                            || value.message.contains("No network"))) offline.countDown();
                  };
              model.state().observeForever(observer);
            });
    assertTrue(offline.await(15, TimeUnit.SECONDS));
    assertNotNull(state.get().model);
    assertTrue(state.get().connected);
    assertFalse(state.get().message.contains("private-test-token"));
    assertEquals("private-test-token", new TokenStore(context).load());

    fake.offline = false;
    CountDownLatch recovered = new CountDownLatch(1);
    Observer<DashboardViewModel.State> recoveredObserver =
        value -> {
          if (!value.syncing && value.message.startsWith("Sync complete")) recovered.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(recoveredObserver);
                model.sync("");
              });
      assertTrue(recovered.await(15, TimeUnit.SECONDS));
      assertEquals(
          "test-owner", new SnapshotStore(context).load("private-test-token").getString("userId"));
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(recoveredObserver));
    }
  }

  @Test
  public void incompatibleResponseIsNotReportedAsEmptySuccess() throws Exception {
    Fake broken =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            throw new org.json.JSONException("private-test-token");
          }
        };
    start(broken);
    CountDownLatch failed = new CountDownLatch(1);
    Observer<DashboardViewModel.State> failedObserver =
        value -> {
          if (!value.syncing && value.message.contains("incompatible response")) failed.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(failedObserver);
                model.sync("private-test-token");
              });
      assertTrue(failed.await(10, TimeUnit.SECONDS));
      assertNull(state.get().model);
      assertFalse(state.get().message.contains("private-test-token"));
      assertEquals("", new TokenStore(context).load());
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(failedObserver));
    }
  }

  @Test
  public void cancelStopsNetworkWorkWithoutSavingAPartialAccount() throws Exception {
    Fake fake = new Fake();
    fake.block = true;
    start(fake);
    InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("fake-test-token"));
    assertTrue(fake.fetching.await(10, TimeUnit.SECONDS));
    InstrumentationRegistry.getInstrumentation().runOnMainSync(model::cancelSync);
    assertTrue(fake.cancelled.get());
    assertFalse(state.get().syncing);
    assertEquals("", new TokenStore(context).load());
    assertFalse(context.getFileStreamPath("dashboard-v1.json").exists());
  }

  @Test
  public void cancellationAfterACompletedWindowKeepsThatHistoryOnDevice() throws Exception {
    Fake fake =
        new Fake() {
          int activityRequests;

          @Override
          public JSONObject get(String path) throws Exception {
            if (path.startsWith("activities") && ++activityRequests == 2) block = true;
            return super.get(path);
          }
        };
    start(fake);
    InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("fake-test-token"));
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
    while (!fake.block && System.nanoTime() < deadline) Thread.sleep(20);
    assertTrue(fake.block);
    while (state.get().model == null && System.nanoTime() < deadline) Thread.sleep(20);
    assertTrue(state.get().syncing);
    assertNotNull(state.get().model);
    InstrumentationRegistry.getInstrumentation().runOnMainSync(model::cancelSync);
    JSONObject saved = new SnapshotStore(context).load("fake-test-token");
    assertFalse(saved.getBoolean("historyComplete"));
    assertEquals("test-owner", saved.getString("userId"));
    assertEquals("fake-test-token", new TokenStore(context).load());
    assertNotNull(state.get().model);
  }

  @Test
  public void syncAndDisconnectSaveThenRemoveLocalAccountData() throws Exception {
    Fake fake = new Fake();
    start(fake);
    CountDownLatch saved = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              observer =
                  value -> {
                    state.set(value);
                    if (!value.syncing && value.model != null && value.connected) saved.countDown();
                  };
              model.state().observeForever(observer);
              model.sync("fake-test-token");
            });
    assertTrue(saved.await(15, TimeUnit.SECONDS));
    assertEquals("fake-test-token", new TokenStore(context).load());
    assertEquals(
        "test-owner", new SnapshotStore(context).load("fake-test-token").getString("userId"));
    assertEquals(0, state.get().model.tasks.size());
    var file = new java.io.File(context.getCacheDir(), "test-adjustments.json");
    try (var output = new java.io.FileOutputStream(file)) {
      output.write(
          "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{\"Old\":\"Work\"},\"archivedParents\":[]}"
              .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    CountDownLatch imported = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              observer =
                  value -> {
                    state.set(value);
                    if (value.message.equals("Project adjustments imported.")) imported.countDown();
                  };
              model.state().observeForever(observer);
              model.importAdjustments(Uri.fromFile(file));
            });
    assertTrue(imported.await(10, TimeUnit.SECONDS));
    assertEquals(
        "Work",
        new SnapshotStore(context)
            .load("fake-test-token")
            .getJSONObject("adjustments")
            .getJSONObject("mappings")
            .getString("Old"));
    assertTrue(file.delete());
    CountDownLatch edited = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              observer =
                  value -> {
                    state.set(value);
                    if (value.message.equals("Project adjustments saved.")) edited.countDown();
                  };
              model.state().observeForever(observer);
              model.saveAdjustments(
                  "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{\"Old\":\"Work\",\"Missing\":\"Unknown"
                      + " root\"},\"archivedParents\":[\"Another archive\"]}");
            });
    assertTrue(edited.await(10, TimeUnit.SECONDS));
    JSONObject persisted =
        new SnapshotStore(context).load("fake-test-token").getJSONObject("adjustments");
    assertEquals("Work", persisted.getJSONObject("mappings").getString("Old"));
    assertEquals("Unknown root", persisted.getJSONObject("mappings").getString("Missing"));
    assertEquals("Another archive", persisted.getJSONArray("archivedParents").getString(0));
    assertEquals(
        "Unknown root",
        MobilePayload.model(state.get().model)
            .getJSONObject("adjustments")
            .getJSONObject("mappings")
            .getString("Missing"));
    try (var output = new java.io.FileOutputStream(file)) {
      output.write(
          "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{\"Old\":\"New root\",\"Another archive\":\"Work\"},\"archivedParents\":[\"Imported parent\"]}"
              .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    CountDownLatch merged = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              observer =
                  value -> {
                    state.set(value);
                    if (value.message.equals("Project adjustments imported.")) merged.countDown();
                  };
              model.state().observeForever(observer);
              model.importAdjustments(Uri.fromFile(file));
            });
    assertTrue(merged.await(10, TimeUnit.SECONDS));
    JSONObject afterImport =
        new SnapshotStore(context).load("fake-test-token").getJSONObject("adjustments");
    assertEquals("New root", afterImport.getJSONObject("mappings").getString("Old"));
    assertEquals("Unknown root", afterImport.getJSONObject("mappings").getString("Missing"));
    assertEquals("Work", afterImport.getJSONObject("mappings").getString("Another archive"));
    assertEquals(1, afterImport.getJSONArray("archivedParents").length());
    assertEquals("Imported parent", afterImport.getJSONArray("archivedParents").getString(0));
    assertTrue(file.delete());
    CountDownLatch invalid = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              observer =
                  value -> {
                    state.set(value);
                    if (value.message.startsWith("Could not save project adjustments"))
                      invalid.countDown();
                  };
              model.state().observeForever(observer);
              model.saveAdjustments(
                  "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{\"Old\":42},\"archivedParents\":[]}");
            });
    assertTrue(invalid.await(10, TimeUnit.SECONDS));
    assertEquals(
        "Unknown root",
        new SnapshotStore(context)
            .load("fake-test-token")
            .getJSONObject("adjustments")
            .getJSONObject("mappings")
            .getString("Missing"));
    CountDownLatch demo = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              observer =
                  value -> {
                    state.set(value);
                    if (value.demo && !value.loading) demo.countDown();
                  };
              model.state().observeForever(observer);
              model.showDemo();
            });
    assertTrue(demo.await(10, TimeUnit.SECONDS));
    InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.saveAdjustments("{}"));
    assertTrue(state.get().demo);
    assertEquals(
        "Unknown root",
        new SnapshotStore(context)
            .load("fake-test-token")
            .getJSONObject("adjustments")
            .getJSONObject("mappings")
            .getString("Missing"));
    context
        .getSharedPreferences("rules", Context.MODE_PRIVATE)
        .edit()
        .putString("web", "private-label")
        .commit();
    CountDownLatch disconnected = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              observer =
                  value -> {
                    if (!value.loading && !value.connected && value.model == null)
                      disconnected.countDown();
                  };
              model.state().observeForever(observer);
              model.disconnect();
            });
    assertTrue(disconnected.await(10, TimeUnit.SECONDS));
    assertEquals("", new TokenStore(context).load());
    assertFalse(context.getFileStreamPath("dashboard-v1.json").exists());
    assertTrue(context.getSharedPreferences("rules", Context.MODE_PRIVATE).getAll().isEmpty());
  }
}
