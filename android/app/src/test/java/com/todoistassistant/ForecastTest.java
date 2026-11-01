package com.todoistassistant;

import org.junit.Test;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class ForecastTest {
    @Test public void completedPeriodsAreExact() {
        assertEquals(349, Forecast.total(349, new double[] {1000}, 1));
    }
    @Test public void freshProjectsUseObservedPace() {
        assertEquals(40, Forecast.total(20, new double[] {}, .5));
    }
    @Test public void emptyPeriodsReduceTheBaseline() {
        assertTrue(Forecast.total(10, new double[] {100, 0, 0}, .5)
            < Forecast.total(10, new double[] {100, 100, 100}, .5));
    }
    @Test public void estimatesNeverUndoCompletedWork() {
        assertTrue(Forecast.total(349, new double[] {1, 2, 3}, .9) >= 349);
    }
}
