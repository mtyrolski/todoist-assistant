package com.todoistassistant;

import static org.junit.Assert.*;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Queue;
import org.junit.Test;

public class HttpTransportTest {
  private static class Response extends HttpURLConnection {
    final int status;
    final String body;
    IOException failure;

    Response(int status, String body) throws Exception {
      super(new URL("https://api.todoist.com/api/v1/user"));
      this.status = status;
      this.body = body;
    }

    @Override
    public int getResponseCode() throws IOException {
      if (failure != null) throw failure;
      return status;
    }

    @Override
    public String getHeaderField(String name) {
      return "Retry-After".equals(name) ? "-1" : null;
    }

    @Override
    public InputStream getInputStream() {
      return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));
    }

    @Override
    public void disconnect() {}

    @Override
    public boolean usingProxy() {
      return false;
    }

    @Override
    public void connect() {}
  }

  private static final class Transport extends HttpTransport {
    final Queue<Response> responses = new ArrayDeque<>();
    int requests;
    URI endpoint;

    Transport() {
      super("private-test-token");
    }

    @Override
    HttpURLConnection openConnection(URI value) {
      requests++;
      endpoint = value;
      return responses.remove();
    }
  }

  @Test
  public void successfulRequestUsesFixedHttpsOriginAndBoundedTimeouts() throws Exception {
    Transport transport = new Transport();
    Response response = new Response(200, "{\"id\":123}");
    transport.responses.add(response);
    assertEquals("123", transport.get("user").getString("id"));
    assertEquals("https://api.todoist.com/api/v1/user", transport.endpoint.toString());
    assertEquals("Bearer private-test-token", response.getRequestProperty("Authorization"));
    assertFalse(response.getInstanceFollowRedirects());
    assertEquals(10000, response.getConnectTimeout());
    assertEquals(15000, response.getReadTimeout());
  }

  @Test
  public void malformedOrExternalPathsAreRejectedBeforeConnecting() throws Exception {
    for (String path :
        new String[] {
          "http://evil.test", "//evil.test", "../user", "%2e%2e/user", "bad path", "user#fragment"
        }) {
      Transport transport = new Transport();
      HttpTransport.Failure error =
          assertThrows(HttpTransport.Failure.class, () -> transport.get(path));
      assertTrue(error.getMessage().contains("Invalid"));
      assertEquals(0, transport.requests);
    }
  }

  @Test
  public void authenticationRedirectAndServerFailuresStayDistinct() throws Exception {
    for (int status : new int[] {401, 403, 302, 500}) {
      Transport transport = new Transport();
      for (int i = 0; i < 3; i++) transport.responses.add(new Response(status, ""));
      IOException error = assertThrows(IOException.class, () -> transport.get("user"));
      if (status == 401) assertTrue(error.getMessage().contains("token was rejected"));
      if (status == 403) assertTrue(error instanceof DataAccessException);
      if (status == 302 || status == 500) assertTrue(error.getMessage().contains("HTTP " + status));
      assertFalse(error.getMessage().contains("private-test-token"));
      assertEquals(status == 500 ? 3 : 1, transport.requests);
    }
  }

  @Test
  public void timeoutIsBoundedAndRecoveryUsesANewRequest() throws Exception {
    Transport transport = new Transport();
    for (int i = 0; i < 3; i++) {
      Response response = new Response(200, "");
      response.failure = new SocketTimeoutException("sensitive details");
      transport.responses.add(response);
    }
    assertThrows(SocketTimeoutException.class, () -> transport.get("user"));
    assertEquals(3, transport.requests);
    transport.responses.add(new Response(200, "{\"id\":\"restored\"}"));
    assertEquals("restored", transport.get("user").getString("id"));
  }

  @Test
  public void longRetryAfterDoesNotLeaveSyncWaitingForMinutes() throws Exception {
    Transport transport = new Transport();
    transport.responses.add(
        new Response(429, "") {
          @Override
          public String getHeaderField(String name) {
            return "Retry-After".equals(name) ? "120" : null;
          }
        });
    HttpTransport.Failure error =
        assertThrows(HttpTransport.Failure.class, () -> transport.get("user"));
    assertTrue(error.getMessage().contains("limiting requests"));
    assertEquals(1, transport.requests);
  }

  @Test
  public void invalidJsonIsNotAcceptedAsAnEmptyResponse() throws Exception {
    Transport transport = new Transport();
    transport.responses.add(new Response(200, "not json"));
    assertThrows(org.json.JSONException.class, () -> transport.get("user"));
  }

  @Test
  public void connectionLostDuringResponseIsNotSuccessfulEmptyData() throws Exception {
    Transport transport = new Transport();
    transport.responses.add(
        new Response(200, "") {
          @Override
          public InputStream getInputStream() {
            return new InputStream() {
              @Override
              public int read() throws IOException {
                throw new SocketException("connection reset");
              }
            };
          }
        });
    assertThrows(SocketException.class, () -> transport.get("user"));
  }
}
