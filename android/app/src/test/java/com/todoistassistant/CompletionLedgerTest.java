package com.todoistassistant;

import static org.junit.Assert.assertEquals;

import java.time.Instant;
import java.util.Arrays;
import org.junit.Test;

public class CompletionLedgerTest {
  private CompletionLedger.Event event(String id, String kind, String day, Boolean recurring) {
    return new CompletionLedger.Event(
        id, "task", kind, Instant.parse(day + "T12:00:00Z"), recurring);
  }

  @Test
  public void undoMovesOrdinaryCompletionToItsNewDate() {
    var result =
        CompletionLedger.effective(
            Arrays.asList(
                event("1", "completed", "2026-09-30", false),
                event("2", "uncompleted", "2026-10-05", false),
                event("3", "completed", "2026-10-06", false)));
    assertEquals(1, result.size());
    assertEquals("3", result.get(0).id);
  }

  @Test
  public void recurringResetsKeepEveryOccurrence() {
    var result =
        CompletionLedger.effective(
            Arrays.asList(
                event("1", "completed", "2026-10-01", true),
                event("2", "uncompleted", "2026-10-02", null),
                event("3", "completed", "2026-10-03", null)));
    assertEquals(2, result.size());
  }

  @Test
  public void duplicateEventsAndRepeatedUndoCannotInflateCounts() {
    var a = event("1", "completed", "2026-10-01", false);
    assertEquals(1, CompletionLedger.effective(Arrays.asList(a, a)).size());
    assertEquals(
        0,
        CompletionLedger.effective(
                Arrays.asList(
                    a,
                    event("2", "uncompleted", "2026-10-02", false),
                    event("3", "uncompleted", "2026-10-03", false)))
            .size());
  }
}
