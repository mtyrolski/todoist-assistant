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
    for (int attempt = 0; attempt < 5; attempt++) {
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
        if ((status == 429 || status >= 500) && attempt < 4) {
          long delay = retryDelay(current.getHeaderField("Retry-After"), attempt);
          current.disconnect();
          Thread.sleep(delay);
          continue;
        }
        if (status == 401)
          throw new IOException(
              "Your Todoist token was rejected. Enter a valid token in Control Panel.");
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
          return new JSONObject(protectIdentifiers(output.toString(StandardCharsets.UTF_8.name())));
        }
      } catch (IOException exception) {
        checkCancelled();
        if (exception instanceof java.net.SocketTimeoutException && attempt < 4) continue;
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
      return Math.min(30000, 1000L << Math.min(attempt, 5));
    }
  }

  // Android's JSON parser converts integers larger than a long to imprecise doubles.
  static String protectIdentifiers(String json) {
    StringBuilder result = new StringBuilder(json.length());
    for (int i = 0; i < json.length(); ) {
      if (json.charAt(i) != '"') {
        result.append(json.charAt(i++));
        continue;
      }
      int end = i + 1;
      while (end < json.length() && json.charAt(end) != '"') {
        if (json.charAt(end) == '\\') end++;
        end++;
      }
      if (end >= json.length()) {
        result.append(json, i, json.length());
        break;
      }
      String key = json.substring(i + 1, end);
      result.append(json, i, end + 1);
      i = end + 1;
      if (!key.equals("id") && !key.endsWith("_id")) continue;
      int colon = i;
      while (colon < json.length() && Character.isWhitespace(json.charAt(colon))) colon++;
      if (colon == json.length() || json.charAt(colon) != ':') continue;
      int first = colon + 1;
      while (first < json.length() && Character.isWhitespace(json.charAt(first))) first++;
      int last = first;
      while (last < json.length() && json.charAt(last) >= '0' && json.charAt(last) <= '9') last++;
      if (last == first
          || (last < json.length()
              && !Character.isWhitespace(json.charAt(last))
              && json.charAt(last) != ','
              && json.charAt(last) != '}'
              && json.charAt(last) != ']')) continue;
      result.append(json, i, first).append('"').append(json, first, last).append('"');
      i = last;
    }
    return result.toString();
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
