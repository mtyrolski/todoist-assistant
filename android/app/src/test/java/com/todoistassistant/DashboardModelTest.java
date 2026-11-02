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
  public void timeBasedDuesUseTheDeviceZone() {
    assertEquals(
        LocalDate.of(2026, 11, 2),
        DashboardModel.localDate("2026-11-01T23:30:00Z", ZoneId.of("Europe/Warsaw")));
    assertNull(DashboardModel.localDate("bad", ZoneId.of("UTC")));
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
    assertEquals(
        demo.getJSONArray("activities").length() - 2, java.util.Arrays.stream(model.weeks).sum());
    JSONObject payload = MobilePayload.model(model);
    assertEquals(40, payload.getJSONArray("tasks").length());
    assertEquals(model.weeks[8], payload.getJSONArray("weeks").getInt(8));
    int estimate = 0;
    JSONObject forecasts = payload.getJSONObject("projectForecasts");
    for (var keys = forecasts.keys(); keys.hasNext(); ) estimate += forecasts.getInt(keys.next());
    assertEquals(payload.getInt("forecast"), estimate);
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
}
