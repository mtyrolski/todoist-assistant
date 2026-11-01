package com.todoistassistant;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.os.Bundle;
import android.text.InputType;
import android.util.AtomicFile;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

public class MainActivity extends Activity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final int background = Color.rgb(17, 19, 24), foreground = Color.rgb(232, 236, 242);
    private final int accent = Color.rgb(97, 244, 179);
    private JSONObject snapshot = new JSONObject();
    private LinearLayout content;
    private TextView status;
    private Button refresh;
    private TokenStore tokens;
    private boolean syncing;
    private int generation;
    private AtomicFile cache;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        tokens = new TokenStore(this);
        cache = new AtomicFile(new File(getFilesDir(), "dashboard-v1.json"));
        try {
            snapshot = new JSONObject(new String(cache.readFully(), StandardCharsets.UTF_8));
        } catch (Exception ignored) { /* First launch or damaged cache: sync can recover. */ }
        render();
        try { if (!tokens.load().isEmpty()) sync(tokens.load(), false); }
        catch (Exception exception) { status.setText("Token could not be unlocked. Open Settings to enter it again."); }
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size) {
        TextView view = new TextView(this);
        view.setText(value); view.setTextSize(size); view.setTextColor(foreground);
        view.setPadding(0, dp(8), 0, dp(8));
        content.addView(view);
        return view;
    }
    private Button button(String value, View.OnClickListener action) {
        Button button = new Button(this); button.setText(value); button.setAllCaps(false);
        button.setOnClickListener(action); content.addView(button); return button;
    }
    private void heading(String value) { text(value, 23).setTextColor(accent); }
    private JSONArray array(String key) { return snapshot.optJSONArray(key) == null ? new JSONArray() : snapshot.optJSONArray(key); }

    private void render() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true); scroll.setBackgroundColor(background);
        content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(20), dp(24), dp(20), dp(24));
        scroll.addView(content);
        // Android 15 draws edge-to-edge; keep content out of status/navigation bars.
        scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                var bars = insets.getInsets(WindowInsets.Type.systemBars());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            } else view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(scroll);
        text("Todoist Assistant", 30);
        status = text(snapshot.has("syncedAt") ? "Saved on device · " + snapshot.optString("syncedAt") : "Enter your Todoist API token in Settings to start.", 14);
        refresh = button(syncing ? "Syncing…" : "Sync now", view -> {
            try { String token = tokens.load(); if (token.isEmpty()) settings(); else sync(token, false); }
            catch (Exception exception) { status.setText("Could not unlock the saved token. Enter it again in Settings."); }
        });
        refresh.setEnabled(!syncing);
        button("Settings", view -> settings());
        if (!snapshot.has("tasks")) return;
        try { dashboard(); }
        catch (Exception exception) { text("Saved data could not be displayed. Sync again to recover it.", 16); }
    }

    private List<CompletionLedger.Event> completions() throws Exception {
        List<CompletionLedger.Event> events = new ArrayList<>();
        JSONArray activity = array("activities");
        for (int i = 0; i < activity.length(); i++) {
            JSONObject item = activity.getJSONObject(i);
            if (!item.optString("object_type").equals("item")) continue;
            JSONObject extra = item.optJSONObject("extra_data");
            if (extra == null) extra = new JSONObject();
            JSONObject due = extra.optJSONObject("due");
            boolean recurring = extra.optBoolean("is_recurring") || extra.optBoolean("sub_tasks_reset") ||
                (due != null && due.optBoolean("is_recurring"));
            events.add(new CompletionLedger.Event(item.getString("id"), item.getString("object_id"),
                item.getString("event_type"), Instant.parse(item.getString("event_date")), recurring));
        }
        return CompletionLedger.effective(events);
    }

    private void dashboard() throws Exception {
        JSONArray tasks = array("tasks"), projects = array("projects"), activity = array("activities");
        Map<String, String> projectNames = new HashMap<>();
        for (int i = 0; i < projects.length(); i++) {
            JSONObject project = projects.getJSONObject(i);
            projectNames.put(project.getString("id"), project.getString("name"));
        }
        int[] priorities = new int[4];
        int fire = 0;
        for (int i = 0; i < tasks.length(); i++) {
            JSONObject task = tasks.getJSONObject(i);
            priorities[4 - Math.max(1, Math.min(4, task.optInt("priority", 1)))]++;
            JSONArray labels = task.optJSONArray("labels");
            if (labels != null) for (int j = 0; j < labels.length(); j++)
                if (labels.getString(j).trim().toLowerCase(java.util.Locale.ROOT).startsWith("fire")) { fire++; break; }
        }
        SharedPreferences rules = getSharedPreferences("rules", MODE_PRIVATE);
        int urgent = (rules.getBoolean("p1", true) ? priorities[0] : 0) + (rules.getBoolean("p2", true) ? priorities[1] : 0);
        heading("Active tasks");
        TextView urgency = text(rules.getBoolean("fire", true) && fire > 0 ? "Urgent · " + fire + " fire tasks" :
            urgent > 0 ? "Attention needed · " + urgent + " priority tasks" : "All clear", 20);
        urgency.setTextColor(rules.getBoolean("fire", true) && fire > 0 ? Color.rgb(255, 119, 119) : urgent > 0 ? Color.rgb(244, 211, 94) : accent);
        text(tasks.length() + " active  ·  P1 " + priorities[0] + "  ·  P2 " + priorities[1] + "  ·  P3 " + priorities[2] + "  ·  P4 " + priorities[3], 16);

        heading("Completed from local history");
        List<CompletionLedger.Event> effective = completions();
        LocalDate monday = LocalDate.now().with(DayOfWeek.MONDAY);
        int[] weeks = new int[9];
        for (CompletionLedger.Event event : effective) {
            long days = java.time.temporal.ChronoUnit.DAYS.between(monday.minusWeeks(8), event.date.atZone(ZoneId.systemDefault()).toLocalDate());
            if (days >= 0 && days < 63) weeks[(int) (days / 7)]++;
        }
        // Estimate at the last successful sync, never advance stale/offline data to today's pace.
        Instant asOf = Instant.parse(snapshot.getString("syncedAt"));
        Instant begin = monday.atStartOfDay(ZoneId.systemDefault()).toInstant();
        Instant end = monday.plusWeeks(1).atStartOfDay(ZoneId.systemDefault()).toInstant();
        double fraction = Duration.between(begin, asOf).toMillis() / (double) Duration.between(begin, end).toMillis();
        double[] history = new double[8];
        for (int i = 0; i < 8; i++) history[i] = weeks[i];
        int forecast = fraction <= 0 ? weeks[8] : Forecast.total(weeks[8], history, fraction);
        text("This week so far: " + weeks[8] + (fraction <= 0 ? "  ·  sync needed" : "  ·  forecast: " + forecast), 20);
        text("Ordinary completions are cancelled when undone; recurring occurrences remain counted. History starts " + snapshot.optString("historyStart") + ".", 14);
        View chart = new WeeklyChart(weeks, forecast, monday);
        chart.setContentDescription("Weekly completed tasks, last nine weeks. This week " + weeks[8] + ", forecast " + forecast);
        content.addView(chart, new LinearLayout.LayoutParams(-1, dp(240)));
        for (int i = 8; i >= 5; i--) text(monday.minusWeeks(8 - i) + " · " + weeks[i] + " completed", 15);

        int undone = 0;
        for (int i = 0; i < activity.length(); i++) {
            JSONObject item = activity.getJSONObject(i);
            if (item.optString("event_type").equals("uncompleted") &&
                !Instant.parse(item.getString("event_date")).atZone(ZoneId.systemDefault()).toLocalDate().isBefore(monday)) undone++;
        }
        text("Undone completions this week: " + undone, 16);
        heading("Projects and tasks");
        for (int i = 0; i < projects.length(); i++) {
            JSONObject project = projects.getJSONObject(i);
            String id = project.getString("id");
            List<JSONObject> projectTasks = new ArrayList<>();
            for (int j = 0; j < tasks.length(); j++) if (tasks.getJSONObject(j).optString("project_id").equals(id)) projectTasks.add(tasks.getJSONObject(j));
            projectTasks.sort(Comparator.comparingInt(task -> -task.optInt("priority", 1)));
            String parent = projectNames.get(project.optString("parent_id"));
            String title = (parent == null ? "" : parent + " / ") + project.getString("name");
            Button toggle = button(title + " · " + projectTasks.size(), null);
            TextView details = text("", 16);
            StringBuilder lines = new StringBuilder();
            for (JSONObject task : projectTasks) {
                JSONObject due = task.optJSONObject("due");
                lines.append("P").append(5 - task.optInt("priority", 1)).append("  ").append(task.optString("content"));
                if (due != null) lines.append("\nDue: ").append(due.optString("date"));
                lines.append("\n\n");
            }
            details.setText(lines.length() == 0 ? "No active tasks" : lines.toString().trim());
            details.setVisibility(View.GONE);
            toggle.setOnClickListener(view -> details.setVisibility(details.getVisibility() == View.GONE ? View.VISIBLE : View.GONE));
        }
        heading("Recent activity");
        List<JSONObject> recent = new ArrayList<>();
        for (int i = 0; i < activity.length(); i++) recent.add(activity.getJSONObject(i));
        recent.sort(Comparator.comparing((JSONObject event) -> event.optString("event_date")).reversed());
        for (int i = 0; i < Math.min(30, recent.size()); i++) {
            JSONObject event = recent.get(i), extra = event.optJSONObject("extra_data");
            text(event.optString("event_type") + " · " + (extra == null ? "" : extra.optString("content", extra.optString("name"))) +
                "\n" + event.optString("event_date"), 15);
        }
    }

    private void settings() {
        EditText input = new EditText(this);
        input.setHint("Todoist API token (leave blank to keep current)");
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        new AlertDialog.Builder(this).setTitle("Connect Todoist").setView(input)
            .setMessage("Token stays encrypted on this device. Sync only reads Todoist; cached data works offline.")
            .setPositiveButton("Save and sync", (dialog, which) -> {
                String token = input.getText().toString().trim();
                if (!token.isEmpty()) sync(token, true);
            }).setNeutralButton("Alert rules", (dialog, which) -> rules())
            .setNegativeButton("Disconnect and clear data", (dialog, which) -> {
                generation++; syncing = false; tokens.clear(); cache.delete(); snapshot = new JSONObject(); render();
            }).show();
    }
    private void rules() {
        SharedPreferences prefs = getSharedPreferences("rules", MODE_PRIVATE);
        String[] keys = {"fire", "p1", "p2"};
        boolean[] checked = {prefs.getBoolean("fire", true), prefs.getBoolean("p1", true), prefs.getBoolean("p2", true)};
        new AlertDialog.Builder(this).setTitle("Local alert rules")
            .setMultiChoiceItems(new String[] {"Red alert for fire labels", "Attention for P1", "Attention for P2"}, checked,
                (dialog, index, value) -> checked[index] = value)
            .setPositiveButton("Save", (dialog, which) -> {
                var edit = prefs.edit(); for (int i = 0; i < keys.length; i++) edit.putBoolean(keys[i], checked[i]); edit.apply(); render();
            }).setNegativeButton("Cancel", null).show();
    }
    private void sync(String token, boolean newAccount) {
        if (syncing) return;
        syncing = true; refresh.setEnabled(false); refresh.setText("Syncing…");
        status.setText("Fetching Todoist data. Saved data stays available while syncing.");
        int request = ++generation;
        JSONObject previous = newAccount ? new JSONObject() : snapshot;
        worker.execute(() -> {
            try {
                JSONObject next = new TodoistClient(token).snapshot(previous);
                runOnUiThread(() -> {
                    if (isDestroyed() || request != generation) return;
                    try {
                        tokens.save(token);
                        var output = cache.startWrite();
                        try { output.write(next.toString().getBytes(StandardCharsets.UTF_8)); cache.finishWrite(output); }
                        catch (Exception error) { cache.failWrite(output); throw error; }
                        snapshot = next; syncing = false; render();
                    } catch (Exception exception) { failed("Could not save data on this device. Try syncing again."); }
                });
            } catch (Exception exception) {
                runOnUiThread(() -> { if (!isDestroyed() && request == generation) failed(exception.getMessage()); });
            }
        });
    }
    private void failed(String message) {
        syncing = false; refresh.setEnabled(true); refresh.setText("Sync now");
        status.setText("Sync failed: " + message + " Saved data is unchanged.");
    }
    @Override protected void onDestroy() { generation++; worker.shutdownNow(); super.onDestroy(); }

    private final class WeeklyChart extends View {
        private final int[] weeks;
        private final int forecast;
        private final LocalDate monday;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        WeeklyChart(int[] weeks, int forecast, LocalDate monday) { super(MainActivity.this); this.weeks = weeks; this.forecast = forecast; this.monday = monday; }
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int max = Math.max(1, forecast);
            for (int count : weeks) max = Math.max(max, count);
            float left = dp(24), right = getWidth() - dp(24), top = dp(24), bottom = getHeight() - dp(44);
            paint.setStrokeWidth(dp(2)); paint.setColor(Color.rgb(244, 211, 94)); paint.setTextSize(dp(11));
            float lastX = 0, lastY = 0;
            for (int i = 0; i < weeks.length; i++) {
                float x = left + (right - left) * i / 8, y = bottom - (bottom - top) * weeks[i] / max;
                if (i > 0) canvas.drawLine(lastX, lastY, x, y, paint);
                paint.setStyle(i == 8 ? Paint.Style.STROKE : Paint.Style.FILL);
                canvas.drawCircle(x, y, dp(i == 8 ? 6 : 3), paint);
                paint.setStyle(Paint.Style.FILL);
                canvas.drawText(String.valueOf(weeks[i]), x - dp(9), y - dp(10), paint);
                if (i % 2 == 0) canvas.drawText(monday.minusWeeks(8 - i).toString().substring(5), x - dp(15), bottom + dp(25), paint);
                lastX = x; lastY = y;
            }
            float forecastY = bottom - (bottom - top) * forecast / max;
            canvas.drawCircle(right, forecastY, dp(6), paint);
        }
    }
}
