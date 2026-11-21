package com.todoistassistant;

import org.json.JSONObject;

interface ApiTransport {
  JSONObject get(String path)
      throws java.io.IOException, org.json.JSONException, InterruptedException;

  default void setProgress(TodoistClient.Progress progress) {}

  void cancel();
}
