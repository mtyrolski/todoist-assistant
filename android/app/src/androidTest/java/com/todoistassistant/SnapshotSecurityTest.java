package com.todoistassistant;

import static org.junit.Assert.*;

import android.content.Context;
import androidx.test.platform.app.InstrumentationRegistry;
import java.time.Clock;
import org.junit.After;
import org.junit.Test;

public class SnapshotSecurityTest {
  private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();

  @Test
  public void largeIdentifiersStayExactOnAndroid() throws Exception {
    String id = "1234567890123456789012345678901234567";
    String json = "{\"id\":" + id + "}";
    Object original = new org.json.JSONObject(json).get("id");
    android.util.Log.i(
        "TodoistIdentifierTest",
        "Android numeric JSON type: " + original.getClass().getSimpleName());
    assertEquals(
        id, new org.json.JSONObject(HttpTransport.protectIdentifiers(json)).getString("id"));
  }

  @After
  public void clear() {
    new SnapshotStore(context).clear();
    new TokenStore(context).clear();
  }

  @Test
  public void deviceKeystoreRoundTripsTheTokenWithoutPlaintextPreferences() throws Exception {
    TokenStore store = new TokenStore(context);
    store.stage("fake-private-token-for-test");
    store.promotePending();
    assertEquals("fake-private-token-for-test", store.load());
    String persisted =
        context.getSharedPreferences("auth", Context.MODE_PRIVATE).getString("token", "");
    assertFalse(persisted.contains("fake-private-token-for-test"));
  }

  @Test
  public void stagedCredentialDoesNotReplaceTheCurrentCredentialPrematurely() throws Exception {
    TokenStore store = new TokenStore(context);
    store.stage("old-secret");
    store.promotePending();
    store.stage("new-secret");
    assertEquals("old-secret", store.load());
    assertEquals("new-secret", store.loadPending());
    String preferences =
        context.getSharedPreferences("auth", Context.MODE_PRIVATE).getAll().toString();
    assertFalse(preferences.contains("old-secret"));
    assertFalse(preferences.contains("new-secret"));
    store.promotePending();
    assertEquals("new-secret", store.load());
    assertEquals("", store.loadPending());
  }

  @Test
  public void malformedCredentialPreferenceIsReportedWithoutDeletingIt() throws Exception {
    var prefs = context.getSharedPreferences("auth", Context.MODE_PRIVATE);
    prefs.edit().putInt("token", 42).commit();
    assertThrows(java.io.IOException.class, () -> new TokenStore(context).load());
    assertEquals(42, prefs.getInt("token", 0));
  }

  @Test
  public void invalidSettingsUseDefaultsWithoutDeletingStoredValues() throws Exception {
    var preferences = context.getSharedPreferences("rules", Context.MODE_PRIVATE);
    preferences.edit().putInt("config", 42).putString("web", "{broken").commit();
    try {
      var settings = MainActivity.readSettings(preferences);
      assertTrue(settings.getJSONObject("rules").getBoolean("enabled"));
      assertTrue(settings.isNull("settings"));
      assertEquals(42, preferences.getInt("config", 0));
      assertEquals("{broken", preferences.getString("web", ""));
    } finally {
      preferences.edit().clear().commit();
    }
  }

  @Test
  public void androidBackupIsDisabledForAppData() {
    assertEquals(
        0,
        context.getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_ALLOW_BACKUP);
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
