package com.todoistassistant;

import java.io.IOException;

final class SyncCancelledException extends IOException {
  SyncCancelledException() {
    super("Sync cancelled. Your saved data is unchanged.");
  }
}
