package com.todoistassistant;

final class Forecast {
  private Forecast() {}

  static int total(int actual, double[] history, double fraction) {
    if (fraction >= 1) return actual;
    double sum = 0, weights = 0, weight = 1;
    for (int i = history.length - 1; i >= Math.max(0, history.length - 8); i--) {
      sum += history[i] * weight;
      weights += weight;
      weight *= .75;
    }
    double baseline = weights == 0 ? 0 : sum / weights;
    if (fraction <= 0) return Math.max(actual, (int) Math.rint(baseline));
    double pace = actual / Math.max(.25, fraction);
    if (history.length == 0) return Math.max(actual, (int) Math.rint(pace));
    double blend = Math.min(.85, Math.max(.15, fraction));
    return Math.max(actual, (int) Math.rint((1 - blend) * baseline + blend * pace));
  }
}
