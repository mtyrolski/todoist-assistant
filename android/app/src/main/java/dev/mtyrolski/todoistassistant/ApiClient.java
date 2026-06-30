package dev.mtyrolski.todoistassistant;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class ApiClient {
    private final String baseUrl;

    ApiClient(String baseUrl) {
        this.baseUrl = trimTrailingSlash(baseUrl);
    }

    JSONObject get(String path) throws IOException, JSONException {
        return request("GET", path, null);
    }

    JSONObject post(String path, JSONObject body) throws IOException, JSONException {
        return request("POST", path, body == null ? new JSONObject() : body);
    }

    JSONObject delete(String path) throws IOException, JSONException {
        return request("DELETE", path, null);
    }

    private JSONObject request(String method, String path, JSONObject body)
            throws IOException, JSONException {
        HttpURLConnection connection = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(45000);
        connection.setRequestProperty("Accept", "application/json");

        if (body != null) {
            byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setDoOutput(true);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(payload);
            }
        }

        int status = connection.getResponseCode();
        String text = readAll(status >= 400 ? connection.getErrorStream() : connection.getInputStream());
        JSONObject json = text.isEmpty() ? new JSONObject() : new JSONObject(text);
        if (status >= 400) {
            String detail = json.optString("detail", json.optString("error", text));
            throw new IOException(detail.isEmpty() ? "HTTP " + status : detail);
        }
        return json;
    }

    private static String readAll(InputStream input) throws IOException {
        if (input == null) return "";
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
        }
        return builder.toString();
    }

    private static String trimTrailingSlash(String value) {
        String trimmed = value == null ? "" : value.trim();
        while (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed.isEmpty() ? "http://10.0.2.2:8000" : trimmed;
    }
}
