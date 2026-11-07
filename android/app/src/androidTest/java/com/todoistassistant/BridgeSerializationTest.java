package com.todoistassistant;

import static org.junit.Assert.*;

import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public class BridgeSerializationTest {
  @Test
  public void stateDispatchPreservesSpecialProjectNamesInWebView() throws Exception {
    char[] padding = new char[2_200_000];
    java.util.Arrays.fill(padding, 'x');
    JSONObject payload =
        new JSONObject()
            .put("counts", new JSONObject().put("__proto__", 17).put("constructor", 2))
            .put("mappings", new JSONObject().put("__proto__", "a \"quoted\" name\n </script>"))
            .put("padding", new String(padding));
    JSONObject status = new JSONObject().put("message", "cached data");
    String quotedModel = JSONObject.quote(payload.toString());
    CountDownLatch ready = new CountDownLatch(1), resultReady = new CountDownLatch(1);
    AtomicReference<WebView> view = new AtomicReference<>();
    AtomicReference<String> result = new AtomicReference<>();
    var instrumentation = InstrumentationRegistry.getInstrumentation();
    try {
      instrumentation.runOnMainSync(
          () -> {
            WebView web = new WebView(instrumentation.getTargetContext());
            view.set(web);
            web.getSettings().setJavaScriptEnabled(true);
            web.setWebViewClient(
                new WebViewClient() {
                  @Override
                  public void onPageFinished(WebView ignored, String url) {
                    ready.countDown();
                  }
                });
            web.loadDataWithBaseURL(
                "https://appassets.androidplatform.net/",
                "<!doctype html><html><script>window.addEventListener('todoist-state',"
                    + "e => window.captured = JSON.stringify(e.detail));</script></html>",
                "text/html",
                "UTF-8",
                null);
          });
      assertTrue(ready.await(10, TimeUnit.SECONDS));
      instrumentation.runOnMainSync(
          () ->
              view.get()
                  .evaluateJavascript(
                      MainActivity.stateEvent(status, quotedModel),
                      ignored ->
                          view.get()
                              .evaluateJavascript(
                                  "(() => { const event=JSON.parse(window.captured), d=event.model;"
                                      + " return JSON.stringify({counts:d.counts,mappings:d.mappings,"
                                      + "length:d.padding.length,message:event.message}); })()",
                                  value -> {
                                    result.set(value);
                                    resultReady.countDown();
                                  })));
      assertTrue(resultReady.await(30, TimeUnit.SECONDS));
      String captured = new JSONArray("[" + result.get() + "]").getString(0);
      JSONObject decoded = new JSONObject(captured);
      assertEquals(17, decoded.getJSONObject("counts").getInt("__proto__"));
      assertEquals(2, decoded.getJSONObject("counts").getInt("constructor"));
      assertEquals(padding.length, decoded.getInt("length"));
      assertEquals("cached data", decoded.getString("message"));
      assertEquals(
          payload.getJSONObject("mappings").getString("__proto__"),
          decoded.getJSONObject("mappings").getString("__proto__"));
    } finally {
      if (view.get() != null) instrumentation.runOnMainSync(() -> view.get().destroy());
    }
  }
}
