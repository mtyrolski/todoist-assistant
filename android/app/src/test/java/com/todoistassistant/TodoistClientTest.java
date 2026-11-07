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

  private static JSONObject page(JSONArray items, Object cursor) throws org.json.JSONException {
    return new JSONObject().put("results", items).put("next_cursor", cursor);
  }

  private static JSONObject event(String id, String when) throws org.json.JSONException {
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
    public JSONObject get(String path)
        throws java.io.IOException, org.json.JSONException, InterruptedException {
      paths.add(path);
      if (path.equals("user"))
        return new JSONObject().put("id", user).put("joined_at", "2026-08-01T00:00:00Z");
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
        .put("syncedAt", "2026-10-31T12:00:00Z")
        .put("activitySyncedAt", "2026-10-31T12:00:00Z")
        .put("historyComplete", true)
        .put("historyStart", "2025-01-01T00:00:00Z")
        .put("activities", new JSONArray().put(event("old", "2026-10-31T12:00:00Z")));
  }

  @Test
  public void missingJoinDateDoesNotBackfillTo1970OrClaimCompleteHistory() throws Exception {
    Fake fake =
        new Fake() {
          int activityRequests;

          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user")) return new JSONObject().put("id", user);
            if (path.startsWith("activities") && ++activityRequests > 3)
              throw new IOException("Unexpected unbounded history request");
            return super.get(path);
          }
        };
    JSONObject result =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false);
    assertEquals("2026-08-09T12:00:00Z", result.getString("historyStart"));
    assertFalse(result.getBoolean("historyComplete"));
    assertTrue(result.getString("activityWarning").contains("join date"));
  }

  @Test
  public void historyResumesWhenJoinDateBecomesAvailable() throws Exception {
    Fake fake =
        new Fake() {
          boolean missingJoinDate = true;

          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user") && missingJoinDate) {
              missingJoinDate = false;
              return new JSONObject().put("id", user);
            }
            return super.get(path);
          }
        };
    TodoistClient client = new TodoistClient(fake, CLOCK, message -> {});
    JSONObject partial = client.snapshot(new JSONObject(), false);
    JSONObject resumed = client.snapshot(partial, true);
    assertTrue(resumed.getBoolean("historyComplete"));
    assertEquals("2026-08-01T00:00:00Z", resumed.getString("historyStart"));
    assertFalse(resumed.has("activityWarning"));
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
  public void switchingAccountsRequiresExplicitRemovalOfSavedHistory() throws Exception {
    Fake fake = new Fake();
    fake.user = "someone-else";
    JSONObject previous = baseline();
    String original = previous.toString();
    HttpTransport.Failure error =
        assertThrows(
            HttpTransport.Failure.class,
            () -> new TodoistClient(fake, CLOCK, message -> {}).snapshot(previous, true));
    assertTrue(error.getMessage().contains("Disconnect"));
    assertEquals(original, previous.toString());
  }

  @Test
  public void importedAdjustmentsStayWithTheirAccountOnRefresh() throws Exception {
    JSONObject before =
        baseline()
            .put(
                "adjustments",
                new JSONObject().put("mappings", new JSONObject().put("Old", "Work")));
    Fake fake = new Fake();
    JSONObject same = new TodoistClient(fake, CLOCK, message -> {}).snapshot(before, false);
    assertEquals(
        "Work", same.getJSONObject("adjustments").getJSONObject("mappings").getString("Old"));
    fake.user = "other-owner";
    assertThrows(
        HttpTransport.Failure.class,
        () -> new TodoistClient(fake, CLOCK, message -> {}).snapshot(before, false));
    assertEquals(
        "Work", before.getJSONObject("adjustments").getJSONObject("mappings").getString("Old"));
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
    assertThrows(
        HttpTransport.Failure.class,
        () -> new TodoistClient(fake, CLOCK, message -> {}).snapshot(old, false));
    old.put("userId", JSONObject.NULL);
    assertEquals(
        2,
        new TodoistClient(fake, CLOCK, message -> {})
            .snapshot(old, true)
            .getJSONArray("activities")
            .length());
    assertThrows(
        HttpTransport.Failure.class,
        () -> new TodoistClient(fake, CLOCK, message -> {}).snapshot(old, false));
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
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
  public void fullHistoryContinuesFromSavedCheckpointAfterFailure() throws Exception {
    List<JSONObject> checkpoints = new ArrayList<>();
    Fake fake =
        new Fake() {
          boolean interrupted;

          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user"))
              return new JSONObject().put("id", user).put("joined_at", "2026-08-03T12:00:00Z");
            if (path.startsWith("activities")) {
              paths.add(path);
              if (path.contains("date_from=2026-09-02T12%3A00%3A00Z") && !interrupted) {
                interrupted = true;
                throw new IOException("offline");
              }
              if (path.contains("date_from=2026-08-03T12%3A00%3A00Z"))
                return page(
                    new JSONArray().put(event("oldest", "2026-08-15T00:00:00Z")), JSONObject.NULL);
              if (path.contains("date_from=2026-09-02T12%3A00%3A00Z"))
                return page(
                    new JSONArray().put(event("middle", "2026-09-15T00:00:00Z")), JSONObject.NULL);
              return page(
                  new JSONArray().put(event("recent", "2026-10-15T00:00:00Z")), JSONObject.NULL);
            }
            return super.get(path);
          }
        };
    TodoistClient client = new TodoistClient(fake, CLOCK, message -> {});
    try {
      client.snapshot(
          new JSONObject(), false, data -> checkpoints.add(new JSONObject(data.toString())));
      fail("Expected history download to be interrupted");
    } catch (IOException expected) {
      assertEquals("offline", expected.getMessage());
    }
    assertEquals(1, checkpoints.size());
    JSONObject partial = checkpoints.get(0);
    assertFalse(partial.getBoolean("historyComplete"));
    assertEquals("2026-10-02T12:00:00Z", partial.getString("historyStart"));
    assertEquals(1, partial.getJSONArray("activities").length());

    JSONObject resumed = client.snapshot(partial, false);
    assertTrue(resumed.getBoolean("historyComplete"));
    assertEquals("2026-08-03T12:00:00Z", resumed.getString("historyStart"));
    assertEquals(3, resumed.getJSONArray("activities").length());
  }

  @Test
  public void existingTwelveWeekSnapshotBackfillsOlderHistory() throws Exception {
    JSONObject old = baseline().put("historyStart", "2026-08-10T00:00:00Z");
    old.remove("historyComplete");
    Fake fake = new Fake();
    JSONObject next = new TodoistClient(fake, CLOCK, message -> {}).snapshot(old, false);
    assertTrue(next.getBoolean("historyComplete"));
    assertEquals("2026-08-01T00:00:00Z", next.getString("historyStart"));
    assertTrue(fake.paths.stream().anyMatch(path -> path.contains("2026-08-01T00%3A00%3A00Z")));
  }

  @Test
  public void emptyWindowsDoNotHideOlderHistory() throws Exception {
    Fake fake =
        new Fake() {
          int windows;

          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user"))
              return new JSONObject().put("id", user).put("joined_at", "2024-01-01T00:00:00Z");
            if (path.startsWith("activities")) {
              windows++;
              JSONArray events = new JSONArray();
              if (windows == 5) events.put(event("old", "2024-09-01T00:00:00Z"));
              return page(events, JSONObject.NULL);
            }
            return super.get(path);
          }
        };
    JSONObject next =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false);
    assertTrue(next.getBoolean("historyComplete"));
    assertEquals("old", next.getJSONArray("activities").getJSONObject(0).getString("id"));
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
  public void adjacentHistoryWindowsUseInclusiveStartAndExclusiveEnd() throws Exception {
    JSONArray events =
        new JSONArray()
            .put(event("before-boundary", "2026-10-02T11:59:59.999Z"))
            .put(event("at-boundary", "2026-10-02T12:00:00Z"))
            .put(event("at-upper-bound", "2026-11-01T12:00:00Z"));
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user"))
              return new JSONObject().put("id", user).put("joined_at", "2026-09-02T12:00:00Z");
            if (path.startsWith("activities?")) {
              Instant from = null, to = null;
              for (String parameter : path.substring(path.indexOf('?') + 1).split("&")) {
                String[] parts = parameter.split("=", 2);
                if (parts.length != 2) continue;
                String value = java.net.URLDecoder.decode(parts[1], "UTF-8");
                if (parts[0].equals("date_from")) from = Instant.parse(value);
                if (parts[0].equals("date_to")) to = Instant.parse(value);
              }
              assertNotNull(from);
              assertNotNull(to);
              JSONArray included = new JSONArray();
              for (int i = 0; i < events.length(); i++) {
                JSONObject item = events.getJSONObject(i);
                Instant when = Instant.parse(item.getString("event_date"));
                if (!when.isBefore(from) && when.isBefore(to)) included.put(item);
              }
              return page(included, JSONObject.NULL);
            }
            return super.get(path);
          }
        };
    JSONArray saved =
        new TodoistClient(fake, CLOCK, ignored -> {})
            .snapshot(new JSONObject(), false)
            .getJSONArray("activities");
    assertEquals(2, saved.length());
    assertEquals("at-boundary", saved.getJSONObject(0).getString("id"));
    assertEquals("before-boundary", saved.getJSONObject(1).getString("id"));
  }

  @Test
  public void extremeRetryAfterCannotOverflowIntoAnImmediateRetry() {
    assertEquals(Long.MAX_VALUE, HttpTransport.retryDelay(String.valueOf(Long.MAX_VALUE), 0));
    assertEquals(Long.MAX_VALUE, HttpTransport.retryDelay("9999999999999999999999", 0));
    assertEquals(300000, HttpTransport.retryDelay("300", 0));
    assertEquals(500, HttpTransport.retryDelay("-100", 0));
    assertEquals(2000, HttpTransport.retryDelay(null, 1));
    assertEquals(16000, HttpTransport.retryDelay(null, 4));
    assertEquals(30000, HttpTransport.retryDelay(null, 8));
  }

  @Test
  public void invalidPaginationAndMissingIdentifiersDoNotBecomePartialHistory() throws Exception {
    for (JSONObject invalid :
        new JSONObject[] {
          new JSONObject().put("results", new JSONArray()),
          page(new JSONArray(), new JSONObject()),
          page(new JSONArray().put(new JSONObject().put("id", JSONObject.NULL)), JSONObject.NULL)
        }) {
      Fake fake =
          new Fake() {
            @Override
            public JSONObject get(String path)
                throws java.io.IOException, org.json.JSONException, InterruptedException {
              if (path.startsWith("projects?")) return invalid;
              return super.get(path);
            }
          };
      assertThrows(
          org.json.JSONException.class,
          () -> new TodoistClient(fake, CLOCK, ignored -> {}).snapshot(new JSONObject(), false));
    }
    Fake invalidAccount =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws IOException, org.json.JSONException, InterruptedException {
            if (path.equals("user")) return new JSONObject().put("id", JSONObject.NULL);
            return super.get(path);
          }
        };
    assertThrows(
        org.json.JSONException.class,
        () ->
            new TodoistClient(invalidAccount, CLOCK, ignored -> {})
                .snapshot(new JSONObject(), false));
  }

  @Test
  public void malformedActivityCannotBeCheckpointed() throws Exception {
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.startsWith("activities")) {
              JSONObject invalid = event("event", "2026-10-01T00:00:00Z");
              invalid.remove("object_id");
              return page(new JSONArray().put(invalid), JSONObject.NULL);
            }
            return super.get(path);
          }
        };
    List<JSONObject> checkpoints = new ArrayList<>();
    assertThrows(
        org.json.JSONException.class,
        () ->
            new TodoistClient(fake, CLOCK, ignored -> {})
                .snapshot(new JSONObject(), false, checkpoints::add));
    assertTrue(checkpoints.isEmpty());
  }

  @Test
  public void largeNumericIdsRemainDistinctWithoutChangingTextOrOtherNumbers() throws Exception {
    String first = "1234567890123456789012345678901234567";
    String second = "1234567890123456789012345678901234568";
    String content = "quoted \\\"id\\\":1234567890123456789012345678901234567";
    String json =
        "{\"results\":[{\"id\":"
            + first
            + ",\"object_id\":42,\"priority\":3,\"content\":\""
            + content
            + "\"},{\"id\":"
            + second
            + "}],\"offset\":42}";
    JSONObject parsed = new JSONObject(HttpTransport.protectIdentifiers(json));
    JSONObject a = parsed.getJSONArray("results").getJSONObject(0);
    JSONObject b = parsed.getJSONArray("results").getJSONObject(1);
    assertEquals(first, a.getString("id"));
    assertEquals(second, b.getString("id"));
    assertEquals("42", a.getString("object_id"));
    assertEquals(3, a.getInt("priority"));
    assertEquals("quoted \"id\":1234567890123456789012345678901234567", a.getString("content"));
    assertEquals(42, parsed.getInt("offset"));
  }

  @Test
  public void syncRepairsRoundedCachedIdsWithoutCountingTheSameEventTwice() throws Exception {
    String exact = "1234567890123456789012345678901234567";
    JSONObject original = event(exact, "2026-10-31T10:00:00Z").put("object_id", "task");
    JSONObject rounded = new JSONObject(original.toString()).put("id", Double.parseDouble(exact));
    JSONObject old = baseline().put("activities", new JSONArray().put(rounded));
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.startsWith("activities"))
              return page(new JSONArray().put(original), JSONObject.NULL);
            return super.get(path);
          }
        };
    List<JSONObject> checkpoints = new ArrayList<>();
    JSONObject next =
        new TodoistClient(fake, CLOCK, message -> {})
            .snapshot(old, false, partial -> checkpoints.add(new JSONObject(partial.toString())));
    assertTrue(next.getBoolean("historyComplete"));
    assertTrue(next.getBoolean("historyIdRepair"));
    assertFalse(checkpoints.isEmpty());
    assertEquals(1, next.getJSONArray("activities").length());
    assertEquals(exact, next.getJSONArray("activities").getJSONObject(0).getString("id"));
  }

  @Test
  public void ambiguousRoundedIdsAreKeptInsteadOfDiscardingAnEvent() throws Exception {
    String first = "1234567890123456789012345678901234567";
    String second = "1234567890123456789012345678901234568";
    JSONObject a = event(first, "2026-10-31T10:00:00Z").put("object_id", "task");
    JSONObject b = new JSONObject(a.toString()).put("id", second);
    JSONObject old =
        baseline()
            .put(
                "activities",
                new JSONArray()
                    .put(new JSONObject(a.toString()).put("id", Double.parseDouble(first))));
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.startsWith("activities"))
              return page(new JSONArray().put(a).put(b), JSONObject.NULL);
            return super.get(path);
          }
        };
    JSONObject next = new TodoistClient(fake, CLOCK, message -> {}).snapshot(old, false);
    assertEquals(3, next.getJSONArray("activities").length());
    assertTrue(next.getString("activityWarning").contains("could not be matched"));
  }

  @Test
  public void missingActivityPermissionStillSavesCoreDataWithoutInventingHistory()
      throws Exception {
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
  public void deniedActivityRefreshKeepsTheOldActivityTimestampAndHistory() throws Exception {
    JSONObject previous = baseline();
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.startsWith("activities")) throw new DataAccessException("forbidden");
            return super.get(path);
          }
        };
    JSONObject next = new TodoistClient(fake, CLOCK, ignored -> {}).snapshot(previous, true);
    assertEquals(CLOCK.instant().toString(), next.getString("syncedAt"));
    assertEquals(previous.getString("activitySyncedAt"), next.getString("activitySyncedAt"));
    assertEquals(
        previous.getJSONArray("activities").toString(), next.getJSONArray("activities").toString());
    assertFalse(next.getBoolean("activityUnavailable"));
    assertTrue(next.getString("activityWarning").contains("not refreshed"));
    assertEquals(
        previous.getString("activitySyncedAt"),
        MobilePayload.model(new DashboardModel(next, CLOCK)).getString("activitySyncedAt"));
  }

  @Test
  public void payloadDoesNotInventAnExclusiveActivityTimestampForLegacyOrUnavailableHistory()
      throws Exception {
    JSONObject legacy = baseline().put("projects", new JSONArray()).put("tasks", new JSONArray());
    legacy.remove("activitySyncedAt");
    assertFalse(MobilePayload.model(new DashboardModel(legacy, CLOCK)).has("activitySyncedAt"));
    legacy.put("activitySyncedAt", CLOCK.instant().toString()).put("activityUnavailable", true);
    assertFalse(MobilePayload.model(new DashboardModel(legacy, CLOCK)).has("activitySyncedAt"));
  }

  @Test
  public void archivedMetadataPermissionFailureDoesNotDiscardFreshActivity() throws Exception {
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.startsWith("projects/archived")) throw new DataAccessException("forbidden");
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
  public void archivedMetadataNetworkFailureDoesNotBecomeSuccessfulEmptyData() throws Exception {
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.startsWith("projects/archived"))
              throw new java.net.SocketException("connection lost");
            return super.get(path);
          }
        };
    assertThrows(
        java.net.SocketException.class,
        () -> new TodoistClient(fake, CLOCK, message -> {}).snapshot(new JSONObject(), false));
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
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
  public void archiveEventProjectContextIsNotTreatedAsAParentLink() throws Exception {
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
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
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
    assertEquals("", TodoistClient.parentId(next.getJSONArray("knownProjects").getJSONObject(0)));
    assertEquals(1, new DashboardModel(next, CLOCK).weeklyProjects.get(8).get("Child").intValue());
  }

  @Test
  public void reopeningAfterPreviousSyncInvalidatesOldArchivedParent() throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Root");
    JSONObject previousChild =
        new JSONObject()
            .put("id", "child")
            .put("name", "Child")
            .put("is_archived", true)
            .put("parent_id", "root");
    JSONObject before =
        baseline()
            .put("syncedAt", "2026-10-31T00:00:00Z")
            .put("activitySyncedAt", "2026-10-28T00:00:00Z")
            .put("activities", new JSONArray())
            .put("knownProjects", new JSONArray().put(root).put(previousChild));
    JSONObject reopened =
        new JSONObject()
            .put("id", "reopened")
            .put("object_type", "project")
            .put("object_id", "child")
            .put("event_type", "unarchived")
            .put("event_date", "2026-10-30T10:00:00Z");
    JSONObject archived = new JSONObject().put("id", "child").put("name", "Child");
    Fake fake =
        new Fake() {
          @Override
          public JSONObject get(String path)
              throws java.io.IOException, org.json.JSONException, InterruptedException {
            if (path.startsWith("projects/archived"))
              return page(new JSONArray().put(archived), JSONObject.NULL);
            if (path.startsWith("projects?"))
              return page(new JSONArray().put(root), JSONObject.NULL);
            if (path.startsWith("activities"))
              return page(new JSONArray().put(reopened), JSONObject.NULL);
            return super.get(path);
          }
        };
    JSONObject next = new TodoistClient(fake, CLOCK, message -> {}).snapshot(before, false);
    assertEquals("", TodoistClient.parentId(next.getJSONArray("knownProjects").getJSONObject(1)));
    assertEquals("root", previousChild.getString("parent_id"));
    archived.put("parent_id", "root");
    JSONObject authoritative =
        new TodoistClient(fake, CLOCK, message -> {}).snapshot(before, false);
    assertEquals(
        "root",
        TodoistClient.parentId(authoritative.getJSONArray("knownProjects").getJSONObject(1)));
  }
}
