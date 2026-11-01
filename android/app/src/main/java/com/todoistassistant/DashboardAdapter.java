package com.todoistassistant;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import androidx.recyclerview.widget.DiffUtil;
import androidx.recyclerview.widget.ListAdapter;
import androidx.recyclerview.widget.RecyclerView;
import java.util.List;
import java.util.Objects;

/** Only visible rows allocate Views, even for accounts with thousands of tasks. */
final class DashboardAdapter extends ListAdapter<DashboardAdapter.Row, DashboardAdapter.Holder> {
  static final class Row {
    final String title, subtitle;
    final int color;
    final boolean heading;
    final Runnable action;
    final DashboardModel chart;
    final int selectedWeek;
    final java.util.function.IntConsumer selectWeek;

    Row(String title, String subtitle, int color, boolean heading, Runnable action) {
      this.title = title;
      this.subtitle = subtitle;
      this.color = color;
      this.heading = heading;
      this.action = action;
      chart = null;
      selectedWeek = 8;
      selectWeek = null;
    }

    Row(DashboardModel model, int selected, java.util.function.IntConsumer select) {
      title = "Completed tasks by week";
      subtitle = "○ actual   ● forecast · tap any week";
      color = Ui.TEXT;
      heading = false;
      action = null;
      chart = model;
      selectedWeek = selected;
      selectWeek = select;
    }
  }

  static final class Holder extends RecyclerView.ViewHolder {
    final LinearLayout box;

    Holder(LinearLayout box) {
      super(box);
      this.box = box;
    }
  }

  DashboardAdapter() {
    super(
        new DiffUtil.ItemCallback<Row>() {
          @Override
          public boolean areItemsTheSame(Row old, Row value) {
            return old.title.equals(value.title);
          }

          @Override
          public boolean areContentsTheSame(Row old, Row value) {
            return old.title.equals(value.title)
                && old.subtitle.equals(value.subtitle)
                && old.color == value.color
                && old.heading == value.heading
                && Objects.equals(old.action, value.action)
                && Objects.equals(old.chart, value.chart)
                && old.selectedWeek == value.selectedWeek;
          }
        });
  }

  void submit(List<Row> next) {
    submitList(next);
  }

  @Override
  public Holder onCreateViewHolder(ViewGroup parent, int type) {
    LinearLayout box = Ui.column(parent.getContext());
    RecyclerView.LayoutParams params = new RecyclerView.LayoutParams(-1, -2);
    params.setMargins(
        Ui.dp(parent.getContext(), 18),
        0,
        Ui.dp(parent.getContext(), 18),
        Ui.dp(parent.getContext(), 12));
    box.setLayoutParams(params);
    return new Holder(box);
  }

  @Override
  public void onBindViewHolder(Holder holder, int position) {
    Row row = getItem(position);
    Context context = holder.box.getContext();
    LinearLayout box = holder.box;
    box.removeAllViews();
    int padding = Ui.dp(context, row.heading ? 2 : 18);
    box.setPadding(padding, Ui.dp(context, 14), padding, Ui.dp(context, 14));
    box.setBackground(row.heading ? null : Ui.rounded(context, Ui.CARD, Ui.BORDER, 18));
    box.addView(Ui.text(context, row.title, row.heading ? 13 : 19, row.color, true));
    if (!row.subtitle.isEmpty())
      box.addView(Ui.text(context, row.subtitle, 13, Ui.MUTED, false), Ui.space(context, 8));
    if (row.chart != null)
      box.addView(
          new WeeklyChartView(context, row.chart, row.selectedWeek, row.selectWeek),
          new LinearLayout.LayoutParams(-1, Ui.dp(context, 230)));
    box.setClickable(row.action != null);
    box.setFocusable(row.action != null);
    box.setOnClickListener(row.action == null ? null : view -> row.action.run());
    box.setContentDescription(row.title + (row.subtitle.isEmpty() ? "" : ". " + row.subtitle));
    box.setForeground(
        row.action == null
            ? null
            : new android.graphics.drawable.RippleDrawable(
                android.content.res.ColorStateList.valueOf(0x2676e8b5),
                null,
                Ui.rounded(context, android.graphics.Color.WHITE, 0, 18)));
    if (row.action != null)
      for (int i = 0; i < box.getChildCount(); i++)
        box.getChildAt(i).setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
  }
}
