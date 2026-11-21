package com.todoistassistant;

import static org.junit.Assert.assertEquals;

import java.nio.file.Files;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public class CompletionConformanceTest {
  @Test
  public void androidAndPythonUseTheSameCountingContract() throws Exception {
    JSONArray scenarios =
        new JSONArray(
            new String(
                Files.readAllBytes(
                    java.nio.file.Paths.get(System.getProperty("completionFixtures"))),
                java.nio.charset.StandardCharsets.UTF_8));
    for (int i = 0; i < scenarios.length(); i++) {
      JSONObject scenario = scenarios.getJSONObject(i);
      List<CompletionLedger.Event> input = new ArrayList<>();
      JSONArray events = scenario.getJSONArray("events");
      for (int j = 0; j < events.length(); j++) {
        JSONObject event = events.getJSONObject(j);
        Boolean recurring =
            event.has("recurring")
                ? Boolean.valueOf(event.getBoolean("recurring"))
                : event.optBoolean("reset") ? Boolean.TRUE : null;
        input.add(
            new CompletionLedger.Event(
                event.getString("id"),
                event.getString("task"),
                event.getString("type"),
                Instant.parse(event.getString("date")),
                recurring));
      }
      List<String> actual = new ArrayList<>(), expected = new ArrayList<>();
      for (var event : CompletionLedger.effective(input)) actual.add(event.id);
      JSONArray completed = scenario.getJSONArray("completed");
      for (int j = 0; j < completed.length(); j++) expected.add(completed.getString(j));
      assertEquals(scenario.getString("name"), expected, actual);
    }
  }
}
