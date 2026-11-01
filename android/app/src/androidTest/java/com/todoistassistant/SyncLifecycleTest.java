package com.todoistassistant;

import static org.junit.Assert.*;

import android.app.Application;
import android.content.Context;
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
    boolean block;

    @Override
    public JSONObject get(String path) throws Exception {
      if (path.equals("user")) return new JSONObject().put("id", "test-owner");
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
  public void successfulSyncCommitsCredentialsAndSnapshotTogether() throws Exception {
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
  }
}
