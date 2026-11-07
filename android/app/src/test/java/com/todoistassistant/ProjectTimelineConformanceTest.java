package com.todoistassistant;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

/** Checks Android's UTC daily history against the desktop lifecycle projection. */
public class ProjectTimelineConformanceTest {
  @Test
  public void androidProjectHistoryMatchesBackendFixturesAcrossDateWindows() throws Exception {
    Path directory = Paths.get(System.getProperty("completionFixtures")).getParent();
    JSONObject fixture =
        new JSONObject(
            new String(
                Files.readAllBytes(directory.resolve("project_timeline_conformance.json")),
                StandardCharsets.UTF_8));
    JSONObject snapshot = fixture.getJSONObject("snapshot");
    JSONArray tasks = snapshot.getJSONArray("tasks"),
        activities = snapshot.getJSONArray("activities");
    for (int index = 0; index < fixture.getInt("subtaskCount"); index++)
      tasks.put(
          new JSONObject()
              .put("id", "sub-" + index)
              .put("parent_id", "parent")
              .put("project_id", "renamed"));
    for (int index = 0; index < fixture.getInt("denseCount"); index++)
      activities.put(
          new JSONObject()
              .put("id", "dense-" + index)
              .put("object_type", "item")
              .put("object_id", "dense-task-" + index)
              .put("event_type", "completed")
              .put(
                  "event_date",
                  LocalDate.of(2026, 1, 1)
                      .plusDays(index)
                      .atTime(12, 0)
                      .toInstant(ZoneOffset.UTC)
                      .toString())
              .put("parent_project_id", "renamed"));
    activities.put(activities.getJSONObject(0));
    Clock clock = Clock.fixed(Instant.parse(snapshot.getString("syncedAt")), ZoneOffset.UTC);
    JSONArray hierarchy = new DashboardModel(snapshot, clock).plotData.getJSONArray("hierarchy");
    Map<String, JSONObject> byId = new HashMap<>();
    for (int i = 0; i < hierarchy.length(); i++) {
      JSONObject project = hierarchy.getJSONObject(i);
      byId.put(project.getString("id"), project);
    }
    JSONArray windows = fixture.getJSONArray("windows"),
        expected = fixture.getJSONArray("expected");
    for (int i = 0; i < windows.length(); i++) {
      JSONObject window = windows.getJSONObject(i), projects = expected.getJSONObject(i);
      for (java.util.Iterator<String> ids = projects.keys(); ids.hasNext(); ) {
        String id = ids.next();
        JSONObject project = byId.get(id), backend = projects.getJSONObject(id);
        assertNotNull("Missing project " + id, project);
        assertEquals(id, backend.getString("name"), project.getString("name"));
        assertEquals(id, backend.getBoolean("archived"), project.getBoolean("archived"));
        assertEquals(id, backend.getInt("openTasks"), project.getInt("openTasks"));
        assertEquals(id, "root", project.getString("parentId"));
        int count = 0;
        JSONArray days = project.getJSONArray("dailyCompletions");
        for (int j = 0; j < days.length(); j++) {
          JSONObject day = days.getJSONObject(j);
          String date = day.getString("date");
          if (date.compareTo(window.getString("start")) >= 0
              && date.compareTo(window.getString("end")) < 0) count += day.getInt("count");
        }
        assertEquals(id + " " + window, backend.getInt("completions"), count);
      }
    }
  }
}
