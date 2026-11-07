package com.todoistassistant;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
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

  interface Checkpoint {
    void save(JSONObject snapshot) throws Exception;
  }

  private final ApiTransport transport;
  private final Clock clock;
  private final Progress progress;

  TodoistClient(ApiTransport transport, Clock clock, Progress progress) {
    this.transport = transport;
    this.clock = clock;
    this.progress = progress;
    transport.setProgress(progress);
  }

  JSONArray list(String path, String label) throws Exception {
    JSONArray all = new JSONArray();
    Set<String> cursors = new HashSet<>();
    String cursor = "";
    progress.update(label + "…");
    do {
      if (Thread.currentThread().isInterrupted()) throw new SyncCancelledException();
      JSONObject page =
          transport.get(
              path
                  + (path.contains("?") ? "&" : "?")
                  + (path.startsWith("activities?") ? "limit=200" : "limit=100")
                  + (cursor.isEmpty() ? "" : "&cursor=" + encode(cursor)));
      JSONArray items = page.getJSONArray("results");
      for (int i = 0; i < items.length(); i++) all.put(items.getJSONObject(i));
      progress.update(label + " · " + all.length() + " loaded");
      Object next = page.opt("next_cursor");
      cursor = next == null || next == JSONObject.NULL ? "" : String.valueOf(next);
      if (!cursor.isEmpty() && !cursors.add(cursor))
        throw new IOException("Todoist repeated a page. Retry sync to recover safely.");
    } while (!cursor.isEmpty());
    return all;
  }

  JSONObject snapshot(JSONObject previous, boolean trustLegacyOwner) throws Exception {
    return snapshot(previous, trustLegacyOwner, ignored -> {});
  }

  JSONObject snapshot(JSONObject previous, boolean trustLegacyOwner, Checkpoint checkpoint)
      throws Exception {
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
    if (baseline.has("adjustments")) data.put("adjustments", baseline.getJSONObject("adjustments"));
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
    data.put("knownProjects", known);
    data.put("syncedAt", started.toString());
    data.put("schemaVersion", 2);
    Map<String, JSONObject> merged = new LinkedHashMap<>();
    Map<String, String> rounded = new HashMap<>();
    JSONArray cached = baseline.optJSONArray("activities");
    if (cached != null)
      for (int i = 0; i < cached.length(); i++) {
        JSONObject item = cached.getJSONObject(i);
        Instant.parse(item.getString("event_date"));
        Object id = item.get("id");
        boolean imprecise = id instanceof Double || id instanceof Float;
        String key = (imprecise ? "rounded:" : "") + id;
        merged.put(key, item);
        if (imprecise) rounded.put(eventIdentity(item, ((Number) id).doubleValue()), key);
      }
    Instant joined = parseInstant(user.optString("joined_at"), null);
    boolean joinDateKnown = joined != null;
    if (!joinDateKnown) joined = started.minus(Duration.ofDays(84));
    if (joined.isAfter(started)) joined = started;
    Instant historyStart = parseInstant(baseline.optString("historyStart"), started);
    if (historyStart.isAfter(started)) historyStart = started;
    Instant activitySyncedAt =
        parseInstant(
            baseline.optString("activitySyncedAt", baseline.optString("syncedAt")), started);
    boolean complete = baseline.optBoolean("historyComplete");
    boolean repairing = baseline.optBoolean("historyIdRepair");
    if (!rounded.isEmpty() && !repairing) {
      historyStart = started;
      complete = false;
      repairing = true;
    }
    data.put("historyIdRepair", repairing);
    boolean fetchedActivity = false;
    int historyWindows = 0;
    try {
      if (baseline.has("syncedAt")) {
        Instant recentStart = activitySyncedAt.minus(Duration.ofDays(1));
        fetchActivity(merged, rounded, recentStart, started, "Updating recent activity");
        fetchedActivity = true;
      }
      activitySyncedAt = started;
      data.put("activitySyncedAt", started.toString());
      while (!complete && historyStart.isAfter(joined)) {
        Instant from = historyStart.minus(Duration.ofDays(30));
        if (from.isBefore(joined)) from = joined;
        fetchActivity(
            merged,
            rounded,
            from,
            historyStart,
            "Loading history from " + from.toString().substring(0, 10));
        fetchedActivity = true;
        historyStart = from;
        complete = joinDateKnown && !historyStart.isAfter(joined);
        historyWindows++;
        if (historyWindows == 1 || historyWindows % 3 == 0 || complete) {
          data.put("historyStart", historyStart.toString());
          data.put("historyComplete", complete);
          data.put("activities", new JSONArray(merged.values()));
          discardReopenedParents(known, archived, baseline, merged.values());
          checkpoint.save(data);
        }
      }
      if (!complete && joinDateKnown) complete = true;
    } catch (DataAccessException unavailable) {
      data.put("activitySyncedAt", activitySyncedAt.toString());
      data.put(
          "activityUnavailable",
          !fetchedActivity
              && (!baseline.has("syncedAt") || baseline.optBoolean("activityUnavailable")));
      data.put(
          "activityWarning",
          "Activity access is unavailable for this account. Tasks and projects are saved; completion history was not refreshed.");
    }
    data.put("activities", new JSONArray(merged.values()));
    discardReopenedParents(known, archived, baseline, merged.values());
    data.put("historyStart", historyStart.toString());
    data.put("historyComplete", complete);
    if (!joinDateKnown && !complete && !data.has("activityWarning"))
      data.put(
          "activityWarning",
          "Todoist did not provide your account join date. Older activity may be missing.");
    if (complete && !rounded.isEmpty() && !data.has("activityWarning"))
      data.put(
          "activityWarning", "Some older saved events could not be matched to Todoist's history.");
    return data;
  }

  private void fetchActivity(
      Map<String, JSONObject> merged,
      Map<String, String> rounded,
      Instant from,
      Instant to,
      String label)
      throws Exception {
    while (to.isAfter(from)) {
      Instant start = to.minus(Duration.ofDays(365));
      if (start.isBefore(from)) start = from;
      JSONArray fetched =
          list(
              "activities?date_from="
                  + encode(start.toString())
                  + "&date_to="
                  + encode(to.toString()),
              label);
      Map<String, Integer> candidates = new HashMap<>();
      if (!rounded.isEmpty())
        for (int i = 0; i < fetched.length(); i++) {
          JSONObject item = fetched.getJSONObject(i);
          String identity = roundedIdentity(item);
          if (identity != null && rounded.containsKey(identity))
            candidates.merge(identity, 1, Integer::sum);
        }
      for (int i = 0; i < fetched.length(); i++) {
        JSONObject item = fetched.getJSONObject(i);
        Instant.parse(item.getString("event_date"));
        String identity = rounded.isEmpty() ? null : roundedIdentity(item);
        if (identity != null && candidates.getOrDefault(identity, 0) == 1) {
          String old = rounded.remove(identity);
          if (old != null) merged.remove(old);
        }
        merged.put(String.valueOf(item.get("id")), item);
      }
      to = start;
    }
  }

  private static String roundedIdentity(JSONObject event) {
    try {
      return eventIdentity(event, Double.parseDouble(String.valueOf(event.get("id"))));
    } catch (Exception invalid) {
      return null;
    }
  }

  private static String eventIdentity(JSONObject event, double roundedId) {
    return roundedId
        + "\u0000"
        + event.optString("object_id")
        + "\u0000"
        + event.optString("object_type")
        + "\u0000"
        + event.optString("event_type")
        + "\u0000"
        + event.optString("event_date")
        + "\u0000"
        + event.optString("parent_project_id");
  }

  private static Instant parseInstant(String value, Instant fallback) {
    try {
      return Instant.parse(value);
    } catch (Exception invalid) {
      return fallback;
    }
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

  private static void discardReopenedParents(
      JSONArray projects, JSONArray archived, JSONObject baseline, Iterable<JSONObject> events)
      throws Exception {
    String lastSync = baseline.optString("activitySyncedAt", baseline.optString("syncedAt", ""));
    if (lastSync.isEmpty()) return;
    Instant cutoff = Instant.parse(lastSync);
    Set<String> currentParents = new HashSet<>(), reopened = new HashSet<>();
    for (int i = 0; i < archived.length(); i++) {
      JSONObject project = archived.getJSONObject(i);
      if (!parentId(project).isEmpty()) currentParents.add(project.getString("id"));
    }
    for (JSONObject event : events)
      if (event.optString("object_type").equals("project")
          && event.optString("event_type").equals("unarchived")
          && Instant.parse(event.getString("event_date")).isAfter(cutoff))
        reopened.add(event.optString("object_id"));
    for (int i = 0; i < projects.length(); i++) {
      JSONObject project = projects.getJSONObject(i);
      String id = project.optString("id");
      if (project.optBoolean("is_archived")
          && reopened.contains(id)
          && !currentParents.contains(id)) {
        project.remove("parent_id");
        project.remove("v2_parent_id");
      }
    }
  }

  private static String encode(String value) throws Exception {
    return URLEncoder.encode(value, StandardCharsets.UTF_8.name());
  }
}
