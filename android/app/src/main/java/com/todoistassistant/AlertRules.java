package com.todoistassistant;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.json.JSONArray;
import org.json.JSONObject;

final class AlertRules {
  boolean enabled = true, fire = true, priority = true, due = true, deadline = true;
  String fireLabels = "fire, fire 🧯🚒";
  Set<Integer> priorities = new HashSet<>(Arrays.asList(4, 3));
  int priorityMin = 1, dueDays = 0, dueMin = 1, deadlineDays = 0, deadlineMin = 1;

  static AlertRules read(String json) {
    AlertRules rules = new AlertRules();
    try {
      JSONObject value = new JSONObject(json);
      rules.enabled = value.optBoolean("enabled", true);
      rules.fire = value.optBoolean("fire", true);
      rules.priority = value.optBoolean("priority", true);
      rules.due = value.optBoolean("due", true);
      rules.deadline = value.optBoolean("deadline", true);
      rules.fireLabels = value.optString("fireLabels", rules.fireLabels);
      JSONArray selected = value.optJSONArray("priorities");
      if (selected != null) {
        rules.priorities.clear();
        for (int i = 0; i < selected.length(); i++)
          if (selected.optInt(i) >= 1 && selected.optInt(i) <= 4)
            rules.priorities.add(selected.optInt(i));
      }
      rules.priorityMin = Math.max(1, value.optInt("priorityMin", 1));
      rules.dueDays = Math.max(0, value.optInt("dueDays"));
      rules.dueMin = Math.max(1, value.optInt("dueMin", 1));
      rules.deadlineDays = Math.max(0, value.optInt("deadlineDays"));
      rules.deadlineMin = Math.max(1, value.optInt("deadlineMin", 1));
    } catch (org.json.JSONException ignored) {
      /* Empty or legacy preferences use defaults. */
    }
    return rules;
  }

  String json() {
    try {
      return new JSONObject()
          .put("enabled", enabled)
          .put("fire", fire)
          .put("priority", priority)
          .put("due", due)
          .put("deadline", deadline)
          .put("fireLabels", fireLabels)
          .put("priorities", new JSONArray(priorities))
          .put("priorityMin", priorityMin)
          .put("dueDays", dueDays)
          .put("dueMin", dueMin)
          .put("deadlineDays", deadlineDays)
          .put("deadlineMin", deadlineMin)
          .toString();
    } catch (org.json.JSONException exception) {
      throw new IllegalStateException(exception);
    }
  }

  static final class Status {
    final int level, matches, fire, priority, due, deadline;

    Status(int level, int matches, int fire, int priority, int due, int deadline) {
      this.level = level;
      this.matches = matches;
      this.fire = fire;
      this.priority = priority;
      this.due = due;
      this.deadline = deadline;
    }
  }

  Status evaluate(List<DashboardModel.Task> tasks, LocalDate today, ZoneId zone) {
    if (!enabled) return new Status(0, 0, 0, 0, 0, 0);
    Set<String> labels = new HashSet<>();
    for (String label : fireLabels.split(","))
      if (!label.trim().isEmpty()) labels.add(label.trim().toLowerCase(Locale.ROOT));
    List<boolean[]> matches = new java.util.ArrayList<>();
    int[] counts = new int[4];
    for (var task : tasks) {
      boolean hasFire =
          fire
              && task.labels.stream()
                  .anyMatch(label -> labels.contains(label.trim().toLowerCase(Locale.ROOT)));
      boolean[] found = {
        hasFire,
        priority && priorities.contains(task.priority),
        due && within(task.due, today, dueDays),
        deadline && within(task.deadline, today, deadlineDays)
      };
      matches.add(found);
      for (int i = 0; i < counts.length; i++) if (found[i]) counts[i]++;
    }
    boolean[] triggered = {
      counts[0] > 0, counts[1] >= priorityMin, counts[2] >= dueMin, counts[3] >= deadlineMin
    };
    int total = 0;
    for (boolean[] found : matches) {
      for (int i = 0; i < found.length; i++)
        if (found[i] && triggered[i]) {
          total++;
          break;
        }
    }
    int level = triggered[0] ? 2 : triggered[1] || triggered[2] || triggered[3] ? 1 : 0;
    return new Status(level, total, counts[0], counts[1], counts[2], counts[3]);
  }

  private static boolean within(String value, LocalDate today, int days) {
    LocalDate date;
    try {
      // Todoist due dates are calendar dates, even when they contain a time and offset.
      String normalized = value.trim().replace(' ', 'T');
      try {
        date = LocalDate.parse(normalized);
      } catch (java.time.format.DateTimeParseException timed) {
        try {
          date = java.time.OffsetDateTime.parse(normalized).toLocalDate();
        } catch (java.time.format.DateTimeParseException noOffset) {
          date = java.time.LocalDateTime.parse(normalized).toLocalDate();
        }
      }
    } catch (RuntimeException invalid) {
      return false;
    }
    return date != null && !date.isAfter(today.plusDays(days));
  }
}
