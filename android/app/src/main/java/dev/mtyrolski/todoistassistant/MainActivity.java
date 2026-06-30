package dev.mtyrolski.todoistassistant;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.ViewGroup;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.URLEncoder;
import java.util.Iterator;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

public final class MainActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());

    private AppSettings settings;
    private EditText serverUrlField;
    private EditText tokenField;
    private EditText timezoneField;
    private EditText automationField;
    private EditText intervalField;
    private TextView statusText;
    private TextView metricsText;
    private TextView automationText;
    private LinearLayout plotsContainer;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        settings = new AppSettings(this);
        buildUi();
        loadSavedSettings();
        refreshStatus();
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private void buildUi() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = column();
        root.setPadding(dp(16), dp(18), dp(16), dp(28));
        scroll.addView(root);

        TextView title = title("Todoist Assistant");
        root.addView(title);
        root.addView(section("Local API"));

        LinearLayout connectionCard = card();
        serverUrlField = editText("API URL, e.g. http://10.0.2.2:8000", InputType.TYPE_CLASS_TEXT);
        tokenField = editText("Paste Todoist API token to save", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        timezoneField = editText("Timezone, e.g. Europe/Warsaw", InputType.TYPE_CLASS_TEXT);
        connectionCard.addView(label("Server URL"));
        connectionCard.addView(serverUrlField);
        connectionCard.addView(label("Todoist API token"));
        connectionCard.addView(tokenField);
        connectionCard.addView(label("Timezone override"));
        connectionCard.addView(timezoneField);
        Button saveButton = button("Save credentials");
        saveButton.setOnClickListener(v -> saveCredentials());
        connectionCard.addView(saveButton);
        statusText = body("");
        connectionCard.addView(statusText);
        root.addView(connectionCard);

        root.addView(section("Dashboard"));
        LinearLayout dashboardCard = card();
        Button refreshButton = button("Refresh dashboard");
        refreshButton.setOnClickListener(v -> refreshDashboard());
        dashboardCard.addView(refreshButton);
        metricsText = body("No dashboard payload loaded yet.");
        dashboardCard.addView(metricsText);
        root.addView(dashboardCard);

        plotsContainer = column();
        root.addView(plotsContainer);

        root.addView(section("Automations"));
        LinearLayout automationCard = card();
        automationField = editText("Automation name, e.g. @ai-breakdown or ALL", InputType.TYPE_CLASS_TEXT);
        intervalField = editText("Background interval minutes", InputType.TYPE_CLASS_NUMBER);
        automationCard.addView(label("Automation"));
        automationCard.addView(automationField);
        automationCard.addView(label("Background interval"));
        automationCard.addView(intervalField);
        Button loadAutomationsButton = button("Load automations");
        loadAutomationsButton.setOnClickListener(v -> loadAutomations());
        Button runAutomationButton = button("Run selected");
        runAutomationButton.setOnClickListener(v -> runSelectedAutomation());
        Button runObserverButton = button("Run observer once");
        runObserverButton.setOnClickListener(v -> runObserverOnce());
        Button enableBackgroundButton = button("Enable background run");
        enableBackgroundButton.setOnClickListener(v -> enableBackground());
        Button disableBackgroundButton = button("Disable background run");
        disableBackgroundButton.setOnClickListener(v -> disableBackground());
        automationCard.addView(loadAutomationsButton);
        automationCard.addView(runAutomationButton);
        automationCard.addView(runObserverButton);
        automationCard.addView(enableBackgroundButton);
        automationCard.addView(disableBackgroundButton);
        automationText = body("");
        automationCard.addView(automationText);
        root.addView(automationCard);

        setContentView(scroll);
    }

    private void loadSavedSettings() {
        serverUrlField.setText(settings.serverUrl());
        timezoneField.setText(settings.timezone());
        automationField.setText(settings.automation());
        intervalField.setText(String.valueOf(settings.intervalMinutes()));
    }

    private void saveCredentials() {
        String serverUrl = serverUrlField.getText().toString();
        String timezone = timezoneField.getText().toString();
        String token = tokenField.getText().toString().trim();
        settings.saveConnection(serverUrl, timezone);

        runApi("Saving credentials...", client -> {
            JSONObject result = new JSONObject();
            if (!token.isEmpty()) {
                result.put("token", client.post("/api/admin/api_token",
                        new JSONObject().put("token", token).put("validate", true)));
            }
            if (!timezone.trim().isEmpty()) {
                result.put("timezone", client.post("/api/admin/timezone",
                        new JSONObject().put("timezone", timezone.trim())));
            }
            return result;
        }, json -> {
            tokenField.setText("");
            setStatus("Credentials saved. " + summarizeJson(json));
            refreshStatus();
        });
    }

    private void refreshStatus() {
        runApi("Checking API...", client -> {
            JSONObject result = new JSONObject();
            result.put("health", client.get("/api/health"));
            result.put("token", client.get("/api/admin/api_token"));
            result.put("timezone", client.get("/api/admin/timezone"));
            return result;
        }, json -> setStatus("Connected. " + summarizeJson(json)));
    }

    private void refreshDashboard() {
        runApi("Loading dashboard...", client -> client.get("/api/dashboard/home?granularity=W&weeks=12"), json -> {
            metricsText.setText(summarizeDashboard(json));
            renderPlots(json.optJSONObject("figures"));
            setStatus("Dashboard refreshed at " + json.optString("refreshedAt", "now"));
        });
    }

    private void loadAutomations() {
        runApi("Loading automations...", client -> client.get("/api/admin/automations"), json -> {
            JSONArray items = json.optJSONArray("automations");
            StringBuilder builder = new StringBuilder();
            if (items == null || items.length() == 0) {
                builder.append("No automations returned.");
            } else {
                for (int i = 0; i < items.length(); i++) {
                    JSONObject item = items.optJSONObject(i);
                    if (item == null) continue;
                    builder.append(item.optString("name", item.optString("key")))
                            .append(item.optBoolean("enabled") ? " enabled" : " disabled")
                            .append('\n');
                }
            }
            automationText.setText(builder.toString().trim());
        });
    }

    private void runSelectedAutomation() {
        saveBackgroundSettings();
        String name = settings.automation();
        String path = "ALL".equalsIgnoreCase(name)
                ? "/api/admin/automations/run_all_async"
                : "/api/admin/automations/run_async?name=" + urlEncode(name);
        runApi("Starting automation...", client -> client.post(path, new JSONObject()), this::pollStartedJob);
    }

    private void runObserverOnce() {
        runApi("Running observer...", client -> client.post("/api/admin/observer/run?force=true", new JSONObject()),
                json -> automationText.setText("Observer result:\n" + json.toString()));
    }

    private void enableBackground() {
        saveBackgroundSettings();
        BackgroundAutomationJobService.schedule(this, settings.intervalMinutes());
        automationText.setText(String.format(Locale.US,
                "Background run enabled every %d minutes for %s.",
                settings.intervalMinutes(), settings.automation()));
    }

    private void disableBackground() {
        BackgroundAutomationJobService.cancel(this);
        automationText.setText("Background run disabled.");
    }

    private void pollStartedJob(JSONObject startPayload) {
        String jobId = startPayload.optString("jobId", "");
        if (jobId.isEmpty()) {
            automationText.setText(startPayload.toString());
            return;
        }
        automationText.setText("Job " + jobId + " started.");
        pollJob(jobId, 0);
    }

    private void pollJob(String jobId, int attempt) {
        if (attempt > 90) {
            automationText.setText("Job " + jobId + " is still running.");
            return;
        }
        handler.postDelayed(() -> runApi("Polling job...", client -> client.get("/api/admin/jobs/" + urlEncode(jobId)), json -> {
            String status = json.optString("status", "");
            automationText.setText("Job " + jobId + ": " + status + "\n" + json.optString("error", ""));
            if ("queued".equals(status) || "running".equals(status)) {
                pollJob(jobId, attempt + 1);
            } else {
                automationText.setText("Job finished:\n" + json.toString());
                refreshDashboard();
            }
        }), 2000);
    }

    private void saveBackgroundSettings() {
        int interval = AppSettings.MIN_PERIODIC_MINUTES;
        try {
            interval = Integer.parseInt(intervalField.getText().toString().trim());
        } catch (NumberFormatException ignored) {
            intervalField.setText(String.valueOf(interval));
        }
        settings.saveBackground(automationField.getText().toString(), interval);
        intervalField.setText(String.valueOf(settings.intervalMinutes()));
    }

    private void runApi(String progress, ApiCall call, Consumer<JSONObject> onSuccess) {
        setStatus(progress);
        executor.execute(() -> {
            try {
                ApiClient client = new ApiClient(settings.serverUrl());
                JSONObject json = call.run(client);
                runOnUiThread(() -> onSuccess.accept(json));
            } catch (Exception exc) {
                runOnUiThread(() -> setStatus("Error: " + exc.getMessage()));
            }
        });
    }

    private void renderPlots(JSONObject figures) {
        plotsContainer.removeAllViews();
        if (figures == null || figures.length() == 0) {
            plotsContainer.addView(body("No plots returned."));
            return;
        }
        Iterator<String> keys = figures.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            JSONObject figure = figures.optJSONObject(key);
            if (figure == null || figure.length() == 0) continue;
            plotsContainer.addView(section(humanize(key)));
            WebView webView = new WebView(this);
            WebSettings webSettings = webView.getSettings();
            webSettings.setJavaScriptEnabled(true);
            webSettings.setDomStorageEnabled(true);
            webView.setLayoutParams(new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, dp(320)));
            webView.loadDataWithBaseURL("https://cdn.plot.ly/", PlotHtml.render(figure), "text/html", "UTF-8", null);
            plotsContainer.addView(webView);
        }
    }

    private String summarizeDashboard(JSONObject json) {
        if (json.has("error")) return json.optString("error");
        StringBuilder builder = new StringBuilder();
        JSONObject range = json.optJSONObject("range");
        if (range != null) {
            builder.append(range.optString("beg")).append(" to ").append(range.optString("end")).append('\n');
        }
        JSONObject metrics = json.optJSONObject("metrics");
        JSONArray items = metrics == null ? null : metrics.optJSONArray("items");
        if (items != null) {
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                if (item == null) continue;
                builder.append(item.optString("name"))
                        .append(": ")
                        .append(item.opt("value"))
                        .append('\n');
            }
        }
        JSONObject badges = json.optJSONObject("badges");
        if (badges != null) {
            builder.append("P1/P2/P3/P4: ")
                    .append(badges.optInt("p1")).append("/")
                    .append(badges.optInt("p2")).append("/")
                    .append(badges.optInt("p3")).append("/")
                    .append(badges.optInt("p4"));
        }
        return builder.toString().trim();
    }

    private String summarizeJson(JSONObject json) {
        String token = json.optJSONObject("token") == null ? "" :
                "token " + json.optJSONObject("token").optString("masked", "configured");
        String timezone = json.optJSONObject("timezone") == null ? "" :
                " timezone " + json.optJSONObject("timezone").optString("timezone", "");
        return (token + timezone).trim();
    }

    private void setStatus(String message) {
        statusText.setText(message == null ? "" : message);
    }

    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return layout;
    }

    private LinearLayout card() {
        LinearLayout layout = column();
        layout.setPadding(dp(14), dp(14), dp(14), dp(14));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, dp(8), 0, dp(16));
        layout.setLayoutParams(params);
        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.WHITE);
        background.setStroke(1, Color.rgb(219, 226, 235));
        background.setCornerRadius(dp(8));
        layout.setBackground(background);
        return layout;
    }

    private TextView title(String text) {
        TextView view = body(text);
        view.setTextSize(28);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setTextColor(Color.rgb(15, 23, 42));
        return view;
    }

    private TextView section(String text) {
        TextView view = body(text);
        view.setTextSize(17);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setTextColor(Color.rgb(30, 41, 59));
        view.setPadding(0, dp(14), 0, dp(4));
        return view;
    }

    private TextView label(String text) {
        TextView view = body(text);
        view.setTextSize(13);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setPadding(0, dp(8), 0, dp(4));
        return view;
    }

    private TextView body(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(14);
        view.setTextColor(Color.rgb(51, 65, 85));
        view.setPadding(0, dp(4), 0, dp(4));
        return view;
    }

    private EditText editText(String hint, int inputType) {
        EditText field = new EditText(this);
        field.setSingleLine(true);
        field.setHint(hint);
        field.setInputType(inputType);
        field.setTextSize(15);
        field.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return field;
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return button;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String humanize(String value) {
        return value.replaceAll("([a-z])([A-Z])", "$1 $2").toLowerCase(Locale.US);
    }

    private static String urlEncode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (Exception exc) {
            return value;
        }
    }

    private interface ApiCall {
        JSONObject run(ApiClient client) throws Exception;
    }
}
