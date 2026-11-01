package com.todoistassistant;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

/** Read-only API client. All requests stay on the worker thread. */
final class TodoistClient {
    private final String token;
    TodoistClient(String token) { this.token = token; }

    JSONObject get(String path) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) URI.create("https://api.todoist.com/api/v1/" + path).toURL().openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(30000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Authorization", "Bearer " + token);
        try {
            int status = connection.getResponseCode();
            if (status == 401 || status == 403) throw new IOException("Todoist rejected the token. Check API access in Settings.");
            if (status == 429) throw new IOException("Todoist rate limit reached. Try syncing again later.");
            if (status != 200) throw new IOException("Todoist request failed (HTTP " + status + ").");
            try (var stream = connection.getInputStream()) {
                var output = new java.io.ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int read;
                while ((read = stream.read(buffer)) != -1) output.write(buffer, 0, read);
                return new JSONObject(output.toString(StandardCharsets.UTF_8.name()));
            }
        } finally { connection.disconnect(); }
    }

    JSONArray list(String path) throws Exception {
        JSONArray all = new JSONArray();
        String cursor = "";
        Set<String> seen = new HashSet<>();
        do {
            JSONObject page = get(path + (path.contains("?") ? "&" : "?") + "limit=100" +
                (cursor.isEmpty() ? "" : "&cursor=" + URLEncoder.encode(cursor, StandardCharsets.UTF_8.name())));
            JSONArray items = page.getJSONArray("results");
            for (int i = 0; i < items.length(); i++) all.put(items.get(i));
            cursor = page.optString("next_cursor", "");
            if (cursor.equals("null")) cursor = "";
            if (!cursor.isEmpty() && !seen.add(cursor)) throw new IOException("Todoist returned a repeated pagination cursor.");
        } while (!cursor.isEmpty());
        return all;
    }

    JSONObject snapshot(JSONObject previous) throws Exception {
        JSONObject data = new JSONObject();

        data.put("projects", list("projects"));
        data.put("tasks", list("tasks"));
        java.time.Instant since = java.time.ZonedDateTime.now().minusWeeks(12)
            .with(java.time.DayOfWeek.MONDAY).toLocalDate().atStartOfDay(java.time.ZoneId.systemDefault()).toInstant();
        JSONArray cached = previous.optJSONArray("activities");
        java.util.Map<String, JSONObject> merged = new java.util.LinkedHashMap<>();
        java.time.Instant newest = null;
        if (cached != null) for (int i = 0; i < cached.length(); i++) {
            JSONObject item = cached.getJSONObject(i);
            merged.put(item.getString("id"), item);
            java.time.Instant time = java.time.Instant.parse(item.getString("event_date"));
            if (newest == null || time.isAfter(newest)) newest = time;
        }
        if (newest != null) since = newest.minus(java.time.Duration.ofDays(1));
        data.put("historyStart", previous.optString("historyStart", since.toString()));
        JSONArray fetched = list("activities?date_from=" +
            URLEncoder.encode(since.toString(), StandardCharsets.UTF_8.name()) + "&date_to=" +
            URLEncoder.encode(java.time.Instant.now().toString(), StandardCharsets.UTF_8.name()));
        for (int i = 0; i < fetched.length(); i++) {
            JSONObject item = fetched.getJSONObject(i);
            merged.put(item.getString("id"), item);
        }
        data.put("activities", new JSONArray(merged.values()));
        data.put("syncedAt", java.time.Instant.now().toString());
        data.put("schemaVersion", 1);
        return data;
    }
}
