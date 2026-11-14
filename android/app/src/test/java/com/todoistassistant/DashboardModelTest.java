package com.todoistassistant;

import static org.junit.Assert.*;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public class DashboardModelTest {
  private static final Clock CLOCK =
      Clock.fixed(Instant.parse("2026-11-01T12:00:00Z"), ZoneId.of("Europe/Warsaw"));

  private JSONObject empty() throws Exception {
    return new JSONObject()
        .put("projects", new JSONArray())
        .put("tasks", new JSONArray())
        .put("activities", new JSONArray())
        .put("syncedAt", CLOCK.instant().toString())
        .put("historyStart", "2026-08-01T00:00:00Z");
  }

  private JSONObject task(String id, String project, String name, int priority) throws Exception {
    return new JSONObject()
        .put("id", id)
        .put("project_id", project)
        .put("content", name)
        .put("priority", priority);
  }

  @Test
  public void habitsMatchBackendCompletionAndRescheduleFixture() throws Exception {
    java.nio.file.Path fixturePath =
        java.nio.file.Paths.get(System.getProperty("completionFixtures"))
            .getParent()
            .resolve("android_habit_conformance.json");
    JSONObject fixture =
        new JSONObject(
            new String(
                java.nio.file.Files.readAllBytes(fixturePath),
                java.nio.charset.StandardCharsets.UTF_8));
    Clock anchor = Clock.fixed(Instant.parse(fixture.getString("anchor")), ZoneId.of("UTC"));
    JSONObject project = new JSONObject().put("id", "p").put("name", "Health");
    JSONObject one =
        task("h1", "p", "Walking", 1).put("labels", new JSONArray().put(" @TRACK_HABIT "));
    JSONObject two =
        task("h2", "p", "Reading", 1).put("labels", new JSONArray().put("track_habit"));
    JSONObject data =
        empty()
            .put("syncedAt", anchor.instant().toString())
            .put("projects", new JSONArray().put(project))
            .put("tasks", new JSONArray().put(one).put(two))
            .put("activities", fixture.getJSONArray("events"));
    JSONObject actual = new DashboardModel(data, anchor).habitTracker;
    JSONObject expected = fixture.getJSONObject("expected");
    assertEquals(expected.getString("weekBeg"), actual.getString("weekBeg"));
    assertEquals(expected.getString("weekEnd"), actual.getString("weekEnd"));
    assertEquals(expected.getInt("trackedCount"), actual.getInt("trackedCount"));
    for (var keys = expected.getJSONObject("totals").keys(); keys.hasNext(); ) {
      String key = keys.next();
      assertEquals(
          key,
          expected.getJSONObject("totals").getInt(key),
          actual.getJSONObject("totals").getInt(key));
    }
    for (int i = 0; i < expected.getJSONArray("items").length(); i++) {
      JSONObject want = expected.getJSONArray("items").getJSONObject(i);
      JSONObject got = actual.getJSONArray("items").getJSONObject(i);
      for (var keys = want.keys(); keys.hasNext(); ) {
        String key = keys.next();
        if (want.get(key) instanceof Number)
          assertEquals(key, want.getDouble(key), got.getDouble(key), 0.00001);
        else assertEquals(key, want.get(key), got.get(key));
      }
    }
  }

  @Test
  public void habitWeekBoundaryUsesDeviceLocalDateAcrossDst() throws Exception {
    ZoneId zone = ZoneId.of("Europe/Warsaw");
    Clock monday = Clock.fixed(Instant.parse("2026-03-30T10:00:00Z"), zone);
    JSONObject tracked =
        task("h", "p", "Habit", 1).put("labels", new JSONArray().put("track_habit"));
    JSONArray events = new JSONArray();
    for (String[] value :
        new String[][] {{"one", "2026-03-29T21:30:00Z"}, {"two", "2026-03-29T22:30:00Z"}})
      events.put(
          new JSONObject()
              .put("id", value[0])
              .put("object_id", "h")
              .put("object_type", "item")
              .put("event_type", "completed")
              .put("event_date", value[1])
              .put("extra_data", new JSONObject().put("is_recurring", true)));
    JSONObject data =
        empty()
            .put("syncedAt", monday.instant().toString())
            .put("tasks", new JSONArray().put(tracked))
            .put("activities", events);
    JSONObject habit = new DashboardModel(data, monday).habitTracker;
    assertEquals("2026-03-23", habit.getString("weekBeg"));
    assertEquals("2026-03-29", habit.getString("weekEnd"));
    assertEquals(1, habit.getJSONObject("totals").getInt("weeklyCompleted"));
    assertEquals(2, habit.getJSONObject("totals").getInt("allTimeCompleted"));
  }

  @Test
  public void activityTotalCountsUniqueEventsBeyondTheVisibleLimit() throws Exception {
    JSONArray events = new JSONArray();
    for (int i = 0; i < 205; i++)
      events.put(
          new JSONObject()
              .put("id", "e" + i)
              .put("object_id", "t" + i)
              .put("object_type", "item")
              .put("event_type", "added")
              .put("event_date", "2026-10-31T10:00:00Z"));
    events.put(events.getJSONObject(0));
    DashboardModel model = new DashboardModel(empty().put("activities", events), CLOCK);
    assertEquals(205, model.activityTotal);
    assertEquals(200, model.recent.size());
    assertEquals(205, MobilePayload.model(model).getInt("activityTotal"));
  }

  @Test
  public void habitReliabilityUsesBackendFloatingPointRounding() throws Exception {
    JSONObject tracked =
        task("h", "p", "Habit", 1).put("labels", new JSONArray().put("track_habit"));
    JSONArray events = new JSONArray();
    for (int i = 0; i < 160; i++) {
      JSONObject extra =
          i < 23
              ? new JSONObject().put("is_recurring", true)
              : new JSONObject().put("due_date", "2026-10-30").put("last_due_date", "2026-10-29");
      events.put(
          new JSONObject()
              .put("id", "e" + i)
              .put("object_id", "h")
              .put("object_type", "item")
              .put("event_type", i < 23 ? "completed" : "updated")
              .put("event_date", "2026-10-29T10:00:00Z")
              .put("extra_data", extra));
    }
    DashboardModel model =
        new DashboardModel(
            empty().put("tasks", new JSONArray().put(tracked)).put("activities", events), CLOCK);
    assertEquals(
        14.37,
        model.habitTracker.getJSONArray("items").getJSONObject(0).getDouble("reliability"),
        0.00001);
  }

  @Test
  public void projectsMissingDuringSyncDoNotHideTheirTasks() throws Exception {
    JSONObject data = empty().put("tasks", new JSONArray().put(task("t", "missing", "Task", 4)));
    DashboardModel model = new DashboardModel(data, CLOCK);
    assertEquals(1, model.tasks.size());
    assertEquals(1, model.projects.size());
    assertEquals("Unknown project", model.projects.get(0).path);
  }

  @Test
  public void checkedAndDeletedTasksAreExcludedFromActiveCounts() throws Exception {
    JSONObject data =
        empty()
            .put(
                "tasks",
                new JSONArray()
                    .put(task("a", "p", "Active", 3))
                    .put(task("b", "p", "Checked", 4).put("checked", true))
                    .put(task("c", "p", "Deleted", 4).put("is_deleted", true)));
    DashboardModel model = new DashboardModel(data, CLOCK);
    assertEquals(1, model.tasks.size());
    assertEquals(0, model.priorities[0]);
    assertEquals(1, model.priorities[1]);
  }

  @Test
  public void cyclicProjectTreesDoNotHang() throws Exception {
    JSONObject a = new JSONObject().put("id", "a").put("name", "A").put("parent_id", "b");
    JSONObject b = new JSONObject().put("id", "b").put("name", "B").put("parent_id", "a");
    assertEquals("B / A", DashboardModel.projectPath("a", Map.of("a", a, "b", b)));
  }

  @Test
  public void timestampDatesUseTheDeviceZone() {
    assertEquals(
        LocalDate.of(2026, 11, 2),
        DashboardModel.localDate("2026-11-01T23:30:00Z", ZoneId.of("Europe/Warsaw")));
    assertNull(DashboardModel.localDate("bad", ZoneId.of("UTC")));
  }

  @Test
  public void dueDatesKeepTheirCalendarDayWhileCompletionsUseDeviceTime() throws Exception {
    ZoneId zone = ZoneId.of("America/Los_Angeles");
    Clock monday = Clock.fixed(Instant.parse("2026-11-02T09:00:00Z"), zone);
    JSONObject futureDue =
        task("future", "p", "Future due", 1)
            .put("due", new JSONObject().put("date", "2026-11-03T00:30:00+14:00"));
    JSONObject todayDue =
        task("today", "p", "Today due", 1)
            .put("due", new JSONObject().put("date", "2026-11-02T23:30:00-10:00"));
    JSONObject invalidDue =
        task("invalid", "p", "Invalid due", 1)
            .put("due", new JSONObject().put("date", "2026-11-02garbage"));
    JSONObject event =
        new JSONObject()
            .put("id", "e")
            .put("object_id", "done")
            .put("object_type", "item")
            .put("event_type", "completed")
            .put("event_date", "2026-11-01T10:30:00Z");
    JSONObject data =
        empty()
            .put("syncedAt", monday.instant().toString())
            .put("tasks", new JSONArray().put(futureDue).put(todayDue).put(invalidDue))
            .put("activities", new JSONArray().put(event));
    DashboardModel model = new DashboardModel(data, monday);
    assertEquals(zone, model.zoneId);
    assertEquals(LocalDate.of(2026, 11, 2), model.renderedOn);
    AlertRules rules = new AlertRules();
    assertEquals(1, rules.evaluate(model.tasks, LocalDate.of(2026, 11, 2), zone).due);
    assertEquals(1, model.weeks[model.weeks.length - 2]);
    assertEquals(0, model.weeks[model.weeks.length - 1]);
  }

  @Test
  public void duplicateActivityIdentifiersUseTheLastRecordForEveryProjection() throws Exception {
    JSONObject first =
        new JSONObject()
            .put("id", "e")
            .put("object_id", "done")
            .put("object_type", "item")
            .put("event_type", "completed")
            .put("event_date", "2026-10-20T08:00:00Z");
    JSONObject last = new JSONObject(first.toString()).put("event_date", "2026-10-30T08:00:00Z");
    DashboardModel model =
        new DashboardModel(empty().put("activities", new JSONArray().put(first).put(last)), CLOCK);
    assertEquals(1, model.recent.size());
    assertEquals(Instant.parse("2026-10-30T08:00:00Z"), model.recent.get(0).date);
    assertEquals(1, java.util.Arrays.stream(model.weeks).sum());
    JSONArray days = model.plotData.getJSONArray("dailyActivity");
    assertEquals(1, days.length());
    assertEquals("2026-10-30", days.getJSONObject(0).getString("date"));
    assertEquals(1, days.getJSONObject(0).getJSONObject("counts").getInt("completed"));
    assertEquals(1, days.getJSONObject(0).getInt("effectiveCompletions"));
  }

  @Test
  public void activitySyncBoundaryIsExclusiveButLegacyFallbackRemainsInclusive() throws Exception {
    String cutoff = "2026-11-01T12:00:00Z";
    JSONArray events = new JSONArray();
    for (int i = -1; i <= 1; i++) {
      events.put(
          new JSONObject()
              .put("id", "e" + i)
              .put("object_id", "t" + i)
              .put("object_type", "item")
              .put("event_type", "completed")
              .put("event_date", Instant.parse(cutoff).plusSeconds(i).toString()));
    }
    JSONObject data = empty().put("activities", events).put("activitySyncedAt", cutoff);
    DashboardModel explicit = new DashboardModel(data, CLOCK);
    assertTrue(explicit.activitySyncExclusive);
    assertEquals(Instant.parse(cutoff), explicit.activitySyncedAt);
    assertEquals(1, explicit.recent.size());
    assertEquals(1, java.util.Arrays.stream(explicit.weeks).sum());
    assertEquals(
        1,
        explicit
            .plotData
            .getJSONArray("dailyActivity")
            .getJSONObject(0)
            .getInt("effectiveCompletions"));
    data.remove("activitySyncedAt");
    DashboardModel legacy = new DashboardModel(data, CLOCK);
    assertFalse(legacy.activitySyncExclusive);
    assertEquals(legacy.syncedAt, legacy.activitySyncedAt);
    assertEquals(2, legacy.recent.size());
    assertEquals(2, java.util.Arrays.stream(legacy.weeks).sum());
  }

  @Test
  public void staleActivityDoesNotOfferAFreshForecastWithinTheSameWeek() throws Exception {
    Clock wednesday = Clock.fixed(Instant.parse("2026-10-28T12:00:00Z"), CLOCK.getZone());
    JSONObject event =
        new JSONObject()
            .put("id", "e")
            .put("object_id", "t")
            .put("object_type", "item")
            .put("event_type", "completed")
            .put("event_date", "2026-10-27T08:00:00Z");
    JSONObject data =
        empty()
            .put("syncedAt", wednesday.instant().toString())
            .put("activitySyncedAt", "2026-10-27T12:00:00Z")
            .put("activities", new JSONArray().put(event));
    DashboardModel stale = new DashboardModel(data, wednesday);
    assertFalse(stale.forecastAvailable);
    assertEquals(Instant.parse("2026-10-27T12:00:00Z"), stale.activitySyncedAt);
    data.put("activitySyncedAt", wednesday.instant().toString());
    assertTrue(new DashboardModel(data, wednesday).forecastAvailable);
    data.remove("activitySyncedAt");
    assertTrue(new DashboardModel(data, wednesday).forecastAvailable);
  }

  @Test
  public void emptyAccountHasNoInventedForecast() throws Exception {
    DashboardModel model = new DashboardModel(empty().put("historyComplete", true), CLOCK);
    assertEquals(0, model.tasks.size());
    assertEquals(0, java.util.Arrays.stream(model.weeks).sum());
    assertEquals(0, model.recent.size());
    assertFalse(model.forecastAvailable);
    assertEquals(0, model.plotData.getJSONArray("dailyActivity").length());
    assertEquals(0, model.plotData.getJSONArray("taskCounts").getJSONObject(0).getInt("total"));
  }

  @Test
  public void largeAccountKeepsProjectAndCompletionTotalsConsistent() throws Exception {
    JSONArray active = new JSONArray(),
        known = new JSONArray(),
        tasks = new JSONArray(),
        events = new JSONArray();
    for (int i = 0; i < 400; i++) {
      String id = "project-" + i;
      JSONObject project = new JSONObject().put("id", id).put("name", "Project " + i);
      if (i < 200) {
        active.put(project);
        tasks.put(task("task-" + i, id, "Task " + i, i % 4 + 1));
      } else {
        project.put("is_archived", true);
      }
      known.put(project);
      events.put(
          new JSONObject()
              .put("id", "event-" + i)
              .put("object_id", "done-" + i)
              .put("object_type", "item")
              .put("event_type", "completed")
              .put("parent_project_id", id)
              .put("event_date", "2026-10-30T08:00:00Z"));
    }
    JSONObject data =
        empty()
            .put("historyComplete", true)
            .put("projects", active)
            .put("knownProjects", known)
            .put("tasks", tasks)
            .put("activities", events);
    DashboardModel model = new DashboardModel(data, CLOCK);
    assertEquals(200, model.tasks.size());
    assertEquals(400, java.util.Arrays.stream(model.weeks).sum());
    assertEquals(
        400,
        model.weeklyProjects.get(model.weeks.length - 1).values().stream()
            .mapToInt(Integer::intValue)
            .sum());
    assertEquals(400, model.plotData.getJSONArray("hierarchy").length());
    JSONObject day = model.plotData.getJSONArray("dailyActivity").getJSONObject(0);
    assertEquals(400, day.getInt("effectiveCompletions"));
    assertEquals(400, day.getJSONObject("counts").getInt("completed"));
    assertEquals(400, day.getJSONObject("projects").length());
  }

  @Test
  public void largeHistoryKeepsArchivedAssignmentsAndTotalsConsistent() throws Exception {
    JSONArray active = new JSONArray(), known = new JSONArray(), tasks = new JSONArray();
    JSONArray events = new JSONArray(), promoted = new JSONArray();
    JSONObject mappings = new JSONObject();
    Map<String, Integer> expected = new java.util.HashMap<>();
    for (int i = 0; i < 5; i++) {
      JSONObject project = new JSONObject().put("id", "root-" + i).put("name", "Group " + i);
      active.put(project);
      known.put(project);
    }
    for (int i = 0; i < 106; i++) {
      String name = "Archived " + i;
      known.put(
          new JSONObject().put("id", "archive-" + i).put("name", name).put("is_archived", true));
      if (i < 104) mappings.put(name, "Group " + (i % 5));
      if (i < 3) promoted.put(name);
    }
    for (int i = 0; i < 2154; i++) tasks.put(task("open-" + i, "root-" + (i % 5), "Open " + i, 1));
    for (int i = 0; i < 65221; i++) {
      int project = i % 106;
      boolean completed = i % 5 == (i / 106) % 5;
      events.put(
          new JSONObject()
              .put("id", "event-" + i)
              .put("object_id", "task-" + i)
              .put("object_type", "item")
              .put("event_type", completed ? "completed" : "updated")
              .put("parent_project_id", "archive-" + project)
              .put("event_date", "2026-11-01T10:00:00Z"));
      if (completed) {
        String group =
            project < 3 || project >= 104 ? "Archived " + project : "Group " + (project % 5);
        expected.merge(group, 1, Integer::sum);
      }
    }
    DashboardModel model =
        new DashboardModel(
            empty()
                .put("projects", active)
                .put("knownProjects", known)
                .put("tasks", tasks)
                .put("activities", events)
                .put(
                    "adjustments",
                    new JSONObject().put("mappings", mappings).put("archivedParents", promoted)),
            CLOCK);
    int total = expected.values().stream().mapToInt(Integer::intValue).sum();
    assertEquals(2154, model.tasks.size());
    assertEquals(65221, model.activityTotal);
    assertEquals(200, model.recent.size());
    assertEquals(total, model.weeks[model.weeks.length - 1]);
    assertEquals(expected, model.weeklyProjects.get(model.weeklyProjects.size() - 1));
    assertEquals(
        total,
        model
            .plotData
            .getJSONArray("dailyActivity")
            .getJSONObject(0)
            .getInt("effectiveCompletions"));
  }

  @Test
  public void fireMatchesWholeLabelsInsteadOfFireworks() throws Exception {
    JSONObject data =
        empty()
            .put(
                "tasks",
                new JSONArray()
                    .put(task("a", "p", "A", 1).put("labels", new JSONArray().put("fireworks")))
                    .put(task("b", "p", "B", 1).put("labels", new JSONArray().put(" FIRE "))));
    DashboardModel model = new DashboardModel(data, CLOCK);
    AlertRules rules = new AlertRules();
    rules.priority = rules.due = rules.deadline = false;
    assertEquals(1, rules.evaluate(model.tasks, LocalDate.now(CLOCK), CLOCK.getZone()).fire);
  }

  @Test
  public void undatedTasksDoNotTriggerDateAlertsInLargeAccounts() throws Exception {
    var tasks = new java.util.ArrayList<DashboardModel.Task>();
    for (int i = 0; i < 5000; i++)
      tasks.add(new DashboardModel.Task(task("t" + i, "p", "Undated", 1), "Project"));
    tasks.add(
        new DashboardModel.Task(
            task("dated", "p", "Due", 1).put("due", new JSONObject().put("date", "2026-11-01")),
            "Project"));
    AlertRules rules = new AlertRules();
    rules.fire = rules.priority = false;
    var status = rules.evaluate(tasks, LocalDate.now(CLOCK), CLOCK.getZone());
    assertEquals(1, status.due);
    assertEquals(0, status.deadline);
    assertEquals(1, status.matches);
  }

  @Test
  public void upcomingWindowStillIncludesOverdueTasks() throws Exception {
    JSONObject data =
        empty()
            .put(
                "tasks",
                new JSONArray()
                    .put(
                        task("a", "p", "Overdue", 1)
                            .put("due", new JSONObject().put("date", "2026-10-01"))));
    DashboardModel model = new DashboardModel(data, CLOCK);
    AlertRules rules = new AlertRules();
    rules.dueDays = 3;
    assertEquals(1, rules.evaluate(model.tasks, LocalDate.now(CLOCK), CLOCK.getZone()).due);
  }

  @Test
  public void emptyPriorityAndFireSelectionsSurviveSaving() throws Exception {
    AlertRules rules = new AlertRules();
    rules.priorities.clear();
    rules.fireLabels = "";
    AlertRules loaded = AlertRules.read(rules.json());
    assertTrue(loaded.priorities.isEmpty());
    assertEquals("", loaded.fireLabels);
  }

  @Test
  public void demoHasConsistentWeeklyProjectTotals() throws Exception {
    JSONObject demo = DemoData.create(CLOCK);
    DashboardModel model = new DashboardModel(demo, CLOCK);
    assertEquals(40, model.tasks.size());
    assertEquals(
        model.weeks[8],
        model.weeklyProjects.get(8).values().stream().mapToInt(Integer::intValue).sum());
    assertTrue(model.forecast >= model.weeks[8]);
    int completionActions = 0;
    for (int i = 0; i < demo.getJSONArray("activities").length(); i++)
      if (demo.getJSONArray("activities")
          .getJSONObject(i)
          .optString("event_type")
          .equals("completed")) completionActions++;
    assertEquals(completionActions - 1, java.util.Arrays.stream(model.weeks).sum());
    JSONObject payload = MobilePayload.model(model);
    assertEquals(40, payload.getJSONArray("tasks").length());
    assertEquals(model.weeks[8], payload.getJSONArray("weeks").getInt(8));
    int estimate = 0;
    JSONObject forecasts = payload.getJSONObject("projectForecasts");
    for (var keys = forecasts.keys(); keys.hasNext(); ) estimate += forecasts.getInt(keys.next());
    assertEquals(payload.getInt("forecast"), estimate);
  }

  @Test
  public void historicalWeeksRemainVisibleWithoutChangingCurrentWeekOrForecast() throws Exception {
    JSONObject project = new JSONObject().put("id", "p").put("name", "Work");
    JSONObject recent =
        new JSONObject()
            .put("id", "recent")
            .put("object_id", "recent-task")
            .put("object_type", "item")
            .put("event_type", "completed")
            .put("parent_project_id", "p")
            .put("event_date", "2026-10-30T10:00:00Z");
    JSONObject old =
        new JSONObject(recent.toString())
            .put("id", "old")
            .put("object_id", "old-task")
            .put("event_date", "2024-02-01T10:00:00Z");
    JSONObject data = empty().put("projects", new JSONArray().put(project));
    DashboardModel recentOnly =
        new DashboardModel(data.put("activities", new JSONArray().put(recent)), CLOCK);
    DashboardModel full =
        new DashboardModel(data.put("activities", new JSONArray().put(old).put(recent)), CLOCK);
    assertTrue(full.weeks.length > 100);
    assertEquals(1, full.weeks[0]);
    assertEquals(1, full.weeklyProjects.get(0).get("Work").intValue());
    assertEquals(recentOnly.weeks[8], full.weeks[full.weeks.length - 1]);
    assertEquals(recentOnly.forecast, full.forecast);
  }

  @Test
  public void archivedRootsKeepActualCountsWithoutForecastingMoreWork() throws Exception {
    Clock wednesday = Clock.fixed(Instant.parse("2026-10-28T12:00:00Z"), CLOCK.getZone());
    JSONObject project = new JSONObject().put("id", "p").put("name", "Shipped");
    JSONArray events = new JSONArray();
    for (int i = 0; i < 15; i++) {
      events.put(
          new JSONObject()
              .put("id", "e" + i)
              .put("object_id", "t" + i)
              .put("object_type", "item")
              .put("event_type", "completed")
              .put("parent_project_id", "p")
              .put("event_date", i == 0 ? "2026-10-26T10:00:00Z" : "2026-10-20T10:00:00Z"));
    }
    JSONObject data =
        empty()
            .put("syncedAt", wednesday.instant().toString())
            .put("activities", events)
            .put("projects", new JSONArray().put(project));
    assertTrue(new DashboardModel(data, wednesday).forecast > 1);
    data.put("projects", new JSONArray())
        .put("knownProjects", new JSONArray().put(project.put("is_archived", true)));
    DashboardModel archived = new DashboardModel(data, wednesday);
    assertEquals(1, archived.weeks[8]);
    assertEquals(1, archived.forecast);
    assertEquals(1, archived.weeklyProjects.get(8).get("Shipped").intValue());
  }

  @Test
  public void importedAdjustmentsGroupArchivedCompletionsAndHonorPromotedParents()
      throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Work").put("color", "blue");
    JSONObject child =
        new JSONObject().put("id", "old").put("name", "Old").put("is_archived", true);
    JSONObject event =
        new JSONObject()
            .put("id", "e")
            .put("object_id", "t")
            .put("object_type", "item")
            .put("event_type", "completed")
            .put("event_date", "2026-11-01T10:00:00Z")
            .put("parent_project_id", "old");
    JSONObject data =
        empty()
            .put("projects", new JSONArray().put(root))
            .put("knownProjects", new JSONArray().put(root).put(child))
            .put("activities", new JSONArray().put(event))
            .put(
                "adjustments",
                new JSONObject()
                    .put("mappings", new JSONObject().put("Old", "Work"))
                    .put("archivedParents", new JSONArray()));
    DashboardModel grouped = new DashboardModel(data, CLOCK);
    assertEquals(1, grouped.weeklyProjects.get(8).get("Work").intValue());
    assertEquals("blue", grouped.projectColors.get("Work"));
    data.getJSONObject("adjustments").put("archivedParents", new JSONArray().put("Old"));
    assertEquals(1, new DashboardModel(data, CLOCK).weeklyProjects.get(8).get("Old").intValue());
  }

  @Test
  public void archivedMappingToSubprojectUsesItsActualRoot() throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Work");
    JSONObject team =
        new JSONObject().put("id", "team").put("name", "Team").put("parent_id", "root");
    JSONObject archived =
        new JSONObject().put("id", "old").put("name", "Old").put("is_archived", true);
    JSONObject event =
        new JSONObject()
            .put("id", "event")
            .put("object_id", "task")
            .put("object_type", "item")
            .put("event_type", "completed")
            .put("event_date", "2026-11-01T10:00:00Z")
            .put("parent_project_id", "old");
    JSONObject data =
        empty()
            .put("projects", new JSONArray().put(root).put(team))
            .put("knownProjects", new JSONArray().put(root).put(team).put(archived))
            .put("activities", new JSONArray().put(event))
            .put(
                "adjustments",
                new JSONObject().put("mappings", new JSONObject().put("Old", "Team")));
    DashboardModel model = new DashboardModel(data, CLOCK);
    assertEquals(1, model.weeklyProjects.get(8).get("Work").intValue());
    assertFalse(model.weeklyProjects.get(8).containsKey("Team"));
    JSONArray hierarchy = model.plotData.getJSONArray("hierarchy");
    for (int i = 0; i < hierarchy.length(); i++) {
      JSONObject row = hierarchy.getJSONObject(i);
      if (row.getString("id").equals("old")) {
        assertEquals("Work", row.getString("rootName"));
        return;
      }
    }
    fail("Archived project is missing from the timeline");
  }

  @Test
  public void historicalActivityCanUseKnownModernProjectId() throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Work");
    JSONObject child =
        new JSONObject()
            .put("id", "modern")
            .put("name", "Old")
            .put("parent_id", "root")
            .put("is_archived", true);
    JSONObject event =
        new JSONObject()
            .put("id", "event")
            .put("object_id", "task")
            .put("object_type", "item")
            .put("event_type", "completed")
            .put("event_date", "2026-11-01T10:00:00Z")
            .put("parent_project_id", "legacy")
            .put("v2_parent_project_id", "modern");
    DashboardModel model =
        new DashboardModel(
            empty()
                .put("projects", new JSONArray().put(root))
                .put("knownProjects", new JSONArray().put(root).put(child))
                .put("activities", new JSONArray().put(event)),
            CLOCK);
    assertEquals(1, model.weeklyProjects.get(8).get("Work").intValue());
    assertEquals("Work / Old", model.recent.get(0).project);
    JSONArray hierarchy = model.plotData.getJSONArray("hierarchy");
    for (int i = 0; i < hierarchy.length(); i++) {
      JSONObject row = hierarchy.getJSONObject(i);
      if (row.getString("id").equals("modern")) {
        assertEquals(1, row.getJSONArray("dailyCompletions").getJSONObject(0).getInt("count"));
        return;
      }
    }
    fail("Historical project is missing from the timeline");
  }

  @Test
  public void projectTimelineIncludesUniquePreviousNamesFromMatchingHistory() throws Exception {
    JSONObject renamed =
        new JSONObject().put("id", "modern").put("name", "Current").put("is_archived", true);
    JSONObject other =
        new JSONObject().put("id", "other").put("name", "Other").put("is_archived", true);
    JSONArray events = new JSONArray();
    for (int i = 0; i < 4; i++) {
      Object oldName = i == 2 ? 42 : i == 3 ? "Current" : "Former name";
      events.put(
          new JSONObject()
              .put("id", "rename-" + i)
              .put("object_type", "project")
              .put("object_id", "legacy")
              .put("v2_object_id", "modern")
              .put("event_type", "updated")
              .put("event_date", "2026-11-01T10:00:00Z")
              .put("extra_data", new JSONObject().put("last_name", oldName)));
    }
    events.put(
        new JSONObject()
            .put("id", "other-event")
            .put("object_type", "project")
            .put("object_id", "other")
            .put("event_type", "updated")
            .put("event_date", "2026-11-01T10:00:00Z")
            .put("extra_data", new JSONObject().put("last_name", "Other history")));
    DashboardModel model =
        new DashboardModel(
            empty()
                .put("knownProjects", new JSONArray().put(renamed).put(other))
                .put("activities", events),
            CLOCK);
    JSONArray rows = model.plotData.getJSONArray("hierarchy");
    int checked = 0;
    for (int i = 0; i < rows.length(); i++) {
      JSONObject row = rows.getJSONObject(i);
      if (row.getString("id").equals("modern")) {
        assertEquals(1, row.getJSONArray("previousNames").length());
        assertEquals("Former name", row.getJSONArray("previousNames").getString(0));
        checked++;
      } else if (row.getString("id").equals("other")) {
        assertEquals("Other history", row.getJSONArray("previousNames").getString(0));
        checked++;
      }
    }
    assertEquals(2, checked);
  }

  @Test
  public void importedMappingsRespectPromotedParentsAmbiguityAndCycles() throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Work");
    JSONObject team =
        new JSONObject().put("id", "team").put("name", "Team").put("parent_id", "root");
    JSONObject promoted =
        new JSONObject()
            .put("id", "p")
            .put("name", "Promoted")
            .put("is_archived", true)
            .put("parent_id", "root");
    JSONObject child =
        new JSONObject()
            .put("id", "child")
            .put("name", "Old")
            .put("parent_id", "p")
            .put("is_archived", true);
    Map<String, JSONObject> projects =
        new java.util.LinkedHashMap<>(
            Map.of("root", root, "team", team, "p", promoted, "child", child));
    JSONObject mappings = new JSONObject().put("Old", "Team").put("Promoted", "Work");
    assertEquals(
        "Promoted",
        DashboardModel.rootName(
            "child", projects, mappings, new JSONObject(), java.util.Set.of("Promoted")));
    assertEquals(
        "Work",
        DashboardModel.rootName("child", projects, mappings, new JSONObject(), java.util.Set.of()));
    JSONObject another =
        new JSONObject().put("id", "other").put("name", "Team").put("parent_id", "another-root");
    projects.put("other", another);
    assertEquals(
        "Team",
        DashboardModel.rootName("child", projects, mappings, new JSONObject(), java.util.Set.of()));
    JSONObject one = new JSONObject().put("id", "one").put("name", "One").put("is_archived", true);
    JSONObject two = new JSONObject().put("id", "two").put("name", "Two").put("is_archived", true);
    assertEquals(
        "One",
        DashboardModel.rootName(
            "one",
            Map.of("one", one, "two", two),
            new JSONObject().put("One", "Two").put("Two", "One"),
            new JSONObject(),
            java.util.Set.of()));
    assertEquals(
        "One",
        DashboardModel.rootName(
            "one",
            Map.of("one", one),
            new JSONObject().put("One", "One"),
            new JSONObject(),
            java.util.Set.of()));
    one.put("parent_id", "root");
    assertEquals(
        "Work",
        DashboardModel.rootName(
            "one",
            Map.of("one", one, "root", root),
            new JSONObject().put("One", "One"),
            new JSONObject(),
            java.util.Set.of()));
  }

  @Test
  public void explicitProjectIdsDisambiguateNamesAndFollowMappedAncestors() throws Exception {
    JSONObject first =
        new JSONObject().put("id", "first").put("name", "Duplicate").put("is_archived", true);
    JSONObject second =
        new JSONObject().put("id", "second").put("name", "Duplicate").put("is_archived", true);
    JSONObject child =
        new JSONObject()
            .put("id", "child")
            .put("name", "Nested")
            .put("parent_id", "first")
            .put("is_archived", true);
    JSONObject target =
        new JSONObject().put("id", "target").put("name", "Renamed target").put("is_archived", true);
    JSONObject root = new JSONObject().put("id", "root").put("name", "Current root");
    target.put("parent_id", "root");
    Map<String, JSONObject> projects =
        new java.util.LinkedHashMap<>(
            Map.of(
                "first", first, "second", second, "child", child, "target", target, "root", root));
    JSONObject ids =
        new JSONObject()
            .put(
                "first",
                new JSONObject().put("targetId", "target").put("targetName", "Old target name"))
            .put(
                "second",
                new JSONObject().put("targetId", "second").put("targetName", "Duplicate"));
    JSONObject legacy = new JSONObject().put("Duplicate", "Wrong legacy root");
    assertEquals(
        "Current root",
        DashboardModel.rootName("first", projects, legacy, ids, java.util.Set.of("Duplicate")));
    assertEquals(
        "Current root",
        DashboardModel.rootName("child", projects, legacy, ids, java.util.Set.of("Duplicate")));
    assertEquals(
        "Duplicate · second",
        DashboardModel.rootName("second", projects, legacy, ids, java.util.Set.of()));

    ids.getJSONObject("first").put("targetId", "first");
    assertEquals(
        "Duplicate · first",
        DashboardModel.rootName("first", projects, legacy, ids, java.util.Set.of()));
    assertEquals(
        "Duplicate · first",
        DashboardModel.rootName("child", projects, legacy, ids, java.util.Set.of()));

    ids.getJSONObject("first").put("targetId", "missing");
    projects.put("other", new JSONObject().put("id", "other").put("name", "Old target name"));
    assertEquals(
        "Old target name · missing",
        DashboardModel.rootName("first", projects, legacy, ids, java.util.Set.of()));
    ids.getJSONObject("first").put("targetId", "second");
    ids.getJSONObject("second").put("targetId", "first");
    assertEquals(
        "Duplicate · first",
        DashboardModel.rootName("first", projects, legacy, ids, java.util.Set.of()));
  }

  @Test
  public void closerLegacyChoiceOverridesInheritedIdMappingWithoutChangingOldRules()
      throws Exception {
    JSONObject child =
        new JSONObject()
            .put("id", "child")
            .put("name", "Child")
            .put("is_archived", true)
            .put("parent_id", "parent");
    JSONObject parent =
        new JSONObject().put("id", "parent").put("name", "Parent").put("is_archived", true);
    JSONObject mapped = new JSONObject().put("id", "mapped").put("name", "Mapped root");
    JSONObject legacyRoot = new JSONObject().put("id", "legacy").put("name", "Legacy root");
    Map<String, JSONObject> projects =
        Map.of("child", child, "parent", parent, "mapped", mapped, "legacy", legacyRoot);
    JSONObject names = new JSONObject().put("Child", "Legacy root");
    JSONObject ids =
        new JSONObject()
            .put(
                "parent",
                new JSONObject().put("targetId", "mapped").put("targetName", "Mapped root"));
    assertEquals(
        "Legacy root", DashboardModel.rootName("child", projects, names, ids, java.util.Set.of()));
    assertEquals(
        "Child", DashboardModel.rootName("child", projects, names, ids, java.util.Set.of("Child")));
    assertEquals(
        "Parent",
        DashboardModel.rootName(
            "child", projects, names, new JSONObject(), java.util.Set.of("Parent")));
    ids.put("child", new JSONObject().put("targetId", "mapped").put("targetName", "Mapped root"));
    assertEquals(
        "Mapped root",
        DashboardModel.rootName("child", projects, names, ids, java.util.Set.of("Child")));
  }

  @Test
  public void projectIdMappingsSurviveImportMergeAndPayload() throws Exception {
    JSONObject ids =
        new JSONObject()
            .put("one", new JSONObject().put("targetId", "root").put("targetName", "Root"));
    JSONObject existing =
        new JSONObject()
            .put("mappings", new JSONObject())
            .put("archivedParents", new JSONArray())
            .put("projectMappings", ids);
    JSONObject legacy =
        ProjectAdjustments.parse(
            "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{},\"archivedParents\":[]}");
    JSONObject merged = ProjectAdjustments.merge(existing, legacy);
    ids.getJSONObject("one").put("targetName", "Changed");
    assertEquals(
        "Root",
        merged.getJSONObject("projectMappings").getJSONObject("one").getString("targetName"));
    DashboardModel model = new DashboardModel(empty().put("adjustments", merged), CLOCK);
    assertEquals(
        "Root",
        MobilePayload.model(model)
            .getJSONObject("adjustments")
            .getJSONObject("projectMappings")
            .getJSONObject("one")
            .getString("targetName"));
    JSONObject incoming =
        ProjectAdjustments.parse(
            "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{},\"archivedParents\":[],\"projectMappings\":{\"one\":{\"targetId\":\"new-root\",\"targetName\":\"New root\"},\"two\":{\"targetId\":\"two\",\"targetName\":\"Own group\"}}}");
    JSONObject updated = ProjectAdjustments.merge(merged, incoming);
    incoming.getJSONObject("projectMappings").getJSONObject("one").put("targetName", "Mutated");
    assertEquals(
        "New root",
        updated.getJSONObject("projectMappings").getJSONObject("one").getString("targetName"));
    assertEquals(
        "two", updated.getJSONObject("projectMappings").getJSONObject("two").getString("targetId"));
    assertEquals(
        "Root",
        merged.getJSONObject("projectMappings").getJSONObject("one").getString("targetName"));
    try {
      ProjectAdjustments.parse(
          "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{},\"archivedParents\":[],\"projectMappings\":{\"one\":{\"targetId\":\"root\"}}}");
      fail("Expected invalid project ID mapping to be rejected");
    } catch (IllegalArgumentException expected) {
      assertEquals("Invalid project mapping", expected.getMessage());
    }
  }

  @Test
  public void importRejectsFilesThatAreNotProjectAdjustments() throws Exception {
    JSONObject valid =
        ProjectAdjustments.parse(
            "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{\"Old\":\"Work\"},\"archivedParents\":[]}");
    assertEquals("Work", valid.getJSONObject("mappings").getString("Old"));
    try {
      ProjectAdjustments.parse("{\"mappings\":{\"Old\":\"Work\"},\"archivedParents\":[]}");
      fail("Expected unrecognized format to be rejected");
    } catch (IllegalArgumentException expected) {
      assertEquals("Unexpected file format", expected.getMessage());
    }
  }

  @Test
  public void editorPayloadRetainsUnresolvedMappingsAndPromotedParents() throws Exception {
    JSONObject adjustments =
        new JSONObject()
            .put("mappings", new JSONObject().put("Missing child", "Missing root"))
            .put("archivedParents", new JSONArray().put("Missing archive"));
    DashboardModel model = new DashboardModel(empty().put("adjustments", adjustments), CLOCK);
    adjustments.getJSONObject("mappings").put("Missing child", "Changed after construction");
    JSONObject exposed = MobilePayload.model(model).getJSONObject("adjustments");
    assertEquals("Missing root", exposed.getJSONObject("mappings").getString("Missing child"));
    assertEquals("Missing archive", exposed.getJSONArray("archivedParents").getString(0));
    JSONObject defaults =
        MobilePayload.model(new DashboardModel(empty(), CLOCK)).getJSONObject("adjustments");
    assertEquals(0, defaults.getJSONObject("mappings").length());
    assertEquals(0, defaults.getJSONArray("archivedParents").length());
  }

  @Test
  public void importMergesPhoneRulesAndIncomingMappingsWinConflicts() throws Exception {
    JSONObject existing =
        new JSONObject()
            .put(
                "mappings",
                new JSONObject().put("Conflict", "Old target").put("Phone only", "Saved root"))
            .put("archivedParents", new JSONArray().put("Phone parent").put("Shared parent"));
    JSONObject incoming =
        ProjectAdjustments.parse(
            "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{\"Conflict\":\"New"
                + " target\",\"Missing child\":\"Missing root\"},\"archivedParents\":[\"Shared"
                + " parent\",\"Imported parent\"]}");
    JSONObject merged = ProjectAdjustments.merge(existing, incoming);
    assertEquals("New target", merged.getJSONObject("mappings").getString("Conflict"));
    assertEquals("Saved root", merged.getJSONObject("mappings").getString("Phone only"));
    assertEquals("Missing root", merged.getJSONObject("mappings").getString("Missing child"));
    assertEquals(3, merged.getJSONArray("archivedParents").length());
    assertEquals("Old target", existing.getJSONObject("mappings").getString("Conflict"));
    assertEquals(2, existing.getJSONArray("archivedParents").length());
  }

  @Test
  public void importedMappingReplacesPhonePromotionUnlessFileAlsoPromotesIt() throws Exception {
    JSONObject phone =
        new JSONObject()
            .put("mappings", new JSONObject())
            .put("archivedParents", new JSONArray().put("Conflict").put("Unrelated"));
    JSONObject imported =
        ProjectAdjustments.parse(
            "{\"format\":\"todoist-assistant-project-adjustments-v1\",\"mappings\":{\"Conflict\":\"Root\"},\"archivedParents\":[]}");
    JSONObject merged = ProjectAdjustments.merge(phone, imported);
    assertEquals("Root", merged.getJSONObject("mappings").getString("Conflict"));
    assertEquals(1, merged.getJSONArray("archivedParents").length());
    assertEquals("Unrelated", merged.getJSONArray("archivedParents").getString(0));
    imported.getJSONArray("archivedParents").put("Conflict");
    assertEquals(
        2, ProjectAdjustments.merge(phone, imported).getJSONArray("archivedParents").length());
  }
}
