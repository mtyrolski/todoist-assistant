package com.todoistassistant;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Encrypt tokens with a non-exportable device key, never in snapshots or APKs. */
class TokenStore {
  private static final String ALIAS = "todoist-api-token";
  private final Context context;

  TokenStore(Context context) {
    this.context = context;
  }

  private SecretKey key(boolean create) throws Exception {
    KeyStore store = KeyStore.getInstance("AndroidKeyStore");
    store.load(null);
    if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
    if (!create) throw new java.io.IOException("Saved credential key is unavailable");
    KeyGenerator generator =
        KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
    generator.init(
        new KeyGenParameterSpec.Builder(
                ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build());
    return generator.generateKey();
  }

  void stage(String token) throws Exception {
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(Cipher.ENCRYPT_MODE, key(true));
    String encrypted =
        Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)
            + ":"
            + Base64.encodeToString(
                cipher.doFinal(token.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
    if (!context
        .getSharedPreferences("auth", Context.MODE_PRIVATE)
        .edit()
        .putString("pending", encrypted)
        .commit()) throw new java.io.IOException("Could not store token on this device");
  }

  String load() throws Exception {
    return decrypt("token");
  }

  String loadPending() throws Exception {
    return decrypt("pending");
  }

  private String decrypt(String name) throws Exception {
    Object stored = context.getSharedPreferences("auth", Context.MODE_PRIVATE).getAll().get(name);
    if (stored == null) return "";
    if (!(stored instanceof String)) throw new java.io.IOException("Invalid saved credential");
    String value = (String) stored;
    if (value.isEmpty()) return "";
    String[] parts = value.split(":", 2);
    if (parts.length != 2) throw new java.io.IOException("Invalid saved credential");
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(
        Cipher.DECRYPT_MODE,
        key(false),
        new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
    return new String(
        cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
  }

  void promotePending() throws Exception {
    var prefs = context.getSharedPreferences("auth", Context.MODE_PRIVATE);
    Object pending = prefs.getAll().get("pending");
    if (!(pending instanceof String) || ((String) pending).isEmpty())
      throw new java.io.IOException("Missing staged credential");
    if (!prefs
        .edit()
        .putString("token", (String) pending)
        .remove("pending")
        .remove("rejected")
        .commit()) throw new java.io.IOException("Could not store token on this device");
  }

  void discardPending() throws Exception {
    if (!context
        .getSharedPreferences("auth", Context.MODE_PRIVATE)
        .edit()
        .remove("pending")
        .commit()) throw new java.io.IOException("Could not update credentials on this device");
  }

  boolean isRejected() {
    return Boolean.TRUE.equals(
        context.getSharedPreferences("auth", Context.MODE_PRIVATE).getAll().get("rejected"));
  }

  void markRejected() throws Exception {
    if (!context
        .getSharedPreferences("auth", Context.MODE_PRIVATE)
        .edit()
        .putBoolean("rejected", true)
        .commit()) throw new java.io.IOException("Could not update credentials on this device");
  }

  boolean clear() {
    return context.getSharedPreferences("auth", Context.MODE_PRIVATE).edit().clear().commit();
  }
}
