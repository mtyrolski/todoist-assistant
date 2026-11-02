package com.todoistassistant;

import java.time.Clock;
import java.time.DayOfWeek;
import java.time.LocalDate;
import org.json.JSONArray;
import org.json.JSONObject;

/** An offline example; never enters the user's saved snapshot. */
final class DemoData {
  static JSONObject create(Clock clock) throws Exception {
    LocalDate today = LocalDate.now(clock), monday = today.with(DayOfWeek.MONDAY);
    JSONArray projects =
        new JSONArray()
            .put(
                new JSONObject()
                    .put("id", "work")
                    .put("name", "Work")
                    .put("color", "blue")
                    .put("created_at", today.minusDays(150).toString()))
            .put(
                new JSONObject()
                    .put("id", "product")
                    .put("name", "Product launch")
                    .put("parent_id", "work")
                    .put("created_at", today.minusDays(120).toString()))
            .put(
                new JSONObject()
                    .put("id", "life")
                    .put("name", "Personal")
                    .put("created_at", today.minusDays(180).toString()));
    JSONArray tasks = new JSONArray(), events = new JSONArray();
    for (int i = 1; i <= 40; i++) {
      String project = i % 3 == 0 ? "life" : "product";
      tasks.put(
          new JSONObject()
              .put("id", "task-" + i)
              .put("project_id", project)
              .put(
                  "content",
                  new String[] {
                            "Review the release checklist",
                            "Plan the next milestone",
                            "Prepare project notes",
                            "Go for a walk"
                          }
                          [i % 4]
                      + " · "
                      + i)
              .put("priority", i % 4 + 1)
              .put("due", new JSONObject().put("date", today.plusDays(i % 7 - 2).toString()))
              .put("labels", new JSONArray().put(i == 1 ? "fire" : "next")));
    }
    for (int day = 62; day >= 0; day--) {
      LocalDate date = today.minusDays(day);
      for (int j = 0; j < 3 + day % 8; j++) {
        String id = "completion-" + day + "-" + j;
        if (j == 0 && day % 7 == 0)
          events.put(
              new JSONObject()
                  .put("id", "added-" + day)
                  .put("object_id", id)
                  .put("object_type", "item")
                  .put("event_type", "added")
                  .put("parent_project_id", "life")
                  .put(
                      "event_date",
                      date.minusDays(1 + day % 9)
                          .atTime(10, 0)
                          .atZone(clock.getZone())
                          .toInstant()
                          .toString()));
        events.put(
            new JSONObject()
                .put("id", id)
                .put("object_id", id)
                .put("object_type", "item")
                .put("event_type", "completed")
                .put("parent_project_id", j % 3 == 0 ? "life" : "product")
                .put(
                    "event_date",
                    date.atTime(
                            day == 0 ? 0 : 7 + (j * 3 + day) % 14, day == 0 ? 0 : (day + j) % 60)
                        .atZone(clock.getZone())
                        .toInstant()
                        .toString())
                .put(
                    "extra_data",
                    new JSONObject().put("content", "Completed milestone " + (day + j))));
      }
    }
    events.put(
        new JSONObject()
            .put("id", "demo-undo")
            .put("object_id", "completion-2-1")
            .put("object_type", "item")
            .put("event_type", "uncompleted")
            .put("parent_project_id", "product")
            .put("event_date", today.atStartOfDay(clock.getZone()).toInstant().toString())
            .put("extra_data", new JSONObject().put("content", "Reopened a milestone")));
    return new JSONObject()
        .put("schemaVersion", 2)
        .put("userId", "demo")
        .put("projects", projects)
        .put("tasks", tasks)
        .put("activities", events)
        .put("syncedAt", clock.instant().toString())
        .put("historyComplete", true)
        .put(
            "historyStart",
            monday.minusWeeks(9).atStartOfDay(clock.getZone()).toInstant().toString());
  }
}
