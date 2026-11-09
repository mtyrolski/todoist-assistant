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
import java.util.concurrent.atomic.AtomicInteger;
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
    start(token -> transport);
  }

  private void start(java.util.function.Function<String, ApiTransport> transports)
      throws Exception {
    new SnapshotStore(context).clear();
    new TokenStore(context).clear();
    attach(transports);
  }

  private void attach(java.util.function.Function<String, ApiTransport> transports)
      throws Exception {
    attach(transports, new TokenStore(context));
  }

  private void attach(
      java.util.function.Function<String, ApiTransport> transports, TokenStore credentials)
      throws Exception {
    CountDownLatch loaded = new CountDownLatch(1);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model =
                  new DashboardViewModel(
                      (Application) context.getApplicationContext(),
                      transports,
                      credentials,
                      new SnapshotStore(context));
              observer =
                  value -> {
                    state.set(value);
                    if (!value.loading) loaded.countDown();
                  };
              model.state().observeForever(observer);
            });
    assertTrue(loaded.await(10, TimeUnit.SECONDS));
  }

  private void detach() {
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().removeObserver(observer);
              model.onCleared();
            });
  }

  private static JSONObject savedHistory() throws Exception {
    return DemoData.create(java.time.Clock.systemUTC())
        .put("userId", "test-owner")
        .put("adjustments", new JSONObject().put("mappings", new JSONObject().put("Old", "Work")));
  }

  private static class Fake implements ApiTransport {
    final CountDownLatch fetching = new CountDownLatch(1), release = new CountDownLatch(1);
    final AtomicBoolean cancelled = new AtomicBoolean();
    volatile boolean block;

    @Override
    public JSONObject get(String path)
        throws java.io.IOException, org.json.JSONException, InterruptedException {
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
  public void localDayAndTimezoneChangeRebuildsCachedModelWithoutNetworkOrStorageWrites()
      throws Exception {
    AtomicInteger requests = new AtomicInteger();
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            requests.incrementAndGet();
            return super.get(path);
          }
        };
    start(fake);
    CountDownLatch synced = new CountDownLatch(1);
    Observer<DashboardViewModel.State> syncObserver =
        value -> {
          if (!value.syncing && value.model != null && value.message.startsWith("Sync complete"))
            synced.countDown();
        };
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().observeForever(syncObserver);
              model.sync("clock-test-token");
            });
    assertTrue(synced.await(20, TimeUnit.SECONDS));
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(() -> model.state().removeObserver(syncObserver));
    int beforeRequests = requests.get();
    String before = new SnapshotStore(context).load("clock-test-token").toString();
    java.time.Clock changed =
        java.time.Clock.fixed(
            java.time.Instant.parse("2030-01-10T12:00:00Z"), java.time.ZoneId.of("Asia/Tokyo"));
    CountDownLatch updated = new CountDownLatch(1);
    Observer<DashboardViewModel.State> updatedObserver =
        value -> {
          if (!value.loading
              && value.model != null
              && value.model.zoneId.equals(changed.getZone())
              && value.model.renderedOn.equals(java.time.LocalDate.now(changed)))
            updated.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(updatedObserver);
                model.refreshClock(changed);
                model.refreshClock(changed);
              });
      assertTrue(updated.await(20, TimeUnit.SECONDS));
      assertEquals(beforeRequests, requests.get());
      assertEquals(before, new SnapshotStore(context).load("clock-test-token").toString());
      assertEquals(java.time.LocalDate.of(2030, 1, 7), state.get().model.weekStart);
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(updatedObserver));
    }
  }

  @Test
  public void interruptedTokenUpdateRecoversTheMatchingCredentialAndHistory() throws Exception {
    TokenStore credentials = new TokenStore(context);
    SnapshotStore history = new SnapshotStore(context);
    credentials.clear();
    history.clear();
    credentials.stage("old-token");
    credentials.promotePending();
    history.save(savedHistory(), "old-token");
    credentials.stage("new-token");
    Fake offline =
        new Fake() {
          @Override
          public JSONObject get(String path) throws java.io.IOException {
            throw new java.net.UnknownHostException();
          }
        };
    attach(token -> offline);
    assertEquals("old-token", credentials.load());
    assertEquals("", credentials.loadPending());
    assertEquals("test-owner", history.load("old-token").getString("userId"));
    detach();

    credentials.stage("new-token");
    history.save(savedHistory(), "new-token");
    attach(token -> offline);
    assertEquals("new-token", credentials.load());
    assertEquals("", credentials.loadPending());
    assertEquals(
        "Work",
        history
            .load("new-token")
            .getJSONObject("adjustments")
            .getJSONObject("mappings")
            .getString("Old"));
  }

  @Test
  public void rejectedSavedTokenIsNotRetriedAfterRestartAndCanBeReplaced() throws Exception {
    TokenStore credentials = new TokenStore(context);
    SnapshotStore history = new SnapshotStore(context);
    credentials.clear();
    history.clear();
    credentials.stage("revoked-token");
    credentials.promotePending();
    history.save(savedHistory(), "revoked-token");
    AtomicInteger attempts = new AtomicInteger();
    Fake denied =
        new Fake() {
          @Override
          public JSONObject get(String path) throws java.io.IOException {
            attempts.incrementAndGet();
            throw new HttpTransport.AuthenticationFailure();
          }
        };
    Fake accepted = new Fake();
    java.util.function.Function<String, ApiTransport> transports =
        token -> token.equals("revoked-token") ? denied : accepted;
    attach(transports);
    CountDownLatch deniedResult = new CountDownLatch(1);
    Observer<DashboardViewModel.State> deniedObserver =
        value -> {
          if (!value.syncing && value.message.contains("token was rejected"))
            deniedResult.countDown();
        };
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(() -> model.state().observeForever(deniedObserver));
    assertTrue(deniedResult.await(15, TimeUnit.SECONDS));
    assertTrue(credentials.isRejected());
    assertEquals(1, attempts.get());
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(() -> model.state().removeObserver(deniedObserver));
    detach();

    attach(transports);
    InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync(""));
    assertEquals(1, attempts.get());
    assertTrue(state.get().message.contains("rejected"));
    assertNotNull(state.get().model);
    CountDownLatch saved = new CountDownLatch(1);
    Observer<DashboardViewModel.State> savedObserver =
        value -> {
          if (!value.syncing && value.message.startsWith("Sync complete")) saved.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(savedObserver);
                model.sync("replacement-token");
              });
      assertTrue(saved.await(20, TimeUnit.SECONDS));
      assertEquals("replacement-token", credentials.load());
      assertFalse(credentials.isRejected());
      assertEquals(
          "Work",
          history
              .load("replacement-token")
              .getJSONObject("adjustments")
              .getJSONObject("mappings")
              .getString("Old"));
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(savedObserver));
    }
  }

  @Test
  public void corruptCredentialCanBeReenteredWithoutLosingMatchingHistory() throws Exception {
    TokenStore credentials = new TokenStore(context);
    SnapshotStore history = new SnapshotStore(context);
    credentials.clear();
    history.clear();
    history.save(savedHistory(), "original-token");
    context
        .getSharedPreferences("auth", Context.MODE_PRIVATE)
        .edit()
        .putString("token", "broken")
        .commit();
    AtomicInteger calls = new AtomicInteger();
    Fake accepted =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            calls.incrementAndGet();
            return super.get(path);
          }
        };
    attach(token -> accepted);
    assertTrue(model.hasSavedHistory());
    assertFalse(state.get().connected);
    CountDownLatch mismatch = new CountDownLatch(1);
    Observer<DashboardViewModel.State> mismatchObserver =
        value -> {
          if (!value.syncing && value.message.contains("could not be verified"))
            mismatch.countDown();
        };
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              model.state().observeForever(mismatchObserver);
              model.sync("different-token");
            });
    assertTrue(mismatch.await(10, TimeUnit.SECONDS));
    assertEquals(0, calls.get());
    assertEquals("test-owner", history.load("original-token").getString("userId"));
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(() -> model.state().removeObserver(mismatchObserver));
    CountDownLatch saved = new CountDownLatch(1);
    Observer<DashboardViewModel.State> savedObserver =
        value -> {
          if (!value.syncing && value.message.startsWith("Sync complete")) saved.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(savedObserver);
                model.sync("original-token");
              });
      assertTrue(saved.await(20, TimeUnit.SECONDS));
      assertEquals("original-token", credentials.load());
      assertEquals(
          "Work",
          history
              .load("original-token")
              .getJSONObject("adjustments")
              .getJSONObject("mappings")
              .getString("Old"));
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(savedObserver));
    }
  }

  @Test
  public void corruptStagedCredentialCanBeReenteredAfterSnapshotWasCommitted() throws Exception {
    TokenStore credentials = new TokenStore(context);
    SnapshotStore history = new SnapshotStore(context);
    credentials.clear();
    history.clear();
    credentials.stage("old-token");
    credentials.promotePending();
    history.save(savedHistory(), "new-token");
    context
        .getSharedPreferences("auth", Context.MODE_PRIVATE)
        .edit()
        .putString("pending", "broken")
        .commit();
    attach(token -> new Fake());
    assertTrue(model.hasSavedHistory());
    assertTrue(state.get().message.contains("could not be opened"));
    CountDownLatch saved = new CountDownLatch(1);
    Observer<DashboardViewModel.State> savedObserver =
        value -> {
          if (!value.syncing && value.message.startsWith("Sync complete")) saved.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(savedObserver);
                model.sync("new-token");
              });
      assertTrue(saved.await(20, TimeUnit.SECONDS));
      assertEquals("new-token", credentials.load());
      assertEquals(
          "Work",
          history
              .load("new-token")
              .getJSONObject("adjustments")
              .getJSONObject("mappings")
              .getString("Old"));
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(savedObserver));
    }
  }

  @Test
  public void corruptHistoryIsNotOverwrittenByARefresh() throws Exception {
    TokenStore credentials = new TokenStore(context);
    credentials.clear();
    new SnapshotStore(context).clear();
    credentials.stage("valid-token");
    credentials.promotePending();
    byte[] damaged = "{damaged history".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    try (var output = context.openFileOutput("dashboard-v1.json", Context.MODE_PRIVATE)) {
      output.write(damaged);
    }
    AtomicInteger calls = new AtomicInteger();
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            calls.incrementAndGet();
            return super.get(path);
          }
        };
    attach(token -> fake);
    assertTrue(model.hasSavedHistory());
    CountDownLatch failed = new CountDownLatch(1);
    Observer<DashboardViewModel.State> failedObserver =
        value -> {
          if (!value.syncing && value.message.contains("could not be verified")) failed.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(failedObserver);
                model.sync("");
              });
      assertTrue(failed.await(10, TimeUnit.SECONDS));
      assertEquals(0, calls.get());
      try (var input = context.openFileInput("dashboard-v1.json")) {
        byte[] actual = new byte[damaged.length];
        assertEquals(damaged.length, input.read(actual));
        assertArrayEquals(damaged, actual);
      }
      assertEquals("valid-token", credentials.load());
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(failedObserver));
    }
  }

  @Test
  public void invalidReplacementDoesNotInvalidateTheSavedAccount() throws Exception {
    TokenStore credentials = new TokenStore(context);
    SnapshotStore history = new SnapshotStore(context);
    credentials.clear();
    history.clear();
    credentials.stage("saved-token");
    credentials.promotePending();
    history.save(savedHistory(), "saved-token");
    Fake offline =
        new Fake() {
          @Override
          public JSONObject get(String path) throws java.io.IOException {
            throw new java.net.UnknownHostException();
          }
        };
    AtomicInteger attempts = new AtomicInteger();
    Fake denied =
        new Fake() {
          @Override
          public JSONObject get(String path) throws java.io.IOException {
            attempts.incrementAndGet();
            throw new HttpTransport.AuthenticationFailure();
          }
        };
    attach(token -> token.equals("saved-token") ? offline : denied);
    CountDownLatch offlineResult = new CountDownLatch(1), deniedResult = new CountDownLatch(1);
    Observer<DashboardViewModel.State> observer =
        value -> {
          if (!value.syncing
              && (value.message.contains("unreachable") || value.message.contains("No network")))
            offlineResult.countDown();
          if (!value.syncing && value.message.contains("token was rejected"))
            deniedResult.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().observeForever(observer));
      assertTrue(offlineResult.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("invalid-token"));
      assertTrue(deniedResult.await(10, TimeUnit.SECONDS));
      assertEquals("saved-token", credentials.load());
      assertFalse(credentials.isRejected());
      assertEquals("test-owner", history.load("saved-token").getString("userId"));
      InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("invalid-token"));
      assertEquals(1, attempts.get());
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(observer));
    }
  }

  @Test
  public void differentAccountCannotOverwriteSavedHistoryWithoutDisconnecting() throws Exception {
    TokenStore credentials = new TokenStore(context);
    SnapshotStore history = new SnapshotStore(context);
    credentials.clear();
    history.clear();
    credentials.stage("saved-token");
    credentials.promotePending();
    history.save(savedHistory(), "saved-token");
    Fake offline =
        new Fake() {
          @Override
          public JSONObject get(String path) throws java.io.IOException {
            throw new java.net.UnknownHostException();
          }
        };
    AtomicInteger calls = new AtomicInteger();
    Fake other =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            calls.incrementAndGet();
            if (path.equals("user")) return new JSONObject().put("id", "different-owner");
            return super.get(path);
          }
        };
    attach(token -> token.equals("saved-token") ? offline : other);
    CountDownLatch offlineResult = new CountDownLatch(1), mismatch = new CountDownLatch(1);
    Observer<DashboardViewModel.State> result =
        value -> {
          if (!value.syncing
              && (value.message.contains("unreachable") || value.message.contains("No network")))
            offlineResult.countDown();
          if (!value.syncing && value.message.contains("does not match saved history"))
            mismatch.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().observeForever(result));
      assertTrue(offlineResult.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("other-token"));
      assertTrue(mismatch.await(10, TimeUnit.SECONDS));
      assertEquals(1, calls.get());
      assertEquals("saved-token", credentials.load());
      assertEquals(
          "Work",
          history
              .load("saved-token")
              .getJSONObject("adjustments")
              .getJSONObject("mappings")
              .getString("Old"));
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(result));
    }
  }

  @Test
  public void failedTokenPromotionBlocksWritesUntilRestartRecovery() throws Exception {
    TokenStore credentials = new TokenStore(context);
    SnapshotStore history = new SnapshotStore(context);
    credentials.clear();
    history.clear();
    credentials.stage("old-token");
    credentials.promotePending();
    history.save(savedHistory(), "old-token");
    TokenStore failedPromotion =
        new TokenStore(context) {
          @Override
          void promotePending() throws Exception {
            super.promotePending();
            throw new java.io.IOException("simulated failed commit after memory update");
          }
        };
    AtomicInteger calls = new AtomicInteger();
    Fake offline =
        new Fake() {
          @Override
          public JSONObject get(String path) throws java.io.IOException {
            throw new java.net.UnknownHostException();
          }
        };
    Fake accepted =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            calls.incrementAndGet();
            return super.get(path);
          }
        };
    attach(token -> token.equals("old-token") ? offline : accepted, failedPromotion);
    CountDownLatch offlineResult = new CountDownLatch(1), recovery = new CountDownLatch(1);
    Observer<DashboardViewModel.State> result =
        value -> {
          if (!value.syncing
              && (value.message.contains("unreachable") || value.message.contains("No network")))
            offlineResult.countDown();
          if (!value.syncing && value.message.contains("needs recovery")) recovery.countDown();
        };
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(() -> model.state().observeForever(result));
    assertTrue(offlineResult.await(10, TimeUnit.SECONDS));
    InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("new-token"));
    assertTrue(recovery.await(20, TimeUnit.SECONDS));
    int completedCalls = calls.get();
    InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("new-token"));
    assertEquals(completedCalls, calls.get());
    assertEquals("new-token", credentials.load());
    assertEquals(
        "Work",
        history
            .load("new-token")
            .getJSONObject("adjustments")
            .getJSONObject("mappings")
            .getString("Old"));
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(() -> model.state().removeObserver(result));
    detach();
    attach(token -> offline);
    assertEquals("new-token", credentials.load());
    assertNotNull(state.get().model);
    assertEquals(
        "Work",
        history
            .load("new-token")
            .getJSONObject("adjustments")
            .getJSONObject("mappings")
            .getString("Old"));
  }

  @Test
  public void transportCreationFailureFinishesLoadingWithoutLeakingDetails() throws Exception {
    start(
        token -> {
          throw new IllegalStateException("private-test-token");
        });
    CountDownLatch failed = new CountDownLatch(1);
    Observer<DashboardViewModel.State> failedObserver =
        value -> {
          if (!value.syncing && value.message.startsWith("Sync failed")) failed.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(failedObserver);
                model.sync("private-test-token");
              });
      assertTrue(failed.await(10, TimeUnit.SECONDS));
      assertFalse(state.get().message.contains("private-test-token"));
      assertNull(state.get().model);
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(failedObserver));
    }
  }

  @Test
  public void newerSyncCompletesBeforeCancelledSlowResponseAndCannotBeOverwritten()
      throws Exception {
    CountDownLatch slowStarted = new CountDownLatch(1),
        releaseSlow = new CountDownLatch(1),
        slowReturned = new CountDownLatch(1);
    AtomicInteger created = new AtomicInteger();
    Fake slow =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user")) {
              slowStarted.countDown();
              while (true) {
                try {
                  if (releaseSlow.await(10, TimeUnit.SECONDS)) break;
                } catch (InterruptedException ignored) {
                  /* Simulate an uncooperative network call. */
                }
              }
              slowReturned.countDown();
              return new JSONObject()
                  .put("id", "old-owner")
                  .put("joined_at", java.time.Instant.now().minusSeconds(86400).toString());
            }
            return super.get(path);
          }

          @Override
          public void cancel() {
            /* The response can arrive after cancellation. */
          }
        };
    Fake fast =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user"))
              return new JSONObject()
                  .put("id", "new-owner")
                  .put("joined_at", java.time.Instant.now().minusSeconds(86400).toString());
            return super.get(path);
          }
        };
    start(
        token -> {
          created.incrementAndGet();
          return token.equals("old-token") ? slow : fast;
        });
    CountDownLatch saved = new CountDownLatch(1);
    Observer<DashboardViewModel.State> savedObserver =
        value -> {
          if (!value.syncing && value.message.startsWith("Sync complete")) saved.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(savedObserver);
                model.sync("old-token");
              });
      assertTrue(slowStarted.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.sync("duplicate-token");
                model.cancelSync();
                model.sync("new-token");
              });
      assertTrue(
          "new request must not wait for the obsolete one", saved.await(15, TimeUnit.SECONDS));
      assertEquals(2, created.get());
      assertEquals("new-owner", new SnapshotStore(context).load("new-token").getString("userId"));
      releaseSlow.countDown();
      assertTrue(slowReturned.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation().waitForIdleSync();
      assertEquals("new-owner", new SnapshotStore(context).load("new-token").getString("userId"));
      assertEquals("new-token", new TokenStore(context).load());
    } finally {
      releaseSlow.countDown();
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(savedObserver));
    }
  }

  @Test
  public void manualRetryCannotBypassRateLimit() throws Exception {
    AtomicInteger attempts = new AtomicInteger();
    Fake limited =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            attempts.incrementAndGet();
            throw new HttpTransport.Failure("Rate limited", 10000);
          }
        };
    start(limited);
    CountDownLatch failed = new CountDownLatch(1);
    Observer<DashboardViewModel.State> failedObserver =
        value -> {
          if (!value.syncing && value.message.equals("Rate limited")) failed.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(failedObserver);
                model.sync("private-test-token");
              });
      assertTrue(failed.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.sync("private-test-token"));
      assertEquals(1, attempts.get());
      assertTrue(state.get().message.contains("wait before retrying"));
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(failedObserver));
    }
  }

  @Test
  public void saturatedCancelledRequestsReturnAnErrorInsteadOfQueueingForever() throws Exception {
    CountDownLatch first = new CountDownLatch(1),
        both = new CountDownLatch(2),
        release = new CountDownLatch(1);
    AtomicInteger started = new AtomicInteger();
    Fake slow =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user")) {
              started.incrementAndGet();
              first.countDown();
              both.countDown();
              while (true) {
                try {
                  if (release.await(15, TimeUnit.SECONDS)) break;
                  throw new java.io.IOException("test timed out");
                } catch (InterruptedException ignored) {
                  /* Simulate an uncooperative call. */
                }
              }
            }
            return super.get(path);
          }

          @Override
          public void cancel() {}
        };
    start(slow);
    try {
      InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync("first"));
      assertTrue(first.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.cancelSync();
                model.sync("second");
              });
      assertTrue(both.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.cancelSync();
                model.sync("third");
              });
      assertFalse(state.get().syncing);
      assertTrue(state.get().message.contains("still stopping"));
      assertEquals(2, started.get());
    } finally {
      release.countDown();
    }
  }

  @Test
  public void syncFinishesWhileScreenIsStoppedAndPublishesOnReturn() throws Exception {
    Fake fake = new Fake();
    fake.block = true;
    start(fake);
    class Owner implements androidx.lifecycle.LifecycleOwner {
      final androidx.lifecycle.LifecycleRegistry lifecycle =
          new androidx.lifecycle.LifecycleRegistry(this);

      @Override
      public androidx.lifecycle.Lifecycle getLifecycle() {
        return lifecycle;
      }
    }
    AtomicReference<Owner> owner = new AtomicReference<>();
    AtomicReference<DashboardViewModel.State> shown = new AtomicReference<>();
    CountDownLatch complete = new CountDownLatch(1);
    Observer<DashboardViewModel.State> completedObserver =
        value -> {
          if (!value.syncing && value.message.startsWith("Sync complete")) complete.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                Owner value = new Owner();
                owner.set(value);
                value.lifecycle.setCurrentState(androidx.lifecycle.Lifecycle.State.STARTED);
                model.state().observe(value, shown::set);
                model.state().observeForever(completedObserver);
                model.sync("fake-test-token");
              });
      assertTrue(fake.fetching.await(10, TimeUnit.SECONDS));
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () ->
                  owner
                      .get()
                      .lifecycle
                      .setCurrentState(androidx.lifecycle.Lifecycle.State.CREATED));
      fake.release.countDown();
      assertTrue(complete.await(15, TimeUnit.SECONDS));
      assertTrue(shown.get().syncing);
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () ->
                  owner
                      .get()
                      .lifecycle
                      .setCurrentState(androidx.lifecycle.Lifecycle.State.STARTED));
      assertFalse(shown.get().syncing);
      assertNotNull(shown.get().model);
      assertTrue(shown.get().message.startsWith("Sync complete"));
    } finally {
      fake.release.countDown();
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                owner.get().lifecycle.setCurrentState(androidx.lifecycle.Lifecycle.State.DESTROYED);
                model.state().removeObserver(completedObserver);
              });
    }
  }

  @Test
  public void unreachableTodoistReturnsToDisconnectedState() throws Exception {
    Fake offline =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
  public void interruptedResponseExplainsConnectionFailureWithoutLeakingData() throws Exception {
    Fake interrupted =
        new Fake() {
          @Override
          public JSONObject get(String path) throws java.io.IOException {
            throw new java.io.EOFException("private-test-token");
          }
        };
    start(interrupted);
    CountDownLatch failed = new CountDownLatch(1);
    Observer<DashboardViewModel.State> failure =
        value -> {
          if (!value.syncing && value.message.contains("connection to Todoist was interrupted"))
            failed.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(failure);
                model.sync("private-test-token");
              });
      assertTrue(failed.await(10, TimeUnit.SECONDS));
      assertFalse(state.get().message.contains("private-test-token"));
      assertNull(state.get().model);
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(failure));
    }
  }

  @Test
  public void savedAccountSurvivesOfflineRestartAndRetry() throws Exception {
    class Flaky extends Fake {
      volatile boolean offline;

      @Override
      public JSONObject get(String path)
          throws java.io.IOException, org.json.JSONException, InterruptedException {
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
  public void offlineRetryKeepsHistoryAndMergesAnotherClientsActivityOnce() throws Exception {
    class Remote extends Fake {
      volatile boolean offline;
      volatile int revision;
      final AtomicInteger userRequests = new AtomicInteger();
      final String older = java.time.Instant.now().minusSeconds(90).toString();
      final String newer = java.time.Instant.now().minusSeconds(30).toString();

      JSONObject event(String id, String date) throws Exception {
        return new JSONObject()
            .put("id", id)
            .put("object_type", "item")
            .put("object_id", "task-" + id)
            .put("event_type", "completed")
            .put("event_date", date)
            .put("parent_project_id", "project");
      }

      @Override
      public JSONObject get(String path)
          throws java.io.IOException, org.json.JSONException, InterruptedException {
        if (offline) throw new java.net.UnknownHostException("offline");
        if (path.equals("user")) {
          userRequests.incrementAndGet();
          return new JSONObject()
              .put("id", "test-owner")
              .put("joined_at", java.time.Instant.now().minusSeconds(86400).toString());
        }
        if (path.startsWith("activities")) {
          try {
            JSONObject first = event("older", older);
            JSONArray rows = new JSONArray().put(first).put(first);
            if (revision > 0) rows.put(event("newer", newer));
            return new JSONObject().put("results", rows).put("next_cursor", JSONObject.NULL);
          } catch (Exception invalid) {
            throw new org.json.JSONException("Invalid test activity");
          }
        }
        return super.get(path);
      }
    }
    Remote remote = new Remote();
    start(remote);
    CountDownLatch initial = new CountDownLatch(1),
        failed = new CountDownLatch(1),
        refreshed = new CountDownLatch(1);
    AtomicInteger successful = new AtomicInteger();
    Observer<DashboardViewModel.State> changes =
        value -> {
          if (!value.syncing && value.model != null && value.message.startsWith("Sync complete")) {
            if (successful.incrementAndGet() == 1) initial.countDown();
            else refreshed.countDown();
          }
          if (!value.syncing
              && (value.message.contains("unreachable") || value.message.contains("No network")))
            failed.countDown();
        };
    try {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.state().observeForever(changes);
                model.sync("test-token");
              });
      assertTrue(initial.await(20, TimeUnit.SECONDS));
      SnapshotStore history = new SnapshotStore(context);
      JSONObject before = history.load("test-token");
      assertEquals(1, before.getJSONArray("activities").length());
      remote.offline = true;
      InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> model.sync(""));
      assertTrue(failed.await(15, TimeUnit.SECONDS));
      assertEquals(before.toString(), history.load("test-token").toString());
      assertEquals("older", state.get().model.recent.get(0).id);

      remote.offline = false;
      remote.revision = 1; // Another client completed a task while this device was offline.
      int requestsBeforeRetry = remote.userRequests.get();
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(
              () -> {
                model.sync("");
                model.sync("");
                model.sync("");
              });
      assertTrue(refreshed.await(20, TimeUnit.SECONDS));
      assertEquals(requestsBeforeRetry + 1, remote.userRequests.get());
      assertEquals(2, history.load("test-token").getJSONArray("activities").length());
      assertEquals("newer", state.get().model.recent.get(0).id);
      assertEquals("older", state.get().model.recent.get(1).id);
    } finally {
      InstrumentationRegistry.getInstrumentation()
          .runOnMainSync(() -> model.state().removeObserver(changes));
    }
    detach();
    remote.offline = true;
    attach(token -> remote);
    assertNotNull(state.get().model);
    assertEquals(2, state.get().model.recent.size());
    assertEquals(
        2, new SnapshotStore(context).load("test-token").getJSONArray("activities").length());
  }

  @Test
  public void incompatibleResponseIsNotReportedAsEmptySuccess() throws Exception {
    Fake broken =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
