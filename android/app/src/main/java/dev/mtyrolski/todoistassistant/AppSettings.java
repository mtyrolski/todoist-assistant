package dev.mtyrolski.todoistassistant;

import android.content.Context;
import android.content.SharedPreferences;

final class AppSettings {
    static final String DEFAULT_SERVER_URL = "http://10.0.2.2:8000";
    static final String DEFAULT_AUTOMATION = "@ai-breakdown";
    static final int MIN_PERIODIC_MINUTES = 15;

    private static final String PREFS = "todoist_assistant";
    private static final String KEY_SERVER_URL = "server_url";
    private static final String KEY_TIMEZONE = "timezone";
    private static final String KEY_AUTOMATION = "automation";
    private static final String KEY_INTERVAL = "interval_minutes";

    private final SharedPreferences prefs;

    AppSettings(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    String serverUrl() {
        return prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL);
    }

    String timezone() {
        return prefs.getString(KEY_TIMEZONE, "");
    }

    String automation() {
        return prefs.getString(KEY_AUTOMATION, DEFAULT_AUTOMATION);
    }

    int intervalMinutes() {
        return Math.max(MIN_PERIODIC_MINUTES, prefs.getInt(KEY_INTERVAL, MIN_PERIODIC_MINUTES));
    }

    void saveConnection(String serverUrl, String timezone) {
        prefs.edit()
                .putString(KEY_SERVER_URL, clean(serverUrl, DEFAULT_SERVER_URL))
                .putString(KEY_TIMEZONE, clean(timezone, ""))
                .apply();
    }

    void saveBackground(String automation, int intervalMinutes) {
        prefs.edit()
                .putString(KEY_AUTOMATION, clean(automation, DEFAULT_AUTOMATION))
                .putInt(KEY_INTERVAL, Math.max(MIN_PERIODIC_MINUTES, intervalMinutes))
                .apply();
    }

    private static String clean(String value, String fallback) {
        String trimmed = value == null ? "" : value.trim();
        return trimmed.isEmpty() ? fallback : trimmed;
    }
}
