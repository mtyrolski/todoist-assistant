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
    DashboardModel model = new DashboardModel(DemoData.create(CLOCK), CLOCK);
    assertEquals(40, model.tasks.size());
    assertEquals(
        model.weeks[8],
        model.projectCompletions.values().stream().mapToInt(Integer::intValue).sum());
    assertTrue(model.forecast >= model.weeks[8]);
  }
}
