package com.todoistassistant;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.json.JSONArray;
import org.json.JSONObject;

/** Compact plot inputs derived from the saved activity ledger and current tasks. */
final class PlotData {
  private static final String UNKNOWN_PROJECT_ID = "__unknown_project__";
  private static final Set<String> TYPES =
      Set.of("added", "completed", "uncompleted", "updated", "deleted", "rescheduled");

  private static final class Day {
    final Map<String, Integer> counts = new HashMap<>();
    final Map<String, Integer> projects = new HashMap<>();
    final int[] hours = new int[24];
    int effective;
  }

  private static final class Item {
    final JSONObject data;
    final Instant time;
    final LocalDate day;

    Item(JSONObject data, Instant time, ZoneId zone) {
      this.data = data;
      this.time = time;
      day = time.atZone(zone).toLocalDate();
    }
  }

  static JSONObject build(
      JSONObject snapshot,
      Clock clock,
      Instant historyAsOf,
      Map<String, JSONObject> projects,
      JSONObject mappings,
      Set<String> promoted,
      LocalDate firstWeek,
      List<CompletionLedger.Event> completed,
      List<JSONObject> activities)
      throws Exception {
    ZoneId zone = clock.getZone();
    TreeMap<LocalDate, Day> daily = new TreeMap<>();
    Map<String, Instant> added = new HashMap<>(), lastCompleted = new HashMap<>();
    Map<String, String> completionProject = new HashMap<>();
    Map<String, Instant> firstProjectEvent = new HashMap<>(), lastProjectEvent = new HashMap<>();
    Map<String, Instant> archivedAt = new HashMap<>(), unarchivedAt = new HashMap<>();
    Map<String, TreeMap<LocalDate, Integer>> projectDailyEvents = new HashMap<>();
    Map<String, TreeMap<LocalDate, Integer>> projectDailyCompletions = new HashMap<>();
    List<Item> itemEvents = new ArrayList<>();
    for (JSONObject event : activities) {
      Instant time = Instant.parse(event.getString("event_date"));
      String kind = event.optString("event_type"), objectType = event.optString("object_type");
      JSONObject extra = event.optJSONObject("extra_data");
      if (extra == null) extra = new JSONObject();
      String plotKind =
          kind.equals("updated") && extra.has("due_date") && extra.has("last_due_date")
              ? "rescheduled"
              : kind;
      if (TYPES.contains(plotKind)) {
        ZonedDateTime local = time.atZone(zone);
        Day day = daily.computeIfAbsent(local.toLocalDate(), ignored -> new Day());
        day.counts.merge(plotKind, 1, Integer::sum);
        day.hours[local.getHour()]++;
      }
      String projectId = event.optString("parent_project_id");
      if (objectType.equals("project")) {
        projectId = event.optString("object_id");
        if (kind.equals("archived") && !projectId.isEmpty())
          archivedAt.merge(projectId, time, PlotData::later);
        if (kind.equals("unarchived") && !projectId.isEmpty())
          unarchivedAt.merge(projectId, time, PlotData::later);
      }
      if (objectType.equals("item") && projectId.isEmpty()) projectId = UNKNOWN_PROJECT_ID;
      if (!projectId.isEmpty()) {
        firstProjectEvent.merge(projectId, time, PlotData::earlier);
        lastProjectEvent.merge(projectId, time, PlotData::later);
        projectDailyEvents
            .computeIfAbsent(projectId, ignored -> new TreeMap<>())
            .merge(time.atZone(zone).toLocalDate(), 1, Integer::sum);
      }
      if (!objectType.equals("item")) continue;
      String taskId = event.optString("object_id");
      if (kind.equals("added") && !taskId.isEmpty()) added.merge(taskId, time, PlotData::earlier);
      if (kind.equals("completed"))
        completionProject.put(
            String.valueOf(event.get("id")), event.optString("parent_project_id"));
      itemEvents.add(new Item(event, time, zone));
    }

    Map<String, Map<String, Integer>> projectWeeks = new HashMap<>();
    for (var event : completed) {
      LocalDate date = event.date.atZone(zone).toLocalDate();
      daily.computeIfAbsent(date, ignored -> new Day()).effective++;
      lastCompleted.merge(event.taskId, event.date, PlotData::later);
      String projectId = completionProject.getOrDefault(event.id, "");
      if (projectId.isEmpty()) projectId = UNKNOWN_PROJECT_ID;
      projectDailyCompletions
          .computeIfAbsent(projectId, ignored -> new TreeMap<>())
          .merge(date, 1, Integer::sum);
      daily
          .get(date)
          .projects
          .merge(DashboardModel.rootName(projectId, projects, mappings, promoted), 1, Integer::sum);
      long days = ChronoUnit.DAYS.between(firstWeek, date);
      if (!projectId.isEmpty() && days >= 0)
        projectWeeks
            .computeIfAbsent(projectId, ignored -> new HashMap<>())
            .merge(String.valueOf(days / 7), 1, Integer::sum);
    }
    JSONArray dailyRows = new JSONArray(), lifespans = new JSONArray();
    for (var entry : daily.entrySet())
      dailyRows.put(
          new JSONObject()
              .put("date", entry.getKey().toString())
              .put("counts", new JSONObject(entry.getValue().counts))
              .put("projects", new JSONObject(entry.getValue().projects))
              .put("hours", new JSONArray(entry.getValue().hours))
              .put("effectiveCompletions", entry.getValue().effective));
    for (var entry : lastCompleted.entrySet()) {
      Instant begin = added.get(entry.getKey());
      if (begin == null || !entry.getValue().isAfter(begin)) continue;
      lifespans.put(
          new JSONObject()
              .put("completedAt", entry.getValue().atZone(zone).toLocalDate().toString())
              .put("seconds", Duration.between(begin, entry.getValue()).toMillis() / 1000.0));
    }

    JSONArray rawTasks = snapshot.getJSONArray("tasks");
    Map<String, Integer> openByProject = new HashMap<>();
    for (int i = 0; i < rawTasks.length(); i++) {
      JSONObject task = rawTasks.getJSONObject(i);
      if (!task.optBoolean("checked") && !task.optBoolean("is_deleted"))
        openByProject.merge(task.optString("project_id"), 1, Integer::sum);
    }
    JSONArray hierarchy = new JSONArray();
    for (var entry : projects.entrySet()) {
      String id = entry.getKey();
      JSONObject project = entry.getValue();
      Instant archive = archivedAt.get(id), reopen = unarchivedAt.get(id);
      if (!project.optBoolean("is_archived")
          || (reopen != null && (archive == null || !archive.isAfter(reopen)))) archive = null;
      String createdAt = date(project.optString("created_at"), zone);
      String createdAtSource = "metadata";
      if (createdAt.isEmpty()) {
        createdAt = date(firstProjectEvent.get(id), zone);
        createdAtSource = createdAt.isEmpty() ? "unknown" : "activity";
      }
      hierarchy.put(
          new JSONObject()
              .put("id", id)
              .put("metadataKnown", true)
              .put("name", project.optString("name", "Unknown project"))
              .put("parentId", TodoistClient.parentId(project))
              .put("rootName", DashboardModel.rootName(id, projects, mappings, promoted))
              .put("color", project.optString("color", "grey"))
              .put("archived", project.optBoolean("is_archived"))
              .put("createdAt", createdAt)
              .put("createdAtSource", createdAtSource)
              .put("updatedAt", date(project.optString("updated_at"), zone))
              .put("lastEventAt", date(lastProjectEvent.get(id), zone))
              .put("archivedAt", date(archive, zone))
              .put("openTasks", openByProject.getOrDefault(id, 0))
              .put("dailyEvents", dailyCounts(projectDailyEvents.get(id)))
              .put("dailyCompletions", dailyCounts(projectDailyCompletions.get(id)))
              .put("weeklyCounts", new JSONObject(projectWeeks.getOrDefault(id, Map.of()))));
    }
    Set<String> unknownProjects = new HashSet<>(projectDailyEvents.keySet());
    unknownProjects.addAll(projectWeeks.keySet());
    unknownProjects.addAll(openByProject.keySet());
    for (String id : unknownProjects)
      if (!id.isEmpty() && !projects.containsKey(id))
        hierarchy.put(
            new JSONObject()
                .put("id", id)
                .put("metadataKnown", false)
                .put("name", "Unknown project")
                .put("parentId", "")
                .put("rootName", "Unknown project")
                .put("color", "grey")
                .put("archived", false)
                .put("createdAt", date(firstProjectEvent.get(id), zone))
                .put("createdAtSource", firstProjectEvent.containsKey(id) ? "activity" : "unknown")
                .put("updatedAt", "")
                .put("lastEventAt", date(lastProjectEvent.get(id), zone))
                .put("archivedAt", "")
                .put("openTasks", openByProject.getOrDefault(id, 0))
                .put("dailyEvents", dailyCounts(projectDailyEvents.get(id)))
                .put("dailyCompletions", dailyCounts(projectDailyCompletions.get(id)))
                .put("weeklyCounts", new JSONObject(projectWeeks.getOrDefault(id, Map.of()))));
    String rawHistoryStart = snapshot.optString("historyStart");
    LocalDate historyStart = DashboardModel.localDate(rawHistoryStart, zone);
    if (!snapshot.optBoolean("historyComplete") && historyStart != null) {
      try {
        Instant start = Instant.parse(rawHistoryStart);
        if (start.isAfter(historyStart.atStartOfDay(zone).toInstant()))
          historyStart = historyStart.plusDays(1);
      } catch (java.time.format.DateTimeParseException dateOnly) {
        // Legacy date-only coverage already names its first full calendar day.
      }
    }
    Instant syncedAt = Instant.parse(snapshot.getString("syncedAt"));
    boolean staleActivity = historyAsOf.isBefore(syncedAt);
    LocalDate taskDate = syncedAt.atZone(zone).toLocalDate();
    return new JSONObject()
        .put("historyComplete", snapshot.optBoolean("historyComplete"))
        .put("historyStart", historyStart == null ? "" : historyStart.toString())
        .put("historyAsOf", historyAsOf.atZone(zone).toLocalDate().toString())
        .put("dailyActivity", dailyRows)
        .put("lifespans", lifespans)
        .put("hierarchy", hierarchy)
        .put(
            "taskCounts",
            taskCounts(
                rawTasks,
                staleActivity ? new ArrayList<>() : itemEvents,
                taskDate,
                historyStart,
                zone));
  }

  private static JSONArray dailyCounts(Map<LocalDate, Integer> counts) throws Exception {
    JSONArray rows = new JSONArray();
    if (counts != null)
      for (var entry : counts.entrySet())
        rows.put(
            new JSONObject().put("date", entry.getKey().toString()).put("count", entry.getValue()));
    return rows;
  }

  private static JSONArray taskCounts(
      JSONArray rawTasks, List<Item> events, LocalDate today, LocalDate historyStart, ZoneId zone)
      throws Exception {
    Map<String, Integer> active = new HashMap<>(), hints = new HashMap<>();
    Map<String, LocalDate> added = new HashMap<>();
    for (int i = 0; i < rawTasks.length(); i++) {
      JSONObject task = rawTasks.getJSONObject(i);
      if (task.optBoolean("checked") || task.optBoolean("is_deleted")) continue;
      String id = task.optString("id");
      if (id.isEmpty()) continue;
      active.put(id, priority(task.opt("priority"), 1));
      LocalDate date =
          DashboardModel.localDate(task.optString("added_at", task.optString("created_at")), zone);
      if (date != null && !date.isAfter(today)) added.put(id, date);
    }
    hints.putAll(active);
    LocalDate boundary = historyStart == null || historyStart.isAfter(today) ? today : historyStart;
    events.removeIf(item -> item.day.isAfter(today) || item.day.isBefore(boundary));
    if (events.isEmpty()) return new JSONArray().put(counts(today, active));
    events.sort(Comparator.comparing((Item item) -> item.time).reversed());
    for (Item item : events) {
      String id = item.data.optString("object_id"), kind = item.data.optString("event_type");
      if (id.isEmpty() || item.day.isAfter(today) || item.day.isBefore(boundary)) continue;
      JSONObject extra = item.data.optJSONObject("extra_data");
      if (extra == null) extra = new JSONObject();
      if (kind.equals("added")) added.merge(id, item.day, (a, b) -> a.isBefore(b) ? a : b);
      if (!hints.containsKey(id)) {
        if (extra.has("priority")) hints.put(id, priority(extra.opt("priority"), 1));
        else if (extra.has("last_priority")) hints.put(id, priority(extra.opt("last_priority"), 1));
      }
      if (!added.containsKey(id)) {
        LocalDate date = DashboardModel.localDate(extra.optString("date_added"), zone);
        if (date != null && !date.isAfter(today)) added.put(id, date);
      }
    }
    TreeMap<LocalDate, List<Item>> byDay = new TreeMap<>(Comparator.reverseOrder());
    Map<LocalDate, Set<String>> addedByDay = new HashMap<>();
    for (Item item : events)
      if (!item.day.isAfter(today) && !item.day.isBefore(boundary))
        byDay.computeIfAbsent(item.day, ignored -> new ArrayList<>()).add(item);
    for (var entry : added.entrySet()) {
      if (entry.getValue().isAfter(today) || entry.getValue().isBefore(boundary)) continue;
      addedByDay.computeIfAbsent(entry.getValue(), ignored -> new HashSet<>()).add(entry.getKey());
      byDay.computeIfAbsent(entry.getValue(), ignored -> new ArrayList<>());
    }
    TreeMap<LocalDate, JSONObject> rows = new TreeMap<>();
    LocalDate cursor = today;
    for (var entry : byDay.entrySet()) {
      LocalDate day = entry.getKey();
      while (!cursor.isBefore(day)) {
        rows.put(cursor, counts(cursor, active));
        cursor = cursor.minusDays(1);
      }
      for (Item event : entry.getValue()) {
        String id = event.data.optString("object_id"), kind = event.data.optString("event_type");
        if (id.isEmpty()) continue;
        JSONObject extra = event.data.optJSONObject("extra_data");
        if (extra == null) extra = new JSONObject();
        if ((kind.equals("completed") || kind.equals("deleted"))
            && !active.containsKey(id)
            && added.containsKey(id))
          active.put(id, priority(extra.opt("priority"), hints.getOrDefault(id, 1)));
        else if (kind.equals("added") || kind.equals("uncompleted")) active.remove(id);
        else if (kind.equals("updated") && extra.has("last_priority") && active.containsKey(id))
          active.put(id, priority(extra.opt("last_priority"), 1));
      }
      for (String id : addedByDay.getOrDefault(day, Set.of())) active.remove(id);
    }
    if (rows.isEmpty()) rows.put(today, counts(today, active));
    return new JSONArray(rows.values());
  }

  private static JSONObject counts(LocalDate day, Map<String, Integer> active) throws Exception {
    int[] counts = new int[4];
    for (int priority : active.values()) counts[4 - priority]++;
    return new JSONObject()
        .put("date", day.toString())
        .put("total", active.size())
        .put("p1", counts[0])
        .put("p2", counts[1])
        .put("p3", counts[2])
        .put("p4", counts[3]);
  }

  private static int priority(Object value, int fallback) {
    try {
      int number = Integer.parseInt(String.valueOf(value));
      return number >= 1 && number <= 4 ? number : fallback;
    } catch (NumberFormatException ignored) {
      return fallback;
    }
  }

  private static Instant earlier(Instant a, Instant b) {
    return a.isBefore(b) ? a : b;
  }

  private static Instant later(Instant a, Instant b) {
    return a.isAfter(b) ? a : b;
  }

  private static String date(Instant instant, ZoneId zone) {
    return instant == null ? "" : instant.atZone(zone).toLocalDate().toString();
  }

  private static String date(String value, ZoneId zone) {
    LocalDate parsed = DashboardModel.localDate(value, zone);
    return parsed == null ? "" : parsed.toString();
  }
}
