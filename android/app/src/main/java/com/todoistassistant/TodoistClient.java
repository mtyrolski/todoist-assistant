package com.todoistassistant;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.json.JSONArray;
import org.json.JSONObject;

/** Assemble an account-scoped snapshot; callers commit only a fully fetched result. */
final class TodoistClient {
  interface Progress {
    void update(String message);
  }

  private final ApiTransport transport;
  private final Clock clock;
  private final Progress progress;

  TodoistClient(ApiTransport transport, Clock clock, Progress progress) {
    this.transport = transport;
    this.clock = clock;
    this.progress = progress;
  }

  JSONArray list(String path, String label) throws Exception {
    JSONArray all = new JSONArray();
    Set<String> cursors = new HashSet<>();
    String cursor = "";
    int pages = 0;
    do {
      if (Thread.currentThread().isInterrupted()) throw new SyncCancelledException();
      JSONObject page =
          transport.get(
              path
                  + (path.contains("?") ? "&" : "?")
                  + "limit=100"
                  + (cursor.isEmpty() ? "" : "&cursor=" + encode(cursor)));
      JSONArray items = page.getJSONArray("results");
      for (int i = 0; i < items.length(); i++) all.put(items.getJSONObject(i));
      progress.update(label + " · " + all.length() + " records · page " + ++pages);
      Object next = page.opt("next_cursor");
      cursor = next == null || next == JSONObject.NULL ? "" : String.valueOf(next);
      if (!cursor.isEmpty() && !cursors.add(cursor))
        throw new IOException("Todoist repeated a page. Retry sync to recover safely.");
    } while (!cursor.isEmpty());
    return all;
  }

  JSONObject snapshot(JSONObject previous, boolean trustLegacyOwner) throws Exception {
    Instant started = clock.instant();
    progress.update("Checking your account…");
    JSONObject user = transport.get("user");
    String userId = String.valueOf(user.get("id"));
    if (userId.trim().isEmpty() || userId.equals("null"))
      throw new IOException("Todoist returned an invalid account identity.");
    boolean sameAccount =
        userId.equals(previous.optString("userId"))
            || (!previous.has("userId") && trustLegacyOwner);
    JSONObject baseline = sameAccount ? previous : new JSONObject();
    JSONObject data = new JSONObject();
    data.put("userId", userId);
    data.put("projects", list("projects", "Loading projects"));
    data.put("tasks", list("tasks", "Loading active tasks"));
    JSONArray archived = new JSONArray();
    String namesSynced = baseline.optString("projectNamesSyncedAt", "1970-01-01T00:00:00Z");
    if (Duration.between(Instant.parse(namesSynced), started).toHours() >= 24) {
      try {
        archived = list("projects/archived", "Loading archived project names");
        namesSynced = started.toString();
      } catch (SyncCancelledException cancelled) {
        throw cancelled;
      } catch (IOException unavailable) {
        data.put(
            "metadataWarning",
            "Some archived project names are unavailable. Their completions remain included.");
      }
    }
    data.put("projectNamesSyncedAt", namesSynced);
    JSONArray known = knownProjects(baseline, archived, data.getJSONArray("projects"));
    Map<String, JSONObject> merged = new LinkedHashMap<>();
    Instant since =
        ZonedDateTime.now(clock)
            .minusWeeks(12)
            .with(DayOfWeek.MONDAY)
            .toLocalDate()
            .atStartOfDay(clock.getZone())
            .toInstant();
    JSONArray cached = baseline.optJSONArray("activities");
    Instant newest = null;
    if (cached != null)
      for (int i = 0; i < cached.length(); i++) {
        JSONObject item = cached.getJSONObject(i);
        Instant time = Instant.parse(item.getString("event_date"));
        merged.put(item.getString("id"), item);
        if (!time.isAfter(started) && (newest == null || time.isAfter(newest))) newest = time;
      }
    if (newest != null) since = newest.minus(Duration.ofDays(1));
    try {
      JSONArray fetched =
          list(
              "activities?date_from="
                  + encode(since.toString())
                  + "&date_to="
                  + encode(started.toString()),
              "Syncing activity");
      for (int i = 0; i < fetched.length(); i++) {
        JSONObject item = fetched.getJSONObject(i);
        Instant.parse(item.getString("event_date"));
        merged.put(item.getString("id"), item);
      }
      data.put("activitySyncedAt", started.toString());
    } catch (DataAccessException unavailable) {
      data.put(
          "activitySyncedAt",
          baseline.optString(
              "activitySyncedAt", baseline.optString("syncedAt", started.toString())));
      data.put(
          "activityUnavailable",
          !baseline.has("syncedAt") || baseline.optBoolean("activityUnavailable"));
      data.put(
          "activityWarning",
          "Activity access is unavailable for this account. Tasks and projects are saved; completion history was not refreshed.");
    }
    data.put("activities", new JSONArray(merged.values()));
    recoverArchivedParents(known, merged.values());
    data.put("knownProjects", known);
    data.put("historyStart", baseline.optString("historyStart", since.toString()));
    // The API range ended at 'started', not at the later time the last page arrived.
    data.put("syncedAt", started.toString());
    data.put("schemaVersion", 2);
    return data;
  }

  private static JSONArray knownProjects(JSONObject baseline, JSONArray archived, JSONArray current)
      throws Exception {
    Map<String, JSONObject> known = new LinkedHashMap<>();
    JSONArray old = baseline.optJSONArray("knownProjects");
    if (old == null) old = baseline.optJSONArray("projects");
    if (old != null)
      for (int i = 0; i < old.length(); i++) {
        JSONObject project = new JSONObject(old.getJSONObject(i).toString());
        known.put(project.getString("id"), project);
      }
    for (int i = 0; i < archived.length(); i++) {
      JSONObject project = new JSONObject(archived.getJSONObject(i).toString());
      JSONObject previous = known.get(project.getString("id"));
      if (parentId(project).isEmpty() && previous != null && !parentId(previous).isEmpty())
        project.put("parent_id", parentId(previous));
      project.put("is_archived", true);
      known.put(project.getString("id"), project);
    }
    for (int i = 0; i < current.length(); i++) {
      JSONObject project = current.getJSONObject(i);
      known.put(project.getString("id"), project);
    }
    return new JSONArray(known.values());
  }

  static String parentId(JSONObject project) {
    String parent = project.optString("parent_id", "");
    return parent.isEmpty() ? project.optString("v2_parent_id", "") : parent;
  }

  private static void recoverArchivedParents(JSONArray projects, Iterable<JSONObject> events)
      throws Exception {
    Map<String, JSONObject> byId = new LinkedHashMap<>();
    Map<String, JSONObject> latest = new LinkedHashMap<>();
    for (int i = 0; i < projects.length(); i++) {
      JSONObject project = projects.getJSONObject(i);
      byId.put(project.getString("id"), project);
    }
    for (JSONObject event : events) {
      if (!event.optString("object_type").equals("project")) continue;
      String id = event.optString("object_id");
      JSONObject previous = latest.get(id);
      if (previous == null
          || Instant.parse(event.getString("event_date"))
              .isAfter(Instant.parse(previous.getString("event_date")))) latest.put(id, event);
    }
    for (var entry : latest.entrySet()) {
      JSONObject project = byId.get(entry.getKey()), event = entry.getValue();
      String parent = event.optString("parent_project_id", "");
      if (project == null
          || !project.optBoolean("is_archived")
          || !parentId(project).isEmpty()
          || !event.optString("event_type").equals("archived")
          || !byId.containsKey(parent)) continue;
      Set<String> visited = new HashSet<>();
      visited.add(entry.getKey());
      String current = parent;
      while (!current.isEmpty() && visited.add(current) && byId.containsKey(current))
        current = parentId(byId.get(current));
      if (current.isEmpty() || !byId.containsKey(current)) project.put("parent_id", parent);
    }
  }

  private static String encode(String value) throws Exception {
    return URLEncoder.encode(value, StandardCharsets.UTF_8.name());
  }
}
