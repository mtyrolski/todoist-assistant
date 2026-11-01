package com.todoistassistant;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.MotionEvent;
import android.view.View;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.function.IntConsumer;

@android.annotation.SuppressLint("ViewConstructor") // Programmatic chart; no XML inflation.
final class WeeklyChartView extends View {
  private final int[] weeks;
  private final int forecast, selected;
  private final boolean showForecast;
  private final LocalDate monday;
  private final IntConsumer select;
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
  private float left, step;
  private final Path line = new Path();
  private final String[] labels = new String[9];
  private final android.graphics.DashPathEffect dash;

  WeeklyChartView(Context context, DashboardModel model, int selected, IntConsumer select) {
    super(context);
    weeks = model.weeks.clone();
    forecast = model.forecast;
    showForecast = model.forecastAvailable;
    monday = model.weekStart;
    this.selected = selected;
    this.select = select;
    dash = new android.graphics.DashPathEffect(new float[] {dp(4), dp(4)}, 0);
    for (int i = 0; i < labels.length; i++)
      labels[i] = monday.minusWeeks(8 - i).format(DateTimeFormatter.ofPattern("M/d"));
    setFocusable(true);
    setContentDescription(
        "Weekly completed tasks. Current week "
            + weeks[8]
            + (showForecast ? ", forecast " + forecast : ", sync needed")
            + ". Tap a week to inspect project contributions.");
  }

  private float dp(float value) {
    return Ui.dp(getContext(), value);
  }

  @Override
  protected void onDraw(Canvas canvas) {
    super.onDraw(canvas);
    int max = Math.max(1, showForecast ? forecast : weeks[8]);
    for (int value : weeks) max = Math.max(max, value);
    left = dp(25);
    float right = getWidth() - dp(24), top = dp(35), bottom = getHeight() - dp(52);
    step = Math.max(1, (right - left) / 8);
    paint.setTextSize(dp(10));
    paint.setStrokeWidth(dp(1));
    paint.setColor(Ui.BORDER);
    canvas.drawLine(left, bottom, right, bottom, paint);
    paint.setColor(Ui.MUTED);
    canvas.drawText(String.valueOf(max), 0, top, paint);
    paint.setColor(0x2276E8B5);
    canvas.drawRoundRect(
        left + selected * step - dp(14),
        top - dp(16),
        left + selected * step + dp(14),
        bottom + dp(5),
        dp(8),
        dp(8),
        paint);
    line.reset();
    for (int i = 0; i < weeks.length; i++) {
      float x = left + i * step, y = bottom - (bottom - top) * weeks[i] / max;
      if (i == 0) line.moveTo(x, y);
      else line.lineTo(x, y);
    }
    paint.setColor(Ui.YELLOW);
    paint.setStrokeWidth(dp(2));
    paint.setStyle(Paint.Style.STROKE);
    canvas.drawPath(line, paint);
    paint.setStyle(Paint.Style.FILL);
    for (int i = 0; i < weeks.length; i++) {
      float x = left + i * step, y = bottom - (bottom - top) * weeks[i] / max;
      paint.setColor(Ui.YELLOW);
      paint.setStyle(i == 8 ? Paint.Style.STROKE : Paint.Style.FILL);
      canvas.drawCircle(x, y, dp(i == selected ? 5 : 3), paint);
      paint.setStyle(Paint.Style.FILL);
      if (i % 2 == 0 || i == selected) {
        paint.setColor(Ui.MUTED);
        paint.setTextAlign(Paint.Align.CENTER);
        canvas.drawText(labels[i], x, bottom + dp(26), paint);
      }
    }
    if (showForecast) {
      float actualY = bottom - (bottom - top) * weeks[8] / max,
          forecastY = bottom - (bottom - top) * forecast / max;
      paint.setColor(Ui.YELLOW);
      paint.setStyle(Paint.Style.STROKE);
      paint.setPathEffect(dash);
      canvas.drawLine(right, actualY, right, forecastY, paint);
      paint.setPathEffect(null);
      paint.setStyle(Paint.Style.FILL);
      canvas.drawCircle(right, forecastY, dp(6), paint);
    }
    paint.setTextAlign(Paint.Align.LEFT);
  }

  @Override
  public boolean onTouchEvent(MotionEvent event) {
    if (event.getAction() == MotionEvent.ACTION_UP) {
      select.accept(
          Math.max(0, Math.min(8, Math.round((event.getX() - left) / Math.max(1, step)))));
      performClick();
      return true;
    }
    return event.getAction() == MotionEvent.ACTION_DOWN;
  }

  @Override
  public boolean performClick() {
    super.performClick();
    return true;
  }

  @Override
  public boolean onKeyDown(int code, android.view.KeyEvent event) {
    if (code == android.view.KeyEvent.KEYCODE_DPAD_LEFT
        || code == android.view.KeyEvent.KEYCODE_DPAD_RIGHT) {
      select.accept(
          Math.max(
              0,
              Math.min(8, selected + (code == android.view.KeyEvent.KEYCODE_DPAD_LEFT ? -1 : 1))));
      return true;
    }
    return super.onKeyDown(code, event);
  }
}
