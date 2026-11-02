package com.todoistassistant;

import static org.junit.Assert.*;

import java.io.IOException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public class TodoistClientTest {
  private static final Clock CLOCK =
      Clock.fixed(Instant.parse("2026-11-01T12:00:00Z"), ZoneId.of("Europe/Warsaw"));

  private static JSONObject page(JSONArray items, Object cursor) throws Exception {
    return new JSONObject().put("results", items).put("next_cursor", cursor);
  }

  private static JSONObject event(String id, String when) throws Exception {
    return new JSONObject()
        .put("id", id)
        .put("event_date", when)
        .put("event_type", "completed")
        .put("object_type", "item")
        .put("object_id", id);
  }

  static class Fake implements ApiTransport {
    final List<String> paths = new ArrayList<>();
    String user = "owner";
    boolean failActivity;

    @Override
    public JSONObject get(String path) throws Exception {
      paths.add(path);
      if (path.equals("user")) return new JSONObject().put("id", user);
      if (path.startsWith("activities")) {
        if (failActivity) throw new IOException("offline");
        return page(new JSONArray().put(event("new", "2026-11-01T10:00:00Z")), JSONObject.NULL);
      }
      return page(new JSONArray(), JSONObject.NULL);
    }

    @Override
    public void cancel() {}
  }

  private static JSONObject baseline() throws Exception {
    return new JSONObject()
        .put("userId", "owner")
        .put("historyStart", "2025-01-01T00:00:00Z")
        .put("activities", new JSONArray().put(event("old", "2026-10-31T12:00:00Z")));
  }

  @Test
  public void sameAccountKeepsHistoryEvenWhenItsTokenChanges() throws Exception {
    Fake fake = new Fake();
    JSONObject next = new TodoistClient(fake, CLOCK, message -> {}).snapshot(baseline(), false);
    assertEquals(2, next.getJSONArray("activities").length());
    assertEquals("2025-01-01T00:00:00Z", next.getString("historyStart"));
    assertTrue(fake.paths.stream().anyMatch(path -> path.contains("2026-10-30T12%3A00%3A00Z")));
  }

  @Test
  public void switchingAccountsDoesNotMergePrivateHistory() throws Exception {
    Fake fake = new Fake();
    fake.user = "someone-else";
    JSONObject next = new TodoistClient(fake, CLOCK, message -> {}).snapshot(baseline(), true);
    assertEquals(1, next.getJSONArray("activities").length());
    assertEquals("someone-else", next.getString("userId"));
    assertNotEquals("2025-01-01T00:00:00Z", next.getString("historyStart"));
  }

  @Test
  public void schemaOneHistoryOnlyMigratesWithTheSavedCredential() throws Exception {
    JSONObject old = baseline();
    old.remove("userId");
    Fake fake = new Fake();
    assertEquals(
        2,
        new TodoistClient(fake, CLOCK, message -> {})
            .snapshot(old, true)
            .getJSONArray("activities")
            .length());
    assertEquals(
        1,
        new TodoistClient(fake, CLOCK, message -> {})
            .snapshot(old, false)
            .getJSONArray("activities")
            .length());
  }

  @Test
  public void failedSyncDoesNotMutateThePreviousSnapshot() throws Exception {
    Fake fake = new Fake();
    fake.failActivity = true;
    JSONObject old = baseline();
    String original = old.toString();
    try {
      new TodoistClient(fake, CLOCK, message -> {}).snapshot(old, true);
      fail("Expected sync failure");
    } catch (IOException expected) {
      assertEquals("offline", expected.getMessage());
    }
    assertEquals(original, old.toString());
  }

  @Test
  public void emptyCursorEndsPaginationWithoutAnExtraRequest() throws Exception {
    Fake fake = new Fake();
    new TodoistClient(fake, CLOCK, message -> {}).list("tasks", "Tasks");
    assertEquals(1, fake.paths.size());
  }

  @Test
  public void repeatedCursorsFailInsteadOfHangingForever() throws Exception {
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            return page(new JSONArray(), "same");
          }
        };
    try {
      new TodoistClient(fake, CLOCK, message -> {}).list("tasks", "Tasks");
      fail("Expected repeated cursor failure");
    } catch (IOException expected) {
      assertTrue(expected.getMessage().contains("repeated"));
    }
  }

  @Test
  public void paginationEscapesOpaqueCursorsAndReportsProgress() throws Exception {
    List<String> progress = new ArrayList<>();
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            paths.add(path);
            return page(
                new JSONArray().put(new JSONObject().put("id", paths.size())),
                paths.size() == 1 ? "next +/&?" : JSONObject.NULL);
          }
        };
    assertEquals(2, new TodoistClient(fake, CLOCK, progress::add).list("tasks", "Tasks").length());
    assertTrue(fake.paths.get(1).contains("next+%2B%2F%26%3F"));
    assertEquals(List.of("Tasks…", "Tasks · 1 loaded", "Tasks · 2 loaded"), progress);
  }

  @Test
  public void snapshotTimestampMatchesTheApiUpperBound() throws Exception {
    Fake fake = new Fake();
    JSONObject next =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false);
    assertEquals(CLOCK.instant().toString(), next.getString("syncedAt"));
    assertTrue(
        fake.paths.stream().anyMatch(path -> path.contains("date_to=2026-11-01T12%3A00%3A00Z")));
  }

  @Test
  public void extremeRetryAfterCannotOverflowIntoAnImmediateRetry() {
    assertEquals(30000, HttpTransport.retryDelay(String.valueOf(Long.MAX_VALUE), 0));
    assertEquals(500, HttpTransport.retryDelay("-100", 0));
    assertEquals(2000, HttpTransport.retryDelay(null, 1));
  }

  @Test
  public void missingActivityPermissionStillSavesCoreDataWithoutInventingHistory()
      throws Exception {
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            if (path.startsWith("activities")) throw new DataAccessException("forbidden");
            return super.get(path);
          }
        };
    JSONObject next =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false);
    assertTrue(next.getBoolean("activityUnavailable"));
    DashboardModel model = new DashboardModel(next, CLOCK);
    assertFalse(model.historyAvailable);
    assertFalse(model.forecastAvailable);
    assertFalse(model.historyWarning.isEmpty());
  }

  @Test
  public void archivedMetadataFailureDoesNotDiscardFreshActivity() throws Exception {
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            if (path.startsWith("projects/archived")) throw new IOException("metadata offline");
            return super.get(path);
          }
        };
    JSONObject next =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false);
    assertEquals(1, next.getJSONArray("activities").length());
    assertTrue(next.has("metadataWarning"));
    assertEquals(CLOCK.instant().toString(), next.getString("activitySyncedAt"));
  }

  @Test
  public void archivedRefreshRetainsKnownParentWithoutChangingPreviousSnapshot() throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Root");
    JSONObject child =
        new JSONObject().put("id", "child").put("name", "Child").put("parent_id", "root");
    JSONObject before = baseline().put("projects", new JSONArray().put(root).put(child));
    String original = before.toString();
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            if (path.startsWith("projects/archived"))
              return page(
                  new JSONArray()
                      .put(
                          new JSONObject()
                              .put("id", "child")
                              .put("name", "Child")
                              .put("parent_id", JSONObject.NULL)),
                  JSONObject.NULL);
            if (path.startsWith("projects?"))
              return page(new JSONArray().put(root), JSONObject.NULL);
            return super.get(path);
          }
        };
    JSONObject next = new TodoistClient(fake, CLOCK, message -> {}).snapshot(before, false);
    assertEquals(original, before.toString());
    assertEquals(
        "root", next.getJSONArray("knownProjects").getJSONObject(1).getString("parent_id"));
    assertEquals(
        "Root / Child",
        DashboardModel.projectPath(
            "child",
            java.util.Map.of(
                "root", root, "child", next.getJSONArray("knownProjects").getJSONObject(1))));
  }

  @Test
  public void archiveEventRecoversParentAndRejectsCycles() throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Root");
    JSONObject child = new JSONObject().put("id", "child").put("name", "Child");
    JSONObject archivedEvent =
        new JSONObject()
            .put("id", "archive")
            .put("event_date", "2026-10-31T12:00:00Z")
            .put("object_type", "project")
            .put("object_id", "child")
            .put("event_type", "archived")
            .put("parent_project_id", "root");
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path) throws Exception {
            if (path.startsWith("projects/archived"))
              return page(new JSONArray().put(child), JSONObject.NULL);
            if (path.startsWith("projects?"))
              return page(new JSONArray().put(root), JSONObject.NULL);
            if (path.startsWith("activities"))
              return page(
                  new JSONArray()
                      .put(archivedEvent)
                      .put(event("done", "2026-11-01T10:00:00Z").put("parent_project_id", "child")),
                  JSONObject.NULL);
            return super.get(path);
          }
        };
    JSONObject next =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false);
    assertEquals(
        "root", next.getJSONArray("knownProjects").getJSONObject(0).getString("parent_id"));
    assertEquals(1, new DashboardModel(next, CLOCK).weeklyProjects.get(8).get("Root").intValue());
    root.put("parent_id", "child");
    JSONObject cyclic =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false);
    assertEquals(
        "", cyclic.getJSONArray("knownProjects").getJSONObject(0).optString("parent_id", ""));
  }
}
