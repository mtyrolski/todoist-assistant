package com.todoistassistant;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** HTTPS-only transport with bounded retries and immediate connection cancellation. */
final class HttpTransport implements ApiTransport {
  private final String token;
  private volatile boolean cancelled;
  private volatile HttpURLConnection connection;

  HttpTransport(String token) {
    this.token = token;
  }

  @Override
  public JSONObject get(String path) throws Exception {
    for (int attempt = 0; attempt < 3; attempt++) {
      checkCancelled();
      HttpURLConnection current =
          (HttpURLConnection)
              URI.create("https://api.todoist.com/api/v1/" + path).toURL().openConnection();
      connection = current;
      current.setConnectTimeout(15000);
      current.setReadTimeout(30000);
      current.setInstanceFollowRedirects(false);
      current.setRequestProperty("Authorization", "Bearer " + token);
      current.setRequestProperty("Accept", "application/json");
      try {
        int status = current.getResponseCode();
        checkCancelled();
        if ((status == 429 || status >= 500) && attempt < 2) {
          long delay = retryDelay(current.getHeaderField("Retry-After"), attempt);
          current.disconnect();
          Thread.sleep(delay);
          continue;
        }
        if (status == 401)
          throw new IOException(
              "Your Todoist token was rejected. Enter a valid token in Settings.");
        if (status == 403)
          throw new DataAccessException(
              "Todoist denied access to this data. Check your account permissions and plan.");
        if (status == 429)
          throw new IOException(
              "Todoist is limiting requests. Wait a little and retry; saved data is available offline.");
        if (status != 200)
          throw new IOException("Todoist is unavailable (HTTP " + status + "). Try again later.");
        try (var stream = current.getInputStream();
            var output = new ByteArrayOutputStream()) {
          byte[] buffer = new byte[8192];
          int read;
          while ((read = stream.read(buffer)) != -1) {
            checkCancelled();
            if (output.size() + read > 16 * 1024 * 1024)
              throw new IOException("Todoist returned an unexpectedly large page.");
            output.write(buffer, 0, read);
          }
          return new JSONObject(output.toString(StandardCharsets.UTF_8.name()));
        }
      } catch (IOException exception) {
        checkCancelled();
        if (exception instanceof java.net.SocketTimeoutException && attempt < 2) continue;
        throw exception;
      } finally {
        current.disconnect();
        if (connection == current) connection = null;
      }
    }
    throw new IOException("Todoist did not respond. Try again when your connection is stable.");
  }

  static long retryDelay(String retryAfter, int attempt) {
    try {
      return Math.max(500, Math.min(30, Long.parseLong(retryAfter)) * 1000);
    } catch (NumberFormatException ignored) {
      return 1000L * (attempt + 1);
    }
  }

  private void checkCancelled() throws SyncCancelledException {
    if (cancelled || Thread.currentThread().isInterrupted()) throw new SyncCancelledException();
  }

  @Override
  public void cancel() {
    cancelled = true;
    HttpURLConnection current = connection;
    if (current != null) current.disconnect();
  }
}
