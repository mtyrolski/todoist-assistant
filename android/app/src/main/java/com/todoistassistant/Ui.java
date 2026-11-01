package com.todoistassistant;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

final class Ui {
  static final int BG = Color.rgb(14, 17, 22),
      CARD = Color.rgb(24, 29, 38),
      BORDER = Color.rgb(43, 51, 66);
  static final int TEXT = Color.rgb(232, 236, 242),
      MUTED = Color.rgb(153, 167, 185),
      ACCENT = Color.rgb(118, 232, 181);
  static final int YELLOW = Color.rgb(244, 211, 94),
      WARN = Color.rgb(240, 201, 122),
      DANGER = Color.rgb(255, 133, 142);

  static int dp(Context context, float value) {
    return Math.round(value * context.getResources().getDisplayMetrics().density);
  }

  static TextView text(Context context, String value, int size, int color, boolean bold) {
    TextView text = new TextView(context);
    text.setText(value);
    text.setTextSize(size);
    text.setTextColor(color);
    if (bold) text.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
    text.setLineSpacing(dp(context, 3), 1);
    return text;
  }

  static LinearLayout column(Context context) {
    LinearLayout view = new LinearLayout(context);
    view.setOrientation(LinearLayout.VERTICAL);
    return view;
  }

  static GradientDrawable rounded(Context context, int color, int stroke, int radius) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(color);
    drawable.setCornerRadius(dp(context, radius));
    if (stroke != 0) drawable.setStroke(dp(context, 1), stroke);
    return drawable;
  }

  static Button button(
      Context context, String title, View.OnClickListener listener, boolean primary) {
    Button button = new Button(context);
    button.setText(title);
    button.setAllCaps(false);
    button.setTextSize(14);
    button.setTextColor(primary ? BG : TEXT);
    button.setBackground(rounded(context, primary ? ACCENT : CARD, primary ? 0 : BORDER, 12));
    button.setBackgroundTintList(ColorStateList.valueOf(primary ? ACCENT : CARD));
    button.setPadding(dp(context, 16), 0, dp(context, 16), 0);
    button.setMinHeight(dp(context, 48));
    button.setOnClickListener(listener);
    return button;
  }

  static LinearLayout.LayoutParams space(Context context, int top) {
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
    params.topMargin = dp(context, top);
    return params;
  }
}
