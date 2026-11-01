package com.todoistassistant;

import java.time.Clock;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;

/** Immutable, precomputed screen data. Build on a worker, bind cheaply on the UI thread. */
final class DashboardModel {
  static final class Task {
    final String id, projectId, content, project, due, deadline;
    final int priority;
    final List<String> labels;

    Task(JSONObject item, String project) {
      id = item.optString("id");
      projectId = item.optString("project_id");
      content = item.optString("content", "Untitled task");
      this.project = project;
      priority = Math.min(4, Math.max(1, item.optInt("priority", 1)));
      due = dateValue(item.opt("due"));
      deadline = dateValue(item.opt("deadline"));
      List<String> names = new ArrayList<>();
      JSONArray raw = item.optJSONArray("labels");
      if (raw != null) for (int i = 0; i < raw.length(); i++) names.add(raw.optString(i));
      labels = Collections.unmodifiableList(names);
    }

    String searchText() {
      return (content + " " + project + " " + String.join(" ", labels)).toLowerCase(Locale.ROOT);
    }
  }

  static final class Project {
    final String id, path;
    final List<Task> tasks;

    Project(String id, String path, List<Task> tasks) {
      this.id = id;
      this.path = path;
      this.tasks = Collections.unmodifiableList(tasks);
    }
  }

  static final class Activity {
    final String id, kind, content, project;
    final Instant date;

    Activity(JSONObject item, Map<String, JSONObject> projects) {
      id = item.optString("id");
      kind = item.optString("event_type");
      JSONObject extra = item.optJSONObject("extra_data");
      content = extra == null ? "" : extra.optString("content", extra.optString("name"));
      project = projectPath(item.optString("parent_project_id"), projects);
      date = Instant.parse(item.optString("event_date"));
    }
  }

  final List<Project> projects;
  final List<Task> tasks;
  final List<Activity> recent;
  final Instant syncedAt;
  final LocalDate weekStart;
  final int[] weeks, priorities;
  final List<Map<String, Integer>> weeklyProjects;
  final int forecast, undone, eventCount;
  final boolean forecastAvailable, historyAvailable;
  final String historyWarning;
  final String historyStart;

  DashboardModel(JSONObject snapshot, Clock clock) throws Exception {
    syncedAt = Instant.parse(snapshot.getString("syncedAt"));
    Instant historyAsOf =
        Instant.parse(snapshot.optString("activitySyncedAt", syncedAt.toString()));
    historyAvailable = !snapshot.optBoolean("activityUnavailable");
    historyWarning = snapshot.optString("activityWarning", snapshot.optString("metadataWarning"));
    historyStart = snapshot.getString("historyStart");
    weekStart = LocalDate.now(clock).with(DayOfWeek.MONDAY);
    Map<String, JSONObject> known = new LinkedHashMap<>();
    JSONArray active = snapshot.getJSONArray("projects");
    JSONArray all = snapshot.optJSONArray("knownProjects");
    if (all == null) all = active;
    for (int i = 0; i < all.length(); i++)
      known.put(all.getJSONObject(i).getString("id"), all.getJSONObject(i));
    for (int i = 0; i < active.length(); i++)
      known.put(active.getJSONObject(i).getString("id"), active.getJSONObject(i));
    java.util.Set<String> archivedRoots = new java.util.HashSet<>();
    for (var project : known.values())
      if (project.optBoolean("is_archived"))
        archivedRoots.add(rootName(project.optString("id"), known));
    for (int i = 0; i < active.length(); i++)
      archivedRoots.remove(rootName(active.getJSONObject(i).optString("id"), known));
    priorities = new int[4];
    List<Task> taskList = new ArrayList<>();
    Map<String, List<Task>> byProject = new HashMap<>();
    JSONArray rawTasks = snapshot.getJSONArray("tasks");
    for (int i = 0; i < rawTasks.length(); i++) {
      JSONObject item = rawTasks.getJSONObject(i);
      if (item.optBoolean("checked") || item.optBoolean("is_deleted")) continue;
      Task task = new Task(item, projectPath(item.optString("project_id"), known));
      taskList.add(task);
      priorities[4 - task.priority]++;
      byProject.computeIfAbsent(task.projectId, id -> new ArrayList<>()).add(task);
    }
    Comparator<Task> order =
        Comparator.comparingInt((Task task) -> -task.priority)
            .thenComparing(task -> task.due.isEmpty() ? "9999" : task.due)
            .thenComparing(task -> task.content, String.CASE_INSENSITIVE_ORDER);
    taskList.sort(order);
    tasks = Collections.unmodifiableList(taskList);
    List<Project> projectList = new ArrayList<>();
    for (int i = 0; i < active.length(); i++) {
      JSONObject item = active.getJSONObject(i);
      String id = item.getString("id");
      List<Task> children = byProject.remove(id);
      if (children == null) children = new ArrayList<>();
      children.sort(order);
      projectList.add(new Project(id, projectPath(id, known), children));
    }
    // A project can disappear between the project and task requests. Keep its tasks visible.
    for (var entry : byProject.entrySet()) {
      entry.getValue().sort(order);
      projectList.add(
          new Project(entry.getKey(), projectPath(entry.getKey(), known), entry.getValue()));
    }
    projectList.sort(Comparator.comparing(project -> project.path, String.CASE_INSENSITIVE_ORDER));
    projects = Collections.unmodifiableList(projectList);
    JSONArray rawEvents = snapshot.getJSONArray("activities");
    eventCount = rawEvents.length();
    List<CompletionLedger.Event> events = new ArrayList<>();
    Map<String, String> completionProjects = new HashMap<>();
    List<Activity> activityList = new ArrayList<>();
    int undoCount = 0;
    for (int i = 0; i < rawEvents.length(); i++) {
      JSONObject item = rawEvents.getJSONObject(i);
      Instant time = Instant.parse(item.getString("event_date"));
      if (time.isAfter(historyAsOf)) continue;
      activityList.add(new Activity(item, known));
      if (!item.optString("object_type").equals("item")) continue;
      JSONObject extra = item.optJSONObject("extra_data");
      if (extra == null) extra = new JSONObject();
      JSONObject due = extra.optJSONObject("due");
      Boolean recurring = null;
      if (extra.opt("is_recurring") instanceof Boolean)
        recurring = (Boolean) extra.opt("is_recurring");
      else if (due != null && due.opt("is_recurring") instanceof Boolean)
        recurring = (Boolean) due.opt("is_recurring");
      else if (extra.optBoolean("sub_tasks_reset")) recurring = Boolean.TRUE;
      String kind = item.optString("event_type"), id = item.getString("id");
      events.add(
          new CompletionLedger.Event(id, item.getString("object_id"), kind, time, recurring));
      completionProjects.put(id, rootName(item.optString("parent_project_id"), known));
      if (kind.equals("uncompleted")
          && !time.atZone(clock.getZone()).toLocalDate().isBefore(weekStart)) undoCount++;
    }
    undone = undoCount;
    activityList.sort(
        Comparator.comparing((Activity event) -> event.date)
            .reversed()
            .thenComparing(event -> event.id));
    recent =
        Collections.unmodifiableList(
            new ArrayList<>(activityList.subList(0, Math.min(200, activityList.size()))));
    weeks = new int[9];
    Map<String, int[]> projectWeeks = new LinkedHashMap<>();
    Map<String, LocalDate> firstCompletion = new HashMap<>();
    for (var event : CompletionLedger.effective(events)) {
      LocalDate day = event.date.atZone(clock.getZone()).toLocalDate();
      String root = completionProjects.get(event.id);
      firstCompletion.merge(root, day, (first, next) -> first.isBefore(next) ? first : next);
      long days = java.time.temporal.ChronoUnit.DAYS.between(weekStart.minusWeeks(8), day);
      if (days < 0 || days >= 63) continue;
      int index = (int) (days / 7);
      weeks[index]++;
      projectWeeks.computeIfAbsent(completionProjects.get(event.id), name -> new int[9])[index]++;
    }
    Instant begin = weekStart.atStartOfDay(clock.getZone()).toInstant();
    Instant end = weekStart.plusWeeks(1).atStartOfDay(clock.getZone()).toInstant();
    forecastAvailable = historyAvailable && !historyAsOf.isBefore(begin);
    double fraction =
        Duration.between(begin, historyAsOf).toMillis()
            / (double) Duration.between(begin, end).toMillis();
    int estimate = 0;
    for (var entry : projectWeeks.entrySet()) {
      int[] values = entry.getValue();
      int first = 0;
      if (!firstCompletion.get(entry.getKey()).isBefore(weekStart.minusWeeks(8)))
        while (first < 8 && values[first] == 0) first++;
      double[] history = new double[8 - first];
      for (int i = first; i < 8; i++) history[i - first] = values[i];
      boolean recentlyActive =
          values[8] > 0 || values[7] > 0 || values[6] > 0 || values[5] > 0 || values[4] > 0;
      estimate +=
          forecastAvailable && recentlyActive && !archivedRoots.contains(entry.getKey())
              ? Forecast.total(values[8], history, fraction)
              : values[8];
    }
    forecast = estimate;
    List<Map<String, Integer>> breakdowns = new ArrayList<>();
    for (int week = 0; week < 9; week++) {
      Map<String, Integer> breakdown = new HashMap<>();
      for (var entry : projectWeeks.entrySet())
        if (entry.getValue()[week] > 0) breakdown.put(entry.getKey(), entry.getValue()[week]);
      List<Map.Entry<String, Integer>> ranked = new ArrayList<>(breakdown.entrySet());
      ranked.sort(
          Map.Entry.<String, Integer>comparingByValue()
              .reversed()
              .thenComparing(Map.Entry.comparingByKey()));
      Map<String, Integer> sortedCounts = new LinkedHashMap<>();
      for (var entry : ranked) sortedCounts.put(entry.getKey(), entry.getValue());
      breakdowns.add(Collections.unmodifiableMap(sortedCounts));
    }
    weeklyProjects = Collections.unmodifiableList(breakdowns);
  }

  static String dateValue(Object value) {
    if (value instanceof JSONObject) return ((JSONObject) value).optString("date");
    return value == null || value == JSONObject.NULL ? "" : String.valueOf(value);
  }

  static LocalDate localDate(String value, ZoneId zone) {
    if (value == null || value.trim().isEmpty()) return null;
    try {
      return OffsetDateTime.parse(value).atZoneSameInstant(zone).toLocalDate();
    } catch (java.time.format.DateTimeParseException ignored) {
      try {
        return LocalDate.parse(value.substring(0, 10));
      } catch (RuntimeException invalid) {
        return null;
      }
    }
  }

  static String projectPath(String id, Map<String, JSONObject> projects) {
    List<String> parts = new ArrayList<>();
    java.util.Set<String> visited = new java.util.HashSet<>();
    while (!id.isEmpty() && visited.add(id)) {
      JSONObject project = projects.get(id);
      if (project == null) break;
      parts.add(project.optString("name", "Unknown project"));
      id = project.isNull("parent_id") ? "" : project.optString("parent_id");
    }
    Collections.reverse(parts);
    return parts.isEmpty() ? "Unknown project" : String.join(" / ", parts);
  }

  private static String rootName(String id, Map<String, JSONObject> projects) {
    String name = "Unknown project";
    java.util.Set<String> visited = new java.util.HashSet<>();
    while (!id.isEmpty() && visited.add(id)) {
      JSONObject project = projects.get(id);
      if (project == null) break;
      name = project.optString("name", name);
      id = project.isNull("parent_id") ? "" : project.optString("parent_id");
    }
    return name;
  }
}
