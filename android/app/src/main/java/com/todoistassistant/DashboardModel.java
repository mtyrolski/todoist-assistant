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
    final String id, projectId, parentId, content, project, due, deadline;
    final int priority;
    final List<String> labels;

    Task(JSONObject item, String project) {
      id = item.optString("id");
      projectId = item.optString("project_id");
      parentId = item.isNull("parent_id") ? "" : item.optString("parent_id", "");
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
  }

  static final class Project {
    final String id, path;

    Project(String id, String path) {
      this.id = id;
      this.path = path;
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
      project = projectPath(activityProjectId(item, projects), projects);
      date = Instant.parse(item.optString("event_date"));
    }
  }

  final List<Project> projects;
  final List<Task> tasks;
  final List<Activity> recent;
  final Instant syncedAt, activitySyncedAt;
  final ZoneId zoneId;
  final LocalDate renderedOn, weekStart;
  final int[] weeks, priorities;
  final List<Map<String, Integer>> weeklyProjects;
  final Map<String, Integer> projectForecasts;
  final Map<String, String> projectColors;
  final JSONObject adjustments;
  final JSONObject plotData;
  final JSONObject habitTracker;
  final String quotedMobilePayload;
  final int forecast, activityTotal;
  final boolean forecastAvailable, historyAvailable, activitySyncExclusive;
  final String historyWarning;

  DashboardModel(JSONObject snapshot, Clock clock) throws Exception {
    syncedAt = Instant.parse(snapshot.getString("syncedAt"));
    String activitySync = snapshot.optString("activitySyncedAt", "");
    activitySyncExclusive = !activitySync.isEmpty() && !activitySync.equals("null");
    activitySyncedAt =
        activitySync.isEmpty() || activitySync.equals("null")
            ? syncedAt
            : Instant.parse(activitySync);
    Instant historyAsOf = activitySyncedAt;
    historyAvailable = !snapshot.optBoolean("activityUnavailable");
    historyWarning = snapshot.optString("activityWarning", snapshot.optString("metadataWarning"));
    zoneId = clock.getZone();
    renderedOn = LocalDate.now(clock);
    weekStart = renderedOn.with(DayOfWeek.MONDAY);
    Map<String, JSONObject> known = new LinkedHashMap<>();
    JSONArray active = snapshot.getJSONArray("projects");
    JSONArray all = snapshot.optJSONArray("knownProjects");
    if (all == null) all = active;
    for (int i = 0; i < all.length(); i++)
      known.put(all.getJSONObject(i).getString("id"), all.getJSONObject(i));
    for (int i = 0; i < active.length(); i++)
      known.put(active.getJSONObject(i).getString("id"), active.getJSONObject(i));
    JSONObject adjustments = snapshot.optJSONObject("adjustments");
    JSONObject mappings =
        adjustments == null ? new JSONObject() : adjustments.optJSONObject("mappings");
    if (mappings == null) mappings = new JSONObject();
    JSONObject projectMappings =
        adjustments == null ? null : adjustments.optJSONObject("projectMappings");
    if (projectMappings == null) projectMappings = new JSONObject();
    JSONArray promoted = adjustments == null ? null : adjustments.optJSONArray("archivedParents");
    this.adjustments =
        new JSONObject()
            .put("mappings", new JSONObject(mappings.toString()))
            .put("projectMappings", new JSONObject(projectMappings.toString()))
            .put(
                "archivedParents",
                promoted == null ? new JSONArray() : new JSONArray(promoted.toString()));
    java.util.Set<String> promotedNames = new java.util.HashSet<>();
    if (promoted != null)
      for (int i = 0; i < promoted.length(); i++) promotedNames.add(promoted.optString(i));
    JSONObject savedMappings = mappings;
    JSONObject savedProjectMappings = projectMappings;
    Map<String, String> rootNames = new HashMap<>();
    java.util.function.Function<String, String> rootFor =
        id ->
            rootNames.computeIfAbsent(
                id,
                key -> rootName(key, known, savedMappings, savedProjectMappings, promotedNames));
    java.util.Set<String> archivedRoots = new java.util.HashSet<>();
    for (var project : known.values())
      if (project.optBoolean("is_archived"))
        archivedRoots.add(rootFor.apply(project.optString("id")));
    for (int i = 0; i < active.length(); i++)
      archivedRoots.remove(rootFor.apply(active.getJSONObject(i).optString("id")));
    Map<String, String> colors = new LinkedHashMap<>();
    for (var project : known.values()) {
      String parent = TodoistClient.parentId(project);
      if (!known.containsKey(parent))
        colors.put(project.optString("name"), project.optString("color", "grey"));
    }
    for (var project : known.values())
      colors.putIfAbsent(
          rootFor.apply(project.optString("id")), project.optString("color", "grey"));
    projectColors = Collections.unmodifiableMap(colors);
    priorities = new int[4];
    List<Task> taskList = new ArrayList<>();
    JSONArray rawTasks = snapshot.getJSONArray("tasks");
    for (int i = 0; i < rawTasks.length(); i++) {
      JSONObject item = rawTasks.getJSONObject(i);
      if (item.optBoolean("checked") || item.optBoolean("is_deleted")) continue;
      Task task = new Task(item, projectPath(item.optString("project_id"), known));
      taskList.add(task);
      priorities[4 - task.priority]++;
    }
    Comparator<Task> order =
        Comparator.comparingInt((Task task) -> -task.priority)
            .thenComparing(task -> task.due.isEmpty() ? "9999" : task.due)
            .thenComparing(task -> task.content, String.CASE_INSENSITIVE_ORDER);
    taskList.sort(order);
    tasks = Collections.unmodifiableList(taskList);
    List<Project> projectList = new ArrayList<>();
    java.util.Set<String> projectIds = new java.util.HashSet<>();
    for (int i = 0; i < active.length(); i++) {
      JSONObject item = active.getJSONObject(i);
      String id = item.getString("id");
      projectIds.add(id);
      projectList.add(new Project(id, projectPath(id, known)));
    }
    // A project can disappear between the project and task requests. Keep its tasks visible.
    for (var task : tasks)
      if (projectIds.add(task.projectId))
        projectList.add(new Project(task.projectId, task.project));
    projectList.sort(Comparator.comparing(project -> project.path, String.CASE_INSENSITIVE_ORDER));
    projects = Collections.unmodifiableList(projectList);
    JSONArray rawEvents = snapshot.getJSONArray("activities");
    Map<String, JSONObject> uniqueEvents = new LinkedHashMap<>();
    for (int i = 0; i < rawEvents.length(); i++) {
      JSONObject item = rawEvents.getJSONObject(i);
      uniqueEvents.put(String.valueOf(item.get("id")), item);
    }
    List<JSONObject> activities = new ArrayList<>();
    for (JSONObject item : uniqueEvents.values()) {
      Instant time = Instant.parse(item.getString("event_date"));
      if (activitySyncExclusive ? time.isBefore(historyAsOf) : !time.isAfter(historyAsOf))
        activities.add(item);
    }
    List<CompletionLedger.Event> events = new ArrayList<>();
    Map<String, String> completionProjects = new HashMap<>();
    List<Activity> activityList = new ArrayList<>();
    for (JSONObject item : activities) {
      Instant time = Instant.parse(item.getString("event_date"));
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
      String kind = item.optString("event_type"), id = String.valueOf(item.get("id"));
      events.add(
          new CompletionLedger.Event(id, item.getString("object_id"), kind, time, recurring));
      completionProjects.put(id, rootFor.apply(activityProjectId(item, known)));
    }
    activityList.sort(
        Comparator.comparing((Activity event) -> event.date)
            .reversed()
            .thenComparing(event -> event.id));
    activityTotal = activityList.size();
    recent =
        Collections.unmodifiableList(
            new ArrayList<>(activityList.subList(0, Math.min(200, activityList.size()))));
    List<CompletionLedger.Event> completed = CompletionLedger.effective(events);
    habitTracker = trackedHabits(tasks, completed, activities, known, weekStart, zoneId);
    LocalDate firstWeek = weekStart.minusWeeks(8);
    for (var event : completed) {
      LocalDate day = event.date.atZone(clock.getZone()).toLocalDate();
      LocalDate week = day.with(DayOfWeek.MONDAY);
      if (week.isBefore(firstWeek)) firstWeek = week;
    }
    int weekCount = (int) java.time.temporal.ChronoUnit.WEEKS.between(firstWeek, weekStart) + 1;
    int currentWeek = weekCount - 1;
    weeks = new int[weekCount];
    Map<String, int[]> projectWeeks = new LinkedHashMap<>();
    Map<String, LocalDate> firstCompletion = new HashMap<>();
    for (var event : completed) {
      LocalDate day = event.date.atZone(clock.getZone()).toLocalDate();
      String root = completionProjects.get(event.id);
      firstCompletion.merge(root, day, (first, next) -> first.isBefore(next) ? first : next);
      long days = java.time.temporal.ChronoUnit.DAYS.between(firstWeek, day);
      if (days < 0 || days >= (long) weekCount * 7) continue;
      int index = (int) (days / 7);
      weeks[index]++;
      projectWeeks
          .computeIfAbsent(completionProjects.get(event.id), name -> new int[weekCount])[index]++;
    }
    Instant begin = weekStart.atStartOfDay(clock.getZone()).toInstant();
    Instant end = weekStart.plusWeeks(1).atStartOfDay(clock.getZone()).toInstant();
    forecastAvailable =
        historyAvailable
            && !completed.isEmpty()
            && !historyAsOf.isBefore(begin)
            && !historyAsOf.isBefore(syncedAt);
    double fraction =
        Duration.between(begin, historyAsOf).toMillis()
            / (double) Duration.between(begin, end).toMillis();
    Map<String, Integer> estimates = new LinkedHashMap<>();
    for (var entry : projectWeeks.entrySet()) {
      int[] values = entry.getValue();
      int first = currentWeek - 8;
      if (!firstCompletion.get(entry.getKey()).isBefore(weekStart.minusWeeks(8)))
        while (first < currentWeek && values[first] == 0) first++;
      double[] history = new double[currentWeek - first];
      for (int i = first; i < currentWeek; i++) history[i - first] = values[i];
      boolean recentlyActive =
          values[currentWeek] > 0
              || values[currentWeek - 1] > 0
              || values[currentWeek - 2] > 0
              || values[currentWeek - 3] > 0
              || values[currentWeek - 4] > 0;
      estimates.put(
          entry.getKey(),
          forecastAvailable && recentlyActive && !archivedRoots.contains(entry.getKey())
              ? Forecast.total(values[currentWeek], history, fraction)
              : values[currentWeek]);
    }
    projectForecasts = Collections.unmodifiableMap(estimates);
    forecast = estimates.values().stream().mapToInt(Integer::intValue).sum();
    List<Map<String, Integer>> breakdowns = new ArrayList<>();
    for (int week = 0; week < weekCount; week++) {
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
    plotData =
        PlotData.build(
            snapshot, clock, historyAsOf, known, rootFor, firstWeek, completed, activities);
    quotedMobilePayload = JSONObject.quote(MobilePayload.model(this).toString());
  }

  private static JSONObject trackedHabits(
      List<Task> tasks,
      List<CompletionLedger.Event> completed,
      List<JSONObject> activities,
      Map<String, JSONObject> projects,
      LocalDate weekStart,
      ZoneId zone)
      throws Exception {
    Map<String, Task> tracked = new LinkedHashMap<>();
    for (Task task : tasks) {
      for (String label : task.labels)
        if (label.trim().replaceFirst("^@+", "").toLowerCase(Locale.ROOT).equals("track_habit")) {
          tracked.put(task.id, task);
          break;
        }
    }
    Map<String, int[]> counts = new HashMap<>();
    int[][] history = new int[8][2];
    for (var event : completed)
      if (tracked.containsKey(event.taskId))
        addHabitEvent(
            counts, history, event.taskId, event.date.atZone(zone).toLocalDate(), weekStart, 0);
    for (JSONObject event : activities) {
      if (!event.optString("object_type").equals("item")
          || !event.optString("event_type").equals("updated")) continue;
      JSONObject extra = event.optJSONObject("extra_data");
      String taskId = event.optString("object_id");
      if (tracked.containsKey(taskId)
          && extra != null
          && extra.has("due_date")
          && extra.has("last_due_date"))
        addHabitEvent(
            counts,
            history,
            taskId,
            Instant.parse(event.getString("event_date")).atZone(zone).toLocalDate(),
            weekStart,
            1);
    }
    List<Task> sorted = new ArrayList<>(tracked.values());
    sorted.sort(
        Comparator.<Task>comparingInt(task -> -counts.getOrDefault(task.id, new int[4])[0])
            .thenComparingInt(task -> counts.getOrDefault(task.id, new int[4])[1])
            .thenComparingInt(task -> -counts.getOrDefault(task.id, new int[4])[2])
            .thenComparing(task -> task.content.toLowerCase(Locale.ROOT)));
    JSONArray items = new JSONArray(), weeks = new JSONArray();
    int[] totals = new int[4];
    String[] keys = {
      "weeklyCompleted", "weeklyRescheduled", "allTimeCompleted", "allTimeRescheduled"
    };
    for (Task task : sorted) {
      int[] values = counts.getOrDefault(task.id, new int[4]);
      JSONObject project = projects.get(task.projectId);
      JSONObject item =
          new JSONObject()
              .put("taskId", task.id)
              .put("name", task.content)
              .put("projectId", task.projectId)
              .put(
                  "projectName",
                  project == null
                      ? "Unknown project"
                      : project.optString("name", "Unknown project"))
              .put("color", project == null ? "grey" : project.optString("color", "grey"));
      for (int i = 0; i < keys.length; i++) {
        item.put(keys[i], values[i]);
        totals[i] += values[i];
      }
      int denominator = values[2] + values[3];
      item.put(
          "reliability",
          denominator == 0
              ? JSONObject.NULL
              : new java.math.BigDecimal(((double) values[2] / denominator) * 100)
                  .setScale(2, java.math.RoundingMode.HALF_EVEN)
                  .doubleValue());
      items.put(item);
    }
    JSONObject total = new JSONObject();
    for (int i = 0; i < keys.length; i++) total.put(keys[i], totals[i]);
    for (int i = 0; i < history.length; i++) {
      LocalDate start = weekStart.minusWeeks(8 - i);
      weeks.put(
          new JSONObject()
              .put("label", start + " to " + start.plusDays(6))
              .put("completed", history[i][0])
              .put("rescheduled", history[i][1]));
    }
    return new JSONObject()
        .put("weekBeg", weekStart.minusWeeks(1).toString())
        .put("weekEnd", weekStart.minusDays(1).toString())
        .put("trackedCount", tracked.size())
        .put("items", items)
        .put("history", weeks)
        .put("totals", total);
  }

  private static void addHabitEvent(
      Map<String, int[]> counts,
      int[][] history,
      String task,
      LocalDate date,
      LocalDate weekStart,
      int kind) {
    int[] values = counts.computeIfAbsent(task, ignored -> new int[4]);
    values[kind + 2]++;
    if (!date.isBefore(weekStart.minusWeeks(1)) && date.isBefore(weekStart)) values[kind]++;
    long days = java.time.temporal.ChronoUnit.DAYS.between(weekStart.minusWeeks(8), date);
    if (days >= 0 && days < 56) history[(int) (days / 7)][kind]++;
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
      id = TodoistClient.parentId(project);
    }
    Collections.reverse(parts);
    return parts.isEmpty() ? "Unknown project" : String.join(" / ", parts);
  }

  static String activityProjectId(JSONObject event, Map<String, JSONObject> projects) {
    String primary =
        event.isNull("parent_project_id") ? "" : event.optString("parent_project_id", "");
    String modern =
        event.isNull("v2_parent_project_id") ? "" : event.optString("v2_parent_project_id", "");
    if (!projects.containsKey(primary) && projects.containsKey(modern)) return modern;
    return primary.isEmpty() ? modern : primary;
  }

  static String rootName(
      String id,
      Map<String, JSONObject> projects,
      JSONObject mappings,
      JSONObject projectMappings,
      java.util.Set<String> promoted) {
    String resolved =
        resolveRoot(id, projects, mappings, projectMappings, promoted, new java.util.HashSet<>());
    if (resolved != null) return resolved;
    // Ignore a cyclic manual assignment rather than merging unrelated projects.
    String name = "Unknown project";
    java.util.Set<String> visited = new java.util.HashSet<>();
    while (!id.isEmpty() && visited.add(id)) {
      JSONObject project = projects.get(id);
      if (project == null) break;
      name = rootLabel(project, projects);
      if (project.optBoolean("is_archived") && promoted.contains(project.optString("name")))
        return name;
      id = TodoistClient.parentId(project);
    }
    return name;
  }

  private static String resolveRoot(
      String id,
      Map<String, JSONObject> projects,
      JSONObject mappings,
      JSONObject projectMappings,
      java.util.Set<String> promoted,
      java.util.Set<String> assignments) {
    if (!assignments.add(id)) return null;
    String name = "Unknown project";
    java.util.Set<String> visited = new java.util.HashSet<>();
    List<JSONObject> ancestors = new ArrayList<>();
    while (!id.isEmpty() && visited.add(id)) {
      JSONObject project = projects.get(id);
      if (project == null) break;
      ancestors.add(project);
      name = project.optString("name", name);
      id = TodoistClient.parentId(project);
    }
    // A specific legacy choice beats an inherited ID rule; the ID wins on the
    // same project. With no ID rule, retain the original legacy precedence.
    JSONObject closerLegacy = null;
    boolean closerPromoted = false;
    for (var project : ancestors) {
      String sourceId = project.optString("id");
      JSONObject target = projectMappings.optJSONObject(sourceId);
      if (target != null) {
        String targetId = target.optString("targetId", "");
        String targetName = target.optString("targetName", "");
        if (!targetId.isEmpty() && !targetName.isEmpty()) {
          if (closerLegacy != null) {
            if (closerPromoted) return rootLabel(closerLegacy, projects);
            return mappedRoot(
                mappings.optString(closerLegacy.optString("name")),
                projects,
                mappings,
                projectMappings,
                promoted,
                assignments);
          }
          if (sourceId.equals(targetId)) return rootLabel(project, projects);
          if (!projects.containsKey(targetId)) return targetName + " · " + targetId;
          return resolveRoot(targetId, projects, mappings, projectMappings, promoted, assignments);
        }
      }
      if (closerLegacy == null && project.optBoolean("is_archived")) {
        String source = project.optString("name");
        if (promoted.contains(source)) {
          closerLegacy = project;
          closerPromoted = true;
        } else if (mappings.has(source) && !mappings.optString(source, source).equals(source)) {
          closerLegacy = project;
        }
      }
    }
    for (var project : ancestors)
      if (project.optBoolean("is_archived") && promoted.contains(project.optString("name")))
        return rootLabel(project, projects);
    for (var project : ancestors) {
      String source = project.optString("name");
      if (project.optBoolean("is_archived") && mappings.has(source)) {
        String target = mappings.optString(source, name);
        if (!target.equals(source))
          return mappedRoot(target, projects, mappings, projectMappings, promoted, assignments);
      }
    }
    return mappings.has(name) && !mappings.optString(name, name).equals(name)
        ? mappedRoot(
            mappings.optString(name, name),
            projects,
            mappings,
            projectMappings,
            promoted,
            assignments)
        : ancestors.isEmpty() ? name : rootLabel(ancestors.get(ancestors.size() - 1), projects);
  }

  private static String rootLabel(JSONObject project, Map<String, JSONObject> projects) {
    String name = project.optString("name", "Unknown project");
    String id = project.optString("id", "");
    for (var other : projects.values())
      if (!id.equals(other.optString("id")) && name.equals(other.optString("name")))
        return name + " · " + id;
    return name;
  }

  private static String mappedRoot(
      String target,
      Map<String, JSONObject> projects,
      JSONObject mappings,
      JSONObject projectMappings,
      java.util.Set<String> promoted,
      java.util.Set<String> assignments) {
    String active = null, archived = null;
    int activeMatches = 0, archivedMatches = 0;
    for (var entry : projects.entrySet()) {
      JSONObject project = entry.getValue();
      if (!target.equals(project.optString("name"))) continue;
      if (project.optBoolean("is_archived")) {
        archived = entry.getKey();
        archivedMatches++;
      } else {
        active = entry.getKey();
        activeMatches++;
      }
    }
    // Match desktop's preference for a unique active project. Do not guess
    // between duplicates; a missing target remains an explicit named bucket.
    String id =
        activeMatches == 1 ? active : activeMatches == 0 && archivedMatches == 1 ? archived : null;
    return id == null
        ? target
        : resolveRoot(id, projects, mappings, projectMappings, promoted, assignments);
  }
}
