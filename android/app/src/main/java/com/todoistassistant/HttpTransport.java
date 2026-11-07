package com.todoistassistant;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** HTTPS-only transport with bounded retries and immediate connection cancellation. */
class HttpTransport implements ApiTransport {
  private static final URI BASE = URI.create("https://api.todoist.com/api/v1/");
  private static final int ATTEMPTS = 3;

  static class Failure extends IOException {
    final long retryAfterMillis;

    Failure(String message) {
      this(message, 0);
    }

    Failure(String message, long retryAfterMillis) {
      super(message);
      this.retryAfterMillis = retryAfterMillis;
    }
  }

  static final class AuthenticationFailure extends Failure {
    AuthenticationFailure() {
      super("Your Todoist token was rejected. Enter a valid token in Control Panel.");
    }
  }

  private final String token;
  private TodoistClient.Progress progress = ignored -> {};
  private volatile boolean cancelled;
  private volatile HttpURLConnection connection;

  HttpTransport(String token) {
    this.token = token;
  }

  @Override
  public void setProgress(TodoistClient.Progress progress) {
    this.progress = progress;
  }

  @Override
  public JSONObject get(String path)
      throws IOException, org.json.JSONException, InterruptedException {
    URI endpoint;
    try {
      URI relative = URI.create(path);
      if (relative.isAbsolute()
          || relative.getRawAuthority() != null
          || relative.getFragment() != null
          || relative.getPath() == null
          || relative.getPath().startsWith("/")
          || java.util.Arrays.asList(relative.getPath().split("/", -1)).contains(".."))
        throw new IllegalArgumentException();
      endpoint = BASE.resolve(relative);
    } catch (IllegalArgumentException invalid) {
      throw new Failure("Invalid Todoist request. Please retry or update the app.");
    }
    for (int attempt = 0; attempt < ATTEMPTS; attempt++) {
      checkCancelled();
      HttpURLConnection current = openConnection(endpoint);
      connection = current;
      try {
        checkCancelled();
        current.setConnectTimeout(10000);
        current.setReadTimeout(15000);
        current.setInstanceFollowRedirects(false);
        current.setRequestProperty("Authorization", "Bearer " + token);
        current.setRequestProperty("Accept", "application/json");
        checkCancelled();
        int status = current.getResponseCode();
        checkCancelled();
        if ((status == 429 || status == 500 || status == 502 || status == 503 || status == 504)
            && attempt < ATTEMPTS - 1) {
          long delay = retryDelay(current.getHeaderField("Retry-After"), attempt);
          if (delay <= 30000) {
            current.disconnect();
            progress.update(
                "Todoist is temporarily unavailable · retrying in " + (delay / 1000) + "s");
            Thread.sleep(delay);
            continue;
          }
        }
        if (status == 401) throw new AuthenticationFailure();
        if (status == 403)
          throw new DataAccessException(
              "Todoist denied access to this data. Check your account permissions and plan.");
        if (status == 429)
          throw new Failure(
              "Todoist is limiting requests. Wait a little and retry; saved data is available offline.",
              retryDelay(current.getHeaderField("Retry-After"), attempt));
        if (status != 200) {
          String retryAfter = current.getHeaderField("Retry-After");
          boolean transientFailure =
              status == 500 || status == 502 || status == 503 || status == 504;
          throw new Failure(
              "Todoist is unavailable (HTTP " + status + "). Try again later.",
              transientFailure && retryAfter != null ? retryDelay(retryAfter, attempt) : 0);
        }
        try (var stream = current.getInputStream();
            var output = new ByteArrayOutputStream()) {
          byte[] buffer = new byte[8192];
          int read;
          while ((read = stream.read(buffer)) != -1) {
            checkCancelled();
            if (output.size() + read > 16 * 1024 * 1024)
              throw new Failure("Todoist returned an unexpectedly large page.");
            output.write(buffer, 0, read);
          }
          return new JSONObject(protectIdentifiers(output.toString(StandardCharsets.UTF_8.name())));
        }
      } catch (IOException exception) {
        checkCancelled();
        if (exception instanceof java.net.SocketTimeoutException && attempt < ATTEMPTS - 1)
          continue;
        throw exception;
      } finally {
        current.disconnect();
        if (connection == current) connection = null;
      }
    }
    throw new IOException("Todoist did not respond. Try again when your connection is stable.");
  }

  HttpURLConnection openConnection(URI endpoint) throws IOException {
    return (HttpURLConnection) endpoint.toURL().openConnection();
  }

  static long retryDelay(String retryAfter, int attempt) {
    return retryDelay(retryAfter, attempt, java.time.Instant.now());
  }

  static long retryDelay(String retryAfter, int attempt, java.time.Instant now) {
    try {
      long seconds = Long.parseLong(retryAfter);
      if (seconds > Long.MAX_VALUE / 1000) return Long.MAX_VALUE;
      return seconds <= 0 ? 500 : Math.max(500, seconds * 1000);
    } catch (NumberFormatException ignored) {
      if (retryAfter != null) {
        if (retryAfter.matches("[0-9]+")) return Long.MAX_VALUE;
        try {
          long millis =
              java.time.Duration.between(
                      now,
                      java.time.ZonedDateTime.parse(
                              retryAfter, java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME)
                          .toInstant())
                  .toMillis();
          return Math.max(500, millis);
        } catch (java.time.DateTimeException | ArithmeticException invalid) {
          // Fall back to bounded exponential backoff for an invalid header.
        }
      }
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
