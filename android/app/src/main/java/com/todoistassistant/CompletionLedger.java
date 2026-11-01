package com.todoistassistant;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Same cache projection as todoist/core/completions.py; never mutates raw events. */
final class CompletionLedger {
  static final class Event {
    final String id, taskId, type;
    final Instant date;
    final Boolean recurring;

    Event(String id, String taskId, String type, Instant date, Boolean recurring) {
      this.id = id;
      this.taskId = taskId;
      this.type = type;
      this.date = date;
      this.recurring = recurring;
    }
  }

  static List<Event> effective(List<Event> input) {
    Map<String, Event> unique = new LinkedHashMap<>();
    for (Event event : input) unique.put(event.id, event);
    List<Event> ordered = new ArrayList<>(unique.values());
    ordered.sort(
        Comparator.comparing((Event event) -> event.date).thenComparing(event -> event.id));
    Map<String, Boolean> recurring = new HashMap<>();
    Set<String> cancelled = new HashSet<>();
    Map<String, java.util.Deque<String>> outstanding = new HashMap<>();
    for (Event event : ordered) {
      if (event.recurring != null) {
        if (!event.recurring.equals(recurring.getOrDefault(event.taskId, false)))
          outstanding.remove(event.taskId);
        recurring.put(event.taskId, event.recurring);
      }
      if (recurring.getOrDefault(event.taskId, false)) continue;
      var pending = outstanding.computeIfAbsent(event.taskId, key -> new java.util.ArrayDeque<>());
      if (event.type.equals("completed")) pending.addLast(event.id);
      if (event.type.equals("uncompleted") && !pending.isEmpty())
        cancelled.add(pending.removeLast());
    }
    ordered.removeIf(event -> cancelled.contains(event.id) || !event.type.equals("completed"));
    return ordered;
  }
}
