package com.todoistassistant;

import static org.junit.Assert.*;

import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import java.time.Clock;
import org.junit.After;
import org.junit.Test;

public class SnapshotSecurityTest {
  private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();

  @After
  public void clear() {
    new SnapshotStore(context).clear();
    new TokenStore(context).clear();
  }

  @Test
  public void deviceKeystoreRoundTripsTheTokenWithoutPlaintextPreferences() throws Exception {
    TokenStore store = new TokenStore(context);
    store.save("fake-private-token-for-test");
    assertEquals("fake-private-token-for-test", store.load());
    String persisted =
        context.getSharedPreferences("auth", Context.MODE_PRIVATE).getString("token", "");
    assertFalse(persisted.contains("fake-private-token-for-test"));
  }

  @Test
  public void snapshotCannotBeOpenedWithAnotherCredential() throws Exception {
    SnapshotStore store = new SnapshotStore(context);
    store.save(DemoData.create(Clock.systemUTC()), "first-test-token");
    assertEquals("demo", store.load("first-test-token").getString("userId"));
    try {
      store.load("another-test-token");
      fail("Expected credential isolation");
    } catch (java.io.IOException expected) {
      assertTrue(expected.getMessage().contains("different connection"));
    }
  }

  @Test
  public void corruptHistoryReportsAnErrorInsteadOfPretendingItIsEmpty() throws Exception {
    try (var stream = context.openFileOutput("dashboard-v1.json", Context.MODE_PRIVATE)) {
      stream.write("broken-json".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    try {
      new SnapshotStore(context).load("test-token");
      fail("Expected invalid history");
    } catch (org.json.JSONException expected) {
      assertTrue(context.getFileStreamPath("dashboard-v1.json").exists());
    }
  }

  @Test
  public void failedCredentialWriteRollsBackTheEntireSnapshot() throws Exception {
    SnapshotStore store = new SnapshotStore(context);
    var original = DemoData.create(Clock.systemUTC()).put("userId", "first");
    store.save(original, "old-token");
    try {
      store.save(
          DemoData.create(Clock.systemUTC()).put("userId", "second"),
          "new-token",
          () -> {
            throw new java.io.IOException("disk full");
          });
      fail("Expected failed credential commit");
    } catch (java.io.IOException expected) {
      assertEquals("disk full", expected.getMessage());
    }
    assertEquals("first", store.load("old-token").getString("userId"));
  }
}
