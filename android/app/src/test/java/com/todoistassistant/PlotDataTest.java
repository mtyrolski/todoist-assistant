package com.todoistassistant;

import static org.junit.Assert.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public class PlotDataTest {
  private static final Clock CLOCK =
      Clock.fixed(Instant.parse("2026-11-01T12:00:00Z"), ZoneId.of("Europe/Warsaw"));

  private JSONObject event(String id, String type, String when) throws Exception {
    return new JSONObject()
        .put("id", id)
        .put("object_type", "item")
        .put("object_id", "done")
        .put("event_type", type)
        .put("parent_project_id", "child")
        .put("event_date", when);
  }

  private JSONObject row(JSONArray rows, String date) throws Exception {
    for (int i = 0; i < rows.length(); i++)
      if (rows.getJSONObject(i).optString("date").equals(date)) return rows.getJSONObject(i);
    fail("Missing date " + date);
    return null;
  }

  private JSONObject project(JSONArray rows, String id) throws Exception {
    for (int i = 0; i < rows.length(); i++)
      if (rows.getJSONObject(i).getString("id").equals(id)) return rows.getJSONObject(i);
    fail("Missing project " + id);
    return null;
  }

  @Test
  public void timelineKeepsProjectIdentityAndOnlyEffectiveDailyCompletions() throws Exception {
    JSONObject root = new JSONObject().put("id", "root").put("name", "Parent");
    JSONObject old = new JSONObject().put("id", "child").put("name", "Old name");
    JSONObject renamed =
        new JSONObject()
            .put("id", "child")
            .put("name", "New name")
            .put("parent_id", "root")
            .put("created_at", "2026-10-01T00:00:00Z");
    JSONObject archived =
        new JSONObject()
            .put("id", "archived")
            .put("name", "Archived")
            .put("is_archived", true)
            .put("updated_at", "2026-10-28T00:00:00Z");
    JSONObject empty = new JSONObject().put("id", "empty").put("name", "New project");
    JSONObject first = event("done1", "completed", "2026-10-20T08:00:00Z");
    JSONArray events =
        new JSONArray()
            .put(first)
            .put(new JSONObject(first.toString()))
            .put(event("undo", "uncompleted", "2026-10-21T08:00:00Z"))
            .put(event("done2", "completed", "2026-10-22T08:00:00Z"))
            .put(
                event("orphan", "updated", "2026-10-25T08:00:00Z").put("parent_project_id", "lost"))
            .put(
                event("archived-event", "updated", "2026-10-26T08:00:00Z")
                    .put("parent_project_id", "archived"));
    JSONArray tasks =
        new JSONArray()
            .put(new JSONObject().put("id", "parent-task").put("project_id", "child"))
            .put(
                new JSONObject()
                    .put("id", "subtask")
                    .put("project_id", "child")
                    .put("parent_id", "parent-task"));
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray().put(root).put(renamed).put(empty))
            .put("knownProjects", new JSONArray().put(root).put(old).put(archived))
            .put("tasks", tasks)
            .put("activities", events)
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2026-10-15T00:00:00Z");
    DashboardModel model = new DashboardModel(snapshot, CLOCK);
    JSONArray hierarchy = model.plotData.getJSONArray("hierarchy");
    JSONObject child = project(hierarchy, "child");
    assertEquals("New name", child.getString("name"));
    assertEquals("root", child.getString("parentId"));
    assertEquals("metadata", child.getString("createdAtSource"));
    assertEquals(2, child.getInt("openTasks"));
    assertEquals(3, child.getJSONArray("dailyEvents").length());
    assertEquals(1, child.getJSONArray("dailyCompletions").length());
    assertEquals(1, row(child.getJSONArray("dailyCompletions"), "2026-10-22").getInt("count"));
    assertEquals("activity", project(hierarchy, "lost").getString("createdAtSource"));
    assertFalse(project(hierarchy, "lost").getBoolean("metadataKnown"));
    assertTrue(child.getBoolean("metadataKnown"));
    assertEquals(1, project(hierarchy, "lost").getJSONArray("dailyEvents").length());
    assertEquals("unknown", project(hierarchy, "empty").getString("createdAtSource"));
    assertEquals("2026-10-28", project(hierarchy, "archived").getString("updatedAt"));
    assertEquals("", project(hierarchy, "archived").getString("archivedAt"));
    JSONArray payloadTasks = MobilePayload.model(model).getJSONArray("tasks");
    for (int i = 0; i < payloadTasks.length(); i++)
      if (payloadTasks.getJSONObject(i).getString("id").equals("subtask")) {
        assertEquals("parent-task", payloadTasks.getJSONObject(i).getString("parentId"));
        return;
      }
    fail("Missing subtask");
  }

  @Test
  public void timelinePreaggregatesDenseHistoryPerLocalDay() throws Exception {
    JSONArray events = new JSONArray();
    for (int i = 0; i < 10000; i++)
      events.put(
          event("event-" + i, "completed", "2026-10-22T08:00:00Z").put("object_id", "task-" + i));
    JSONObject snapshot =
        new JSONObject()
            .put(
                "projects",
                new JSONArray().put(new JSONObject().put("id", "child").put("name", "Dense")))
            .put("tasks", new JSONArray())
            .put("activities", events)
            .put("syncedAt", CLOCK.instant().toString());
    JSONObject child =
        project(new DashboardModel(snapshot, CLOCK).plotData.getJSONArray("hierarchy"), "child");
    assertEquals(1, child.getJSONArray("dailyEvents").length());
    assertEquals(10000, child.getJSONArray("dailyEvents").getJSONObject(0).getInt("count"));
    assertEquals(10000, child.getJSONArray("dailyCompletions").getJSONObject(0).getInt("count"));
  }

  @Test
  public void plotsUseEffectiveCompletionsAndObservedEvents() throws Exception {
    JSONArray projects =
        new JSONArray()
            .put(new JSONObject().put("id", "root").put("name", "Root"))
            .put(new JSONObject().put("id", "child").put("name", "Child").put("parent_id", "root"));
    JSONArray events =
        new JSONArray()
            .put(event("add", "added", "2026-10-20T08:00:00Z"))
            .put(event("done1", "completed", "2026-10-21T08:00:00Z"))
            .put(event("undo", "uncompleted", "2026-10-22T08:00:00Z"))
            .put(event("done2", "completed", "2026-10-23T08:00:00Z"))
            .put(
                event("move", "updated", "2026-10-24T08:00:00Z")
                    .put(
                        "extra_data",
                        new JSONObject()
                            .put("due_date", "2026-10-28")
                            .put("last_due_date", "2026-10-25")));
    JSONObject active =
        new JSONObject()
            .put("id", "active")
            .put("project_id", "child")
            .put("priority", 4)
            .put("added_at", "2026-10-26T12:00:00Z");
    JSONObject snapshot =
        new JSONObject()
            .put("projects", projects)
            .put("tasks", new JSONArray().put(active))
            .put("activities", events)
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2026-10-01T00:00:00Z");
    DashboardModel model = new DashboardModel(snapshot, CLOCK);
    JSONObject data = MobilePayload.model(model).getJSONObject("plotData");
    JSONObject undone = row(data.getJSONArray("dailyActivity"), "2026-10-21");
    JSONObject completed = row(data.getJSONArray("dailyActivity"), "2026-10-23");
    assertEquals(1, undone.getJSONObject("counts").getInt("completed"));
    assertEquals(0, undone.getInt("effectiveCompletions"));
    assertEquals(1, completed.getInt("effectiveCompletions"));
    assertEquals(1, completed.getJSONObject("projects").getInt("Root"));
    assertEquals(1, completed.getJSONArray("hours").getInt(10));
    assertEquals(
        1,
        row(data.getJSONArray("dailyActivity"), "2026-10-24")
            .getJSONObject("counts")
            .getInt("rescheduled"));
    assertEquals(1, data.getJSONArray("lifespans").length());
    assertEquals(
        3 * 86400, data.getJSONArray("lifespans").getJSONObject(0).getDouble("seconds"), 0.01);
    assertEquals(1, row(data.getJSONArray("taskCounts"), "2026-11-01").getInt("p1"));
    JSONObject child = data.getJSONArray("hierarchy").getJSONObject(1);
    assertEquals("root", child.getString("parentId"));
    assertEquals(
        1, child.getJSONObject("weeklyCounts").getInt(String.valueOf(model.weeks.length - 2)));
  }

  @Test
  public void demoProvidesDurationsAndMoreThanOneActivityHour() throws Exception {
    DashboardModel model = new DashboardModel(DemoData.create(CLOCK), CLOCK);
    JSONObject data = MobilePayload.model(model).getJSONObject("plotData");
    assertTrue(data.getBoolean("historyComplete"));
    assertTrue(data.getJSONArray("lifespans").length() > 1);
    java.util.Set<Integer> occupied = new java.util.HashSet<>();
    JSONArray days = data.getJSONArray("dailyActivity");
    for (int i = 0; i < days.length(); i++) {
      JSONArray hours = days.getJSONObject(i).getJSONArray("hours");
      for (int hour = 0; hour < 24; hour++) if (hours.getInt(hour) > 0) occupied.add(hour);
    }
    assertTrue(occupied.size() > 3);
  }

  @Test
  public void hierarchyIncludesCompletionsWithoutAProjectId() throws Exception {
    JSONObject completion = event("unknown", "completed", "2026-10-30T10:00:00Z");
    completion.remove("parent_project_id");
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put("tasks", new JSONArray())
            .put("activities", new JSONArray().put(completion))
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2026-10-01T00:00:00Z");
    DashboardModel model = new DashboardModel(snapshot, CLOCK);
    JSONObject project = model.plotData.getJSONArray("hierarchy").getJSONObject(0);
    assertEquals("Unknown project", project.getString("rootName"));
    assertEquals(
        1, project.getJSONObject("weeklyCounts").getInt(String.valueOf(model.weeks.length - 1)));
  }

  @Test
  public void localCalendarBoundariesAndDaylightSavingStayConsistent() throws Exception {
    Clock monday = Clock.fixed(Instant.parse("2026-11-02T12:00:00Z"), CLOCK.getZone());
    JSONArray events =
        new JSONArray()
            .put(event("a", "added", "2026-10-25T00:30:00Z"))
            .put(event("b", "updated", "2026-10-25T01:30:00Z"))
            .put(event("c", "completed", "2026-11-01T23:30:00Z"));
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put("tasks", new JSONArray())
            .put("activities", events)
            .put("syncedAt", monday.instant().toString())
            .put("historyStart", "2026-10-01T00:00:00Z");
    DashboardModel model = new DashboardModel(snapshot, monday);
    JSONArray daily = model.plotData.getJSONArray("dailyActivity");
    assertEquals(2, row(daily, "2026-10-25").getJSONArray("hours").getInt(2));
    assertEquals(1, row(daily, "2026-11-02").getInt("effectiveCompletions"));
    assertEquals(1, row(daily, "2026-11-02").getJSONArray("hours").getInt(0));
    assertEquals(1, model.weeks[model.weeks.length - 1]);
  }

  @Test
  public void partialHistoryDoesNotExtrapolateFromOlderTaskCreation() throws Exception {
    JSONObject task =
        new JSONObject().put("id", "t").put("priority", 4).put("added_at", "2020-01-01");
    JSONArray events = new JSONArray().put(event("edit", "updated", "2026-10-29T08:00:00Z"));
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put("tasks", new JSONArray().put(task))
            .put("activities", events)
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2026-10-25T00:00:00Z");
    JSONArray counts = new DashboardModel(snapshot, CLOCK).plotData.getJSONArray("taskCounts");
    assertEquals("2026-10-29", counts.getJSONObject(0).getString("date"));
    assertFalse(new DashboardModel(snapshot, CLOCK).plotData.getBoolean("historyComplete"));
    snapshot.put("activities", new JSONArray());
    assertEquals(
        1, new DashboardModel(snapshot, CLOCK).plotData.getJSONArray("taskCounts").length());
  }

  @Test
  public void taskCountsHandlePriorityChangesAndReopenedTasksAcrossDays() throws Exception {
    JSONArray tasks = new JSONArray().put(new JSONObject().put("id", "active").put("priority", 4));
    JSONArray events =
        new JSONArray()
            .put(event("add", "added", "2026-10-28T08:00:00Z").put("object_id", "active"))
            .put(
                event("priority", "updated", "2026-10-29T08:00:00Z")
                    .put("object_id", "active")
                    .put("extra_data", new JSONObject().put("last_priority", 2)))
            .put(event("add-old", "added", "2026-10-28T09:00:00Z").put("object_id", "old"))
            .put(
                event("done-old", "completed", "2026-10-30T08:00:00Z")
                    .put("object_id", "old")
                    .put("extra_data", new JSONObject().put("priority", 3)));
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put("tasks", tasks)
            .put("activities", events)
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2026-10-27T00:00:00Z");
    JSONArray counts = new DashboardModel(snapshot, CLOCK).plotData.getJSONArray("taskCounts");
    assertEquals(1, row(counts, "2026-11-01").getInt("p1"));
    assertEquals(2, row(counts, "2026-10-29").getInt("total"));
    assertEquals(1, row(counts, "2026-10-29").getInt("p1"));
    assertEquals(1, row(counts, "2026-10-29").getInt("p2"));
    assertEquals(1, row(counts, "2026-10-28").getInt("p3"));
  }

  @Test
  public void taskCountsPreserveSameDayAndMissingCreationBoundaries() throws Exception {
    JSONArray events =
        new JSONArray()
            .put(event("add", "added", "2026-10-29T08:00:00Z").put("object_id", "same"))
            .put(event("done", "completed", "2026-10-29T09:00:00Z").put("object_id", "same"))
            .put(event("unknown", "completed", "2026-10-28T09:00:00Z").put("object_id", "unknown"));
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put(
                "tasks",
                new JSONArray().put(new JSONObject().put("id", "undated").put("priority", 4)))
            .put("activities", events)
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2026-10-01T00:00:00Z");
    JSONArray counts = new DashboardModel(snapshot, CLOCK).plotData.getJSONArray("taskCounts");
    for (String date : new String[] {"2026-10-28", "2026-10-29", "2026-11-01"}) {
      JSONObject value = row(counts, date);
      assertEquals(1, value.getInt("total"));
      assertEquals(1, value.getInt("p1"));
    }
  }

  @Test
  public void taskCountHistoryRemainsCorrectForManyTasksAndYears() throws Exception {
    JSONArray tasks = new JSONArray();
    for (int i = 0; i < 6000; i++)
      tasks.put(new JSONObject().put("id", "task-" + i).put("priority", (i % 4) + 1));
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put("tasks", tasks)
            .put("activities", new JSONArray().put(event("old", "updated", "2016-11-01T00:00:00Z")))
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2016-11-01T00:00:00Z")
            .put("historyComplete", true);
    JSONArray counts = new DashboardModel(snapshot, CLOCK).plotData.getJSONArray("taskCounts");
    assertEquals(3653, counts.length());
    for (String date : new String[] {"2016-11-01", "2026-11-01"}) {
      JSONObject value = row(counts, date);
      assertEquals(6000, value.getInt("total"));
      for (String priority : new String[] {"p1", "p2", "p3", "p4"})
        assertEquals(1500, value.getInt(priority));
    }
  }

  @Test
  public void incompleteCoverageStartsAtTheFirstWholeLocalDayAcrossDst() throws Exception {
    Clock afterDst = Clock.fixed(Instant.parse("2026-10-27T12:00:00Z"), CLOCK.getZone());
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put("tasks", new JSONArray())
            .put("activities", new JSONArray())
            .put("syncedAt", afterDst.instant().toString())
            .put("historyComplete", false)
            .put("historyStart", "2026-10-25T00:30:00Z");
    assertEquals(
        "2026-10-26", new DashboardModel(snapshot, afterDst).plotData.getString("historyStart"));
    assertEquals("2026-10-25T00:30:00Z", snapshot.getString("historyStart"));
    snapshot.put("historyStart", "2026-10-24T22:00:00Z");
    assertEquals(
        "2026-10-25", new DashboardModel(snapshot, afterDst).plotData.getString("historyStart"));
    snapshot.put("historyStart", "2026-10-25");
    assertEquals(
        "2026-10-25", new DashboardModel(snapshot, afterDst).plotData.getString("historyStart"));
    snapshot.put("historyStart", "2026-10-25T00:30:00Z").put("historyComplete", true);
    assertEquals(
        "2026-10-25", new DashboardModel(snapshot, afterDst).plotData.getString("historyStart"));

    ZoneId brazil = ZoneId.of("America/Sao_Paulo");
    Clock skippedMidnight = Clock.fixed(Instant.parse("2018-11-07T12:00:00Z"), brazil);
    snapshot
        .put("syncedAt", skippedMidnight.instant().toString())
        .put("historyComplete", false)
        .put("historyStart", "2018-11-04T03:00:00Z");
    assertEquals(
        "2018-11-04",
        new DashboardModel(snapshot, skippedMidnight).plotData.getString("historyStart"));
    snapshot.put("historyStart", "2018-11-04T03:30:00Z");
    assertEquals(
        "2018-11-05",
        new DashboardModel(snapshot, skippedMidnight).plotData.getString("historyStart"));
  }

  @Test
  public void oldArchiveDoesNotEndAnActiveOrReopenedProject() throws Exception {
    JSONObject project = new JSONObject().put("id", "p").put("name", "Project");
    JSONArray events =
        new JSONArray()
            .put(
                event("archive", "archived", "2026-10-20T08:00:00Z")
                    .put("object_type", "project")
                    .put("object_id", "p"))
            .put(
                event("reopen", "unarchived", "2026-10-21T08:00:00Z")
                    .put("object_type", "project")
                    .put("object_id", "p"));
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray().put(project))
            .put("tasks", new JSONArray())
            .put("activities", events)
            .put("syncedAt", CLOCK.instant().toString())
            .put("historyStart", "2026-10-01T00:00:00Z");
    assertEquals(
        "",
        new DashboardModel(snapshot, CLOCK)
            .plotData
            .getJSONArray("hierarchy")
            .getJSONObject(0)
            .getString("archivedAt"));
    project.put("is_archived", true);
    assertEquals(
        "",
        new DashboardModel(snapshot, CLOCK)
            .plotData
            .getJSONArray("hierarchy")
            .getJSONObject(0)
            .getString("archivedAt"));
  }

  @Test
  public void staleActivityCannotReconstructCountsAcrossAnUnknownGap() throws Exception {
    JSONObject task = new JSONObject().put("id", "t").put("priority", 4);
    JSONObject snapshot =
        new JSONObject()
            .put("projects", new JSONArray())
            .put("tasks", new JSONArray().put(task))
            .put("activities", new JSONArray().put(event("e", "completed", "2026-10-26T08:00:00Z")))
            .put("syncedAt", CLOCK.instant().toString())
            .put("activitySyncedAt", "2026-10-28T12:00:00Z")
            .put("historyStart", "2026-10-01T00:00:00Z");
    JSONObject plots = new DashboardModel(snapshot, CLOCK).plotData;
    JSONArray counts = plots.getJSONArray("taskCounts");
    assertEquals("2026-10-28", plots.getString("historyAsOf"));
    assertEquals(1, counts.length());
    assertEquals("2026-11-01", counts.getJSONObject(0).getString("date"));
    assertEquals(1, counts.getJSONObject(0).getInt("total"));
  }
}
