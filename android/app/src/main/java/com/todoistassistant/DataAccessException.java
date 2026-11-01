package com.todoistassistant;

import java.io.IOException;

/** A readable account can still lack permission for a particular data source. */
final class DataAccessException extends IOException {
  DataAccessException(String message) {
    super(message);
  }
}
