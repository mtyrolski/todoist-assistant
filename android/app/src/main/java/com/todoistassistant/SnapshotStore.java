package com.todoistassistant;

import android.content.Context;
import android.util.AtomicFile;
import java.io.File;
import java.io.FileNotFoundException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.json.JSONObject;

/** Atomic, credential-bound snapshots. A crash cannot reveal another account's cache. */
final class SnapshotStore {
  private final AtomicFile file;

  SnapshotStore(Context context) {
    file = new AtomicFile(new File(context.getFilesDir(), "dashboard-v1.json"));
  }

  JSONObject load(String token) throws Exception {
    JSONObject envelope;
    try {
      envelope = new JSONObject(new String(file.readFully(), StandardCharsets.UTF_8));
    } catch (FileNotFoundException empty) {
      return new JSONObject();
    }
    if (token.isEmpty()) return new JSONObject();
    String binding = envelope.optString("credentialFingerprint");
    if (!binding.isEmpty()
        && !MessageDigest.isEqual(
            binding.getBytes(StandardCharsets.UTF_8),
            fingerprint(token).getBytes(StandardCharsets.UTF_8)))
      throw new java.io.IOException(
          "Saved history belongs to a different connection. Reconnect to load that account safely.");
    JSONObject data = envelope.optJSONObject("snapshot");
    if (data == null) data = envelope; // Migrate the original flat snapshot format.
    int schema = data.optInt("schemaVersion", 1);
    if (schema < 1 || schema > 2)
      throw new java.io.IOException("This saved history needs a newer app version.");
    data.getJSONArray("projects");
    data.getJSONArray("tasks");
    data.getJSONArray("activities");
    java.time.Instant.parse(data.getString("syncedAt"));
    java.time.Instant.parse(data.getString("historyStart"));
    return data;
  }

  interface BeforeCommit {
    void run() throws Exception;
  }

  void save(JSONObject data, String token) throws Exception {
    save(data, token, () -> {});
  }

  void save(JSONObject data, String token, BeforeCommit credentials) throws Exception {
    JSONObject persisted =
        new JSONObject().put("snapshot", data).put("credentialFingerprint", fingerprint(token));
    var stream = file.startWrite();
    try {
      stream.write(persisted.toString().getBytes(StandardCharsets.UTF_8));
      stream.getFD().sync();
      credentials.run();
      file.finishWrite(stream);
    } catch (Exception error) {
      file.failWrite(stream);
      throw error;
    }
  }

  void clear() {
    file.delete();
  }

  private static String fingerprint(String token) throws Exception {
    byte[] hash =
        MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8));
    StringBuilder result = new StringBuilder();
    for (byte value : hash)
      result.append(String.format(java.util.Locale.ROOT, "%02x", value & 0xff));
    return result.toString();
  }
}
