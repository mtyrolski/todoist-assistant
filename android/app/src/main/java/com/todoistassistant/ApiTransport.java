package com.todoistassistant;

import org.json.JSONObject;

interface ApiTransport {
  JSONObject get(String path) throws Exception;

  default void setProgress(TodoistClient.Progress progress) {}

  void cancel();
}
