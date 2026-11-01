package com.todoistassistant;

import org.json.JSONObject;

interface ApiTransport {
  JSONObject get(String path) throws Exception;

  void cancel();
}
