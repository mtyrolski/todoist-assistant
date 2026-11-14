package com.todoistassistant;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class ForecastTest {
  @Test
  public void completedPeriodsAreExact() {
    assertEquals(349, Forecast.total(349, new double[] {1000}, 1));
  }

  @Test
  public void freshProjectsUseObservedPace() {
    assertEquals(40, Forecast.total(20, new double[] {}, .5));
  }

  @Test
  public void emptyPeriodsReduceTheBaseline() {
    assertTrue(
        Forecast.total(10, new double[] {100, 0, 0}, .5)
            < Forecast.total(10, new double[] {100, 100, 100}, .5));
  }

  @Test
  public void estimatesNeverUndoCompletedWork() {
    assertTrue(Forecast.total(349, new double[] {1, 2, 3}, .9) >= 349);
  }

  @Test
  public void halfValuesUseTheSameRoundingAsDesktop() {
    assertEquals(0, Forecast.total(0, new double[] {1}, .5));
    assertEquals(2, Forecast.total(0, new double[] {3}, .5));
  }
}
