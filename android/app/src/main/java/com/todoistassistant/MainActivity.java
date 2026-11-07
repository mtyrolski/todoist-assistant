package com.todoistassistant;

import android.annotation.SuppressLint;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import androidx.activity.ComponentActivity;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.lifecycle.ViewModelProvider;
import androidx.webkit.WebViewAssetLoader;
import java.io.ByteArrayInputStream;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.TreeSet;
import org.json.JSONArray;
import org.json.JSONObject;

public class MainActivity extends ComponentActivity {
  private static final String ORIGIN = "https://appassets.androidplatform.net";
  private WebView web;
  private DashboardViewModel model;
  private volatile DashboardViewModel.State state;
  private DashboardModel renderedModel;
  private JSONObject modelPayload;
  private boolean ready;
  private final androidx.activity.result.ActivityResultLauncher<String[]> adjustmentsPicker =
      registerForActivityResult(
          new ActivityResultContracts.OpenDocument(),
          uri -> {
            if (uri != null && model != null) model.importAdjustments(uri);
          });

  @SuppressLint("SetJavaScriptEnabled")
  @Override
  protected void onCreate(Bundle saved) {
    super.onCreate(saved);
    WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
    model = new ViewModelProvider(this).get(DashboardViewModel.class);
    web = new WebView(this);
    WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
    web.setBackgroundColor(0xff0b0f16);
    WebSettings settings = web.getSettings();
    settings.setJavaScriptEnabled(true);
    settings.setDomStorageEnabled(true);
    settings.setAllowFileAccess(false);
    settings.setAllowContentAccess(false);
    settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
    settings.setTextZoom(Math.round(getResources().getConfiguration().fontScale * 100));
    web.setWebChromeClient(new WebChromeClient());
    web.addJavascriptInterface(new Bridge(), "Todoist");
    WebViewAssetLoader assets =
        new WebViewAssetLoader.Builder()
            .addPathHandler("/", new WebViewAssetLoader.AssetsPathHandler(this))
            .build();
    web.setWebViewClient(
        new WebViewClient() {
          @Override
          public WebResourceResponse shouldInterceptRequest(
              WebView view, WebResourceRequest request) {
            if (request.getUrl().toString().startsWith(ORIGIN + "/")) {
              WebResourceResponse response = assets.shouldInterceptRequest(request.getUrl());
              if (response != null) return response;
            }
            return new WebResourceResponse(
                "text/plain",
                "UTF-8",
                404,
                "Not found",
                java.util.Collections.emptyMap(),
                new ByteArrayInputStream(new byte[0]));
          }

          @Override
          public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return !request.getUrl().toString().equals(ORIGIN + "/android.html");
          }
        });
    FrameLayout root = new FrameLayout(this);
    root.addView(web, new FrameLayout.LayoutParams(-1, -1));
    ViewCompat.setOnApplyWindowInsetsListener(
        root,
        (view, insets) -> {
          var bars =
              insets.getInsets(
                  WindowInsetsCompat.Type.systemBars()
                      | WindowInsetsCompat.Type.displayCutout()
                      | WindowInsetsCompat.Type.ime());
          view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
          return insets;
        });
    setContentView(root);
    model
        .state()
        .observe(
            this,
            value -> {
              state = value;
              publish(false);
            });
    getOnBackPressedDispatcher()
        .addCallback(
            this,
            new androidx.activity.OnBackPressedCallback(true) {
              @Override
              public void handleOnBackPressed() {
                web.evaluateJavascript("window.dispatchEvent(new Event('todoist-back'))", null);
              }
            });
    web.loadUrl(ORIGIN + "/android.html");
  }

  private void publish(boolean force) {
    if (!ready || state == null) return;
    try {
      JSONObject payload =
          new JSONObject()
              .put("version", BuildConfig.VERSION_NAME)
              .put("preview", BuildConfig.APPLICATION_ID.endsWith(".preview"))
              .put("loading", state.loading)
              .put("syncing", state.syncing)
              .put("connected", state.connected)
              .put("savedHistory", model.hasSavedHistory())
              .put("demo", state.demo)
              .put("message", state.message);
      if (force || renderedModel != state.model) {
        renderedModel = state.model;
        modelPayload = state.model == null ? null : MobilePayload.model(state.model);
        payload.put("model", modelPayload == null ? JSONObject.NULL : modelPayload);
      }
      JSONObject preferences = new JSONObject(new Bridge().getSettings());
      AlertRules rules = AlertRules.read(preferences.getJSONObject("rules").toString());
      if (state.model != null) {
        var alert = rules.evaluate(state.model.tasks, LocalDate.now(), ZoneId.systemDefault());
        payload.put(
            "alert",
            new JSONObject()
                .put("enabled", rules.enabled)
                .put("level", alert.level)
                .put("matches", alert.matches)
                .put("fire", alert.fire)
                .put("priority", alert.priority)
                .put("due", alert.due)
                .put("deadline", alert.deadline));
      }
      payload.put("preferences", preferences);
      web.evaluateJavascript(stateEvent(payload), null);
    } catch (Exception exception) {
      web.evaluateJavascript(
          "window.dispatchEvent(new CustomEvent('todoist-error',{detail:'Could not open dashboard"
              + " data. Retry sync.'}))",
          null);
    }
  }

  @Override
  protected void onResume() {
    super.onResume();
    if (model != null) model.refreshClock();
  }

  static String stateEvent(JSONObject payload) {
    return "window.dispatchEvent(new CustomEvent('todoist-state',{detail:JSON.parse("
        + JSONObject.quote(payload.toString())
        + ")}))";
  }

  static JSONObject readSettings(android.content.SharedPreferences prefs)
      throws org.json.JSONException {
    var values = prefs.getAll();
    Object config = values.get("config"), web = values.get("web");
    JSONObject settings = null;
    if (web instanceof String) {
      try {
        settings = new JSONObject((String) web);
      } catch (org.json.JSONException invalid) {
        // Keep the stored value intact until the user saves replacement settings.
      }
    }
    return new JSONObject()
        .put(
            "rules",
            new JSONObject(AlertRules.read(config instanceof String ? (String) config : "").json()))
        .put("settings", settings == null ? JSONObject.NULL : settings);
  }

  private final class Bridge {
    @JavascriptInterface
    public void ready() {
      runOnUiThread(
          () -> {
            ready = true;
            publish(true);
          });
    }

    @JavascriptInterface
    public String getSettings() {
      try {
        var prefs = getSharedPreferences("rules", MODE_PRIVATE);
        TreeSet<String> labels = new TreeSet<>();
        var current = state;
        if (current != null && current.model != null)
          for (var task : current.model.tasks) labels.addAll(task.labels);
        return readSettings(prefs).put("labels", new JSONArray(labels)).toString();
      } catch (Exception exception) {
        return "{\"error\":\"Could not load settings\"}";
      }
    }

    @JavascriptInterface
    public String saveSettings(String json) {
      try {
        JSONObject value = new JSONObject(json);
        String rules = AlertRules.read(value.getJSONObject("rules").toString()).json();
        if (!getSharedPreferences("rules", MODE_PRIVATE)
            .edit()
            .putString("config", rules)
            .putString("web", value.getJSONObject("settings").toString())
            .commit()) throw new java.io.IOException("Could not save settings");
        runOnUiThread(() -> publish(false));
        return value.toString();
      } catch (Exception exception) {
        return "{\"error\":\"Could not save settings\"}";
      }
    }

    @JavascriptInterface
    public void command(String name, String argument) {
      runOnUiThread(
          () -> {
            switch (name) {
              case "demo":
                model.showDemo();
                break;
              case "account":
                model.exitDemo();
                break;
              case "sync":
                model.sync(argument);
                break;
              case "refresh-clock":
                model.refreshClock();
                break;
              case "cancel":
                model.cancelSync();
                break;
              case "disconnect":
                android.webkit.WebStorage.getInstance().deleteAllData();
                model.disconnect();
                break;
              case "import-adjustments":
                adjustmentsPicker.launch(
                    new String[] {"application/json", "text/plain", "application/octet-stream"});
                break;
              case "save-adjustments":
                model.saveAdjustments(argument);
                break;
              case "close":
                finish();
                break;
              default:
                break;
            }
          });
    }
  }

  @Override
  protected void onDestroy() {
    ready = false;
    web.removeJavascriptInterface("Todoist");
    web.destroy();
    super.onDestroy();
  }
}
