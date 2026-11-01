package com.todoistassistant;

import android.app.AlertDialog;
import android.os.Bundle;
import android.os.Parcelable;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.view.WindowInsets;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import androidx.activity.ComponentActivity;
import androidx.lifecycle.ViewModelProvider;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class MainActivity extends ComponentActivity {
  private DashboardViewModel model;
  private DashboardViewModel.State state;
  private DashboardAdapter adapter;
  private RecyclerView list;
  private LinearLayoutManager layout;
  private TextView status, timestamp;
  private ProgressBar progress;
  private Button sync, cancel;
  private EditText search;
  private Spinner priority;
  private LinearLayout filters;
  private final Button[] tabs = new Button[3];
  private final String[] queries = {"", "", ""};
  private final Set<String> expanded = new HashSet<>();
  private final android.os.Handler handler =
      new android.os.Handler(android.os.Looper.getMainLooper());
  private final Runnable updateSearch = () -> rebuildRows(false);
  private int tab, priorityValue, selectedWeek = 8;
  private boolean allContributions, changingSearch;
  private Parcelable restoredScroll;
  private DashboardModel renderedModel;
  private boolean renderedLoading;

  @Override
  public void onCreate(Bundle saved) {
    super.onCreate(saved);
    if (saved != null) {
      tab = saved.getInt("tab");
      priorityValue = saved.getInt("priority");
      selectedWeek = saved.getInt("week", 8);
      String[] stored = saved.getStringArray("queries");
      if (stored != null) System.arraycopy(stored, 0, queries, 0, Math.min(3, stored.length));
      ArrayList<String> opened = saved.getStringArrayList("expanded");
      if (opened != null) expanded.addAll(opened);
      restoredScroll = saved.getParcelable("scroll");
    }
    model = new ViewModelProvider(this).get(DashboardViewModel.class);
    createScreen();
    model
        .state()
        .observe(
            this,
            value -> {
              state = value;
              renderState();
            });
    getOnBackPressedDispatcher()
        .addCallback(
            this,
            new androidx.activity.OnBackPressedCallback(true) {
              @Override
              public void handleOnBackPressed() {
                if (tab != 0) selectTab(0);
                else {
                  setEnabled(false);
                  getOnBackPressedDispatcher().onBackPressed();
                }
              }
            });
  }

  private void createScreen() {
    LinearLayout root = Ui.column(this);
    root.setBackgroundColor(Ui.BG);
    root.setOnApplyWindowInsetsListener(
        (view, insets) -> {
          if (android.os.Build.VERSION.SDK_INT >= 30) {
            var bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
          } else
            view.setPadding(
                insets.getSystemWindowInsetLeft(),
                insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(),
                insets.getSystemWindowInsetBottom());
          return insets;
        });
    LinearLayout header = Ui.column(this);
    header.setPadding(dp(20), dp(18), dp(20), dp(8));
    header.addView(Ui.text(this, "TODOIST ASSISTANT", 11, Ui.ACCENT, true));
    header.addView(Ui.text(this, "Activity & focus", 27, Ui.TEXT, true), Ui.space(this, 4));
    timestamp = Ui.text(this, "Your day, at a glance", 12, Ui.MUTED, false);
    header.addView(timestamp, Ui.space(this, 5));
    LinearLayout actions = new LinearLayout(this);
    sync =
        Ui.button(
            this,
            "Connect Todoist",
            view -> {
              if (state != null && state.demo) model.exitDemo();
              else if (state != null && state.connected) model.sync("");
              else tokenDialog();
            },
            true);
    actions.addView(sync, new LinearLayout.LayoutParams(0, dp(46), 1));
    Button settings = Ui.button(this, "Settings", view -> settings(), false);
    LinearLayout.LayoutParams settingsParams = new LinearLayout.LayoutParams(-2, dp(46));
    settingsParams.leftMargin = dp(10);
    actions.addView(settings, settingsParams);
    header.addView(actions, Ui.space(this, 14));
    status = Ui.text(this, "", 12, Ui.MUTED, false);
    status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
    header.addView(status, Ui.space(this, 8));
    progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
    progress.setIndeterminate(true);
    header.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));
    cancel = Ui.button(this, "Cancel sync", view -> model.cancelSync(), false);
    header.addView(cancel, Ui.space(this, 6));
    root.addView(header);
    LinearLayout navigation = new LinearLayout(this);
    navigation.setPadding(dp(18), dp(6), dp(18), dp(8));
    String[] labels = {"Overview", "Projects", "Activity"};
    for (int i = 0; i < tabs.length; i++) {
      final int selected = i;
      tabs[i] = Ui.button(this, labels[i], view -> selectTab(selected), false);
      tabs[i].setPadding(0, 0, 0, 0);
      LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(44), 1);
      if (i > 0) params.leftMargin = dp(6);
      navigation.addView(tabs[i], params);
    }
    root.addView(navigation);
    filters = new LinearLayout(this);
    filters.setPadding(dp(18), 0, dp(18), dp(10));
    search = new EditText(this);
    search.setSingleLine(true);
    search.setTextSize(14);
    search.setTextColor(Ui.TEXT);
    search.setHintTextColor(Ui.MUTED);
    search.setInputType(InputType.TYPE_CLASS_TEXT);
    search.setPadding(dp(12), 0, dp(12), 0);
    search.setBackground(Ui.rounded(this, Ui.CARD, Ui.BORDER, 12));
    search.setContentDescription("Search tasks, projects or activity");
    filters.addView(search, new LinearLayout.LayoutParams(0, dp(48), 1));
    priority = new Spinner(this);
    priority.setAdapter(
        new ArrayAdapter<>(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            new String[] {"All", "P1", "P2", "P3", "P4"}));
    priority.setContentDescription("Filter task priority");
    LinearLayout.LayoutParams filterParams = new LinearLayout.LayoutParams(dp(85), dp(48));
    filterParams.leftMargin = dp(6);
    filters.addView(priority, filterParams);
    priority.setSelection(priorityValue == 0 ? 0 : 5 - priorityValue);
    priority.setOnItemSelectedListener(
        new android.widget.AdapterView.OnItemSelectedListener() {
          @Override
          public void onItemSelected(
              android.widget.AdapterView<?> parent, View view, int position, long id) {
            int next = position == 0 ? 0 : 5 - position;
            if (priorityValue != next) {
              priorityValue = next;
              rebuildRows(true);
            }
          }

          @Override
          public void onNothingSelected(android.widget.AdapterView<?> parent) {}
        });
    search.addTextChangedListener(
        new TextWatcher() {
          @Override
          public void beforeTextChanged(CharSequence s, int start, int count, int after) {}

          @Override
          public void onTextChanged(CharSequence s, int start, int before, int count) {
            if (changingSearch) return;
            queries[tab] = s.toString();
            handler.removeCallbacks(updateSearch);
            handler.postDelayed(updateSearch, 180);
          }

          @Override
          public void afterTextChanged(Editable value) {}
        });
    root.addView(filters);
    list = new RecyclerView(this);
    layout = new LinearLayoutManager(this);
    list.setLayoutManager(layout);
    adapter = new DashboardAdapter();
    list.setAdapter(adapter);
    list.setItemAnimator(null);
    list.setClipToPadding(false);
    list.setPadding(0, 0, 0, dp(20));
    root.addView(list, new LinearLayout.LayoutParams(-1, 0, 1));
    setContentView(root);
  }

  private void selectTab(int next) {
    tab = next;
    changingSearch = true;
    search.setText(queries[tab]);
    changingSearch = false;
    renderNavigation();
    rebuildRows(true);
  }

  private void renderNavigation() {
    for (int i = 0; i < tabs.length; i++) {
      tabs[i].setTextColor(tab == i ? Ui.BG : Ui.MUTED);
      tabs[i].setBackgroundTintList(
          android.content.res.ColorStateList.valueOf(tab == i ? Ui.ACCENT : Ui.CARD));
      tabs[i].setSelected(tab == i);
    }
    filters.setVisibility(
        tab == 0 || state == null || state.model == null ? View.GONE : View.VISIBLE);
    priority.setVisibility(tab == 1 ? View.VISIBLE : View.GONE);
    search.setHint(tab == 1 ? "Search tasks, projects, labels" : "Search recent activity");
  }

  private void renderState() {
    if (state == null) return;
    boolean busy = state.loading || state.syncing;
    sync.setEnabled(!busy);
    sync.setText(
        state.demo
            ? "Back to my data"
            : state.syncing ? "Syncing…" : state.connected ? "Sync now" : "Connect Todoist");
    status.setText(state.message);
    status.setVisibility(state.message.isEmpty() ? View.GONE : View.VISIBLE);
    progress.setVisibility(busy ? View.VISIBLE : View.GONE);
    cancel.setVisibility(state.syncing ? View.VISIBLE : View.GONE);
    if (state.model == null) timestamp.setText("Private on your device · works offline");
    else
      timestamp.setText(
          (state.demo ? "DEMO · " : "Saved · ")
              + DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT)
                  .format(state.model.syncedAt.atZone(ZoneId.systemDefault())));
    if (!search.getText().toString().equals(queries[tab])) {
      changingSearch = true;
      search.setText(queries[tab]);
      changingSearch = false;
    }
    renderNavigation();
    if (adapter.getItemCount() == 0
        || renderedModel != state.model
        || renderedLoading != state.loading) {
      renderedModel = state.model;
      renderedLoading = state.loading;
      rebuildRows(false);
    }
  }

  private void rebuildRows(boolean top) {
    if (state == null) return;
    List<DashboardAdapter.Row> rows = new ArrayList<>();
    if (state.model == null) {
      rows.add(
          card(
              "Make your week visible",
              "See your progress, find the work that needs attention, and browse projects from one place.",
              Ui.TEXT,
              this::tokenDialog));
      rows.add(
          card(
              "Connect your Todoist account",
              "Use your API token. The app only reads Todoist; your saved history stays on this device.",
              Ui.ACCENT,
              this::tokenDialog));
      rows.add(
          card(
              "Explore a demo",
              "Try the dashboard offline before connecting your account.",
              Ui.TEXT,
              () -> model.showDemo()));
      if (state.loading) rows.add(card("Opening your history…", "", Ui.MUTED, null));
    } else if (tab == 0) overview(rows, state.model);
    else if (tab == 1) projects(rows, state.model);
    else activity(rows, state.model);
    Parcelable scroll = top ? null : layout.onSaveInstanceState();
    adapter.submit(rows);
    if (top) list.scrollToPosition(0);
    else if (restoredScroll != null) {
      layout.onRestoreInstanceState(restoredScroll);
      restoredScroll = null;
    } else if (scroll != null) layout.onRestoreInstanceState(scroll);
  }

  private DashboardAdapter.Row card(String title, String detail, int color, Runnable action) {
    return new DashboardAdapter.Row(title, detail, color, false, action);
  }

  private DashboardAdapter.Row heading(String title) {
    return new DashboardAdapter.Row(title, "", Ui.MUTED, true, null);
  }

  private void overview(List<DashboardAdapter.Row> rows, DashboardModel data) {
    AlertRules rules =
        AlertRules.read(getSharedPreferences("rules", MODE_PRIVATE).getString("config", ""));
    AlertRules.Status alert = rules.evaluate(data.tasks, LocalDate.now(), ZoneId.systemDefault());
    rows.add(heading("FOCUS TODAY"));
    rows.add(
        card(
            !rules.enabled
                ? "Monitoring paused"
                : alert.level == 2
                    ? "Urgent attention needed"
                    : alert.level == 1 ? "Attention needed" : "All clear",
            !rules.enabled
                ? "Turn on the rules you want in Settings."
                : alert.matches
                    + " matching tasks · fire "
                    + alert.fire
                    + " · priority "
                    + alert.priority
                    + " · due "
                    + alert.due
                    + " · deadline "
                    + alert.deadline,
            alert.level == 2 ? Ui.DANGER : alert.level == 1 ? Ui.WARN : Ui.ACCENT,
            this::rulesDialog));
    rows.add(
        card(
            data.tasks.size() + " active tasks",
            "P1 "
                + data.priorities[0]
                + "   ·   P2 "
                + data.priorities[1]
                + "   ·   P3 "
                + data.priorities[2]
                + "   ·   P4 "
                + data.priorities[3]
                + "\nBrowse projects and filter your priorities →",
            Ui.TEXT,
            () -> selectTab(1)));
    if (!data.historyAvailable) {
      rows.add(card("Completion history unavailable", data.historyWarning, Ui.WARN, null));
      return;
    }
    if (!data.historyWarning.isEmpty())
      rows.add(card("History refresh notice", data.historyWarning, Ui.WARN, null));
    rows.add(heading("YOUR WEEK"));
    rows.add(
        card(
            data.weeks[8] + " completed so far",
            data.forecastAvailable
                ? "Forecast: " + data.forecast + " by Sunday · estimated at the last sync"
                : "No sync this week yet. Refresh to see current progress.",
            Ui.YELLOW,
            null));
    rows.add(
        new DashboardAdapter.Row(
            data,
            selectedWeek,
            week -> {
              selectedWeek = week;
              allContributions = false;
              rebuildRows(false);
            }));
    rows.add(heading("WEEK OF " + data.weekStart.minusWeeks(8 - selectedWeek)));
    rows.add(
        card(
            data.weeks[selectedWeek] + " completed tasks",
            selectedWeek == 8
                ? "Current week · completed tasks remain separate from estimates."
                : "Completed calendar week · Monday to Sunday",
            Ui.TEXT,
            null));
    var contributions = data.weeklyProjects.get(selectedWeek);
    int shown = 0;
    for (var entry : contributions.entrySet()) {
      if (!allContributions && shown++ >= 6) break;
      rows.add(card(entry.getKey(), entry.getValue() + " completed", Ui.TEXT, null));
    }
    if (contributions.isEmpty())
      rows.add(
          card(
              "No completions recorded",
              "There are no effective completions for this week in your saved history.",
              Ui.MUTED,
              null));
    if (!allContributions && contributions.size() > 6)
      rows.add(
          card(
              "Show all " + contributions.size() + " projects",
              "",
              Ui.ACCENT,
              () -> {
                allContributions = true;
                rebuildRows(false);
              }));
    rows.add(
        card(
            data.undone + " undone completions this week",
            "Undo actions are recorded separately. Ordinary undone completions are removed from their original period; recurring occurrences stay counted.",
            Ui.MUTED,
            () -> {
              queries[2] = "uncompleted";
              selectTab(2);
            }));
    rows.add(heading("SAVED ON THIS DEVICE"));
    rows.add(
        card(
            data.eventCount + " activity records",
            "History from "
                + data.historyStart.substring(0, 10)
                + ". Older periods need recorded history; missing history is never filled with invented counts.",
            Ui.MUTED,
            null));
  }

  private void projects(List<DashboardAdapter.Row> rows, DashboardModel data) {
    String query = queries[1].trim().toLowerCase(Locale.ROOT);
    int found = 0;
    rows.add(heading("PROJECTS & TASKS"));
    for (var project : data.projects) {
      List<DashboardModel.Task> matches = new ArrayList<>();
      boolean projectMatch = project.path.toLowerCase(Locale.ROOT).contains(query);
      for (var task : project.tasks)
        if ((priorityValue == 0 || priorityValue == task.priority)
            && (projectMatch || task.searchText().contains(query))) matches.add(task);
      if (matches.isEmpty() && (!query.isEmpty() || priorityValue != 0)) continue;
      boolean filtered = !query.isEmpty() || priorityValue != 0;
      boolean open = expanded.contains(project.id) || filtered;
      rows.add(
          card(
              (open ? "▾  " : "▸  ") + project.path,
              matches.size()
                  + (filtered
                      ? " matching tasks"
                      : " tasks · tap to " + (open ? "collapse" : "expand")),
              Ui.TEXT,
              filtered
                  ? null
                  : () -> {
                    if (!expanded.add(project.id)) expanded.remove(project.id);
                    rebuildRows(false);
                  }));
      found += matches.size();
      if (open)
        for (var task : matches)
          rows.add(
              card(
                  "P" + (5 - task.priority) + "  " + task.content,
                  (task.due.isEmpty() ? "No due date" : "Due " + task.due)
                      + (task.deadline.isEmpty() ? "" : " · deadline " + task.deadline),
                  task.priority == 4 ? Ui.DANGER : task.priority == 3 ? Ui.WARN : Ui.TEXT,
                  () -> taskDetails(task)));
    }
    rows.add(
        1,
        card(
            found + " matching tasks",
            "Search includes project paths and labels. Priority filters apply to every project.",
            Ui.MUTED,
            null));
    if (rows.size() == 2)
      rows.add(
          card("No tasks match", "Try another search or choose All priorities.", Ui.TEXT, null));
  }

  private void activity(List<DashboardAdapter.Row> rows, DashboardModel data) {
    if (!data.historyAvailable) {
      rows.add(card("Activity unavailable", data.historyWarning, Ui.WARN, null));
      return;
    }
    rows.add(heading("RECENT ACTIVITY · UP TO 200 EVENTS"));
    String query = queries[2].trim().toLowerCase(Locale.ROOT);
    for (var event : data.recent) {
      if (!(event.kind + " " + event.content + " " + event.project)
          .toLowerCase(Locale.ROOT)
          .contains(query)) continue;
      String when =
          DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
              .format(event.date.atZone(ZoneId.systemDefault()));
      rows.add(
          card(
              event.kind.equals("uncompleted")
                  ? "Undone completion"
                  : event.kind.isEmpty()
                      ? "Activity"
                      : event.kind.substring(0, 1).toUpperCase(Locale.ROOT)
                          + event.kind.substring(1),
              event.content + "\n" + event.project + " · " + when,
              event.kind.equals("uncompleted") ? Ui.WARN : Ui.TEXT,
              null));
    }
    if (rows.size() == 1)
      rows.add(
          card(
              "No activity matches",
              "Try another search, or sync to refresh your history.",
              Ui.MUTED,
              null));
  }

  private void taskDetails(DashboardModel.Task task) {
    TextView body =
        Ui.text(
            this,
            task.content
                + "\n\n"
                + task.project
                + "\nPriority P"
                + (5 - task.priority)
                + (task.due.isEmpty() ? "" : "\nDue: " + task.due)
                + (task.deadline.isEmpty() ? "" : "\nDeadline: " + task.deadline)
                + (task.labels.isEmpty() ? "" : "\nLabels: " + String.join(", ", task.labels)),
            16,
            Ui.TEXT,
            false);
    body.setTextIsSelectable(true);
    body.setPadding(dp(24), dp(12), dp(24), dp(12));
    new AlertDialog.Builder(this)
        .setTitle("Task details")
        .setView(body)
        .setPositiveButton("Close", null)
        .show();
  }

  private void settings() {
    List<String> options =
        new ArrayList<>(
            java.util.Arrays.asList("Connect or update token", "Alert rules", "Explore demo"));
    if (state != null && state.connected) options.add("Disconnect and clear local data");
    new AlertDialog.Builder(this)
        .setTitle("Settings")
        .setItems(
            options.toArray(new String[0]),
            (dialog, which) -> {
              if (which == 0) tokenDialog();
              else if (which == 1) rulesDialog();
              else if (which == 2) model.showDemo();
              else
                new AlertDialog.Builder(this)
                    .setTitle("Disconnect this device?")
                    .setMessage(
                        "This removes the saved token and history from this device. Your Todoist tasks are unchanged.")
                    .setPositiveButton(
                        "Disconnect",
                        (confirm, choice) -> {
                          expanded.clear();
                          model.disconnect();
                        })
                    .setNegativeButton("Keep data", null)
                    .show();
            })
        .setNegativeButton("Close", null)
        .show();
  }

  private void tokenDialog() {
    EditText input = new EditText(this);
    input.setSingleLine(true);
    input.setTextColor(Ui.TEXT);
    input.setHint("Paste Todoist API token");
    input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
    input.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
    LinearLayout box = Ui.column(this);
    box.setPadding(dp(24), dp(8), dp(24), 0);
    box.addView(input);
    AlertDialog dialog =
        new AlertDialog.Builder(this)
            .setTitle("Connect Todoist")
            .setMessage(
                "Find your API token in Todoist Settings → Integrations → Developer. Requests are read-only; the token stays encrypted on this device. Updating a token for the same account keeps its history.")
            .setView(box)
            .setPositiveButton("Connect and sync", null)
            .setNegativeButton("Cancel", null)
            .create();
    dialog.setOnShowListener(
        view ->
            dialog
                .getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(
                    button -> {
                      String value = input.getText().toString().trim();
                      if (value.isEmpty()) {
                        input.setError("Enter an API token");
                        return;
                      }
                      if (state != null && (state.syncing || state.loading)) {
                        input.setError("Wait for the current operation or cancel it first");
                        return;
                      }
                      model.sync(value);
                      input.setText("");
                      dialog.dismiss();
                    }));
    dialog.show();
  }

  private CheckBox check(LinearLayout box, String label, boolean value) {
    CheckBox check = new CheckBox(this);
    check.setText(label);
    check.setTextColor(Ui.TEXT);
    check.setChecked(value);
    box.addView(check);
    return check;
  }

  private EditText number(LinearLayout box, String label, int value) {
    box.addView(Ui.text(this, label, 13, Ui.MUTED, false), Ui.space(this, 8));
    EditText input = new EditText(this);
    input.setInputType(InputType.TYPE_CLASS_NUMBER);
    input.setText(String.valueOf(value));
    input.setSingleLine(true);
    input.setTextColor(Ui.TEXT);
    box.addView(input);
    return input;
  }

  private void rulesDialog() {
    AlertRules rules =
        AlertRules.read(getSharedPreferences("rules", MODE_PRIVATE).getString("config", ""));
    LinearLayout box = Ui.column(this);
    box.setPadding(dp(20), dp(8), dp(20), dp(16));
    CheckBox enabled = check(box, "Enable attention monitoring", rules.enabled),
        fire = check(box, "Red alert for fire labels", rules.fire);
    box.addView(
        Ui.text(this, "Fire labels (exact names, separated by commas)", 13, Ui.MUTED, false));
    EditText labels = new EditText(this);
    labels.setTextColor(Ui.TEXT);
    labels.setText(rules.fireLabels);
    box.addView(labels);
    CheckBox priorities = check(box, "Attention for selected priorities", rules.priority);
    CheckBox[] selected = new CheckBox[4];
    for (int i = 0; i < 4; i++)
      selected[i] = check(box, "P" + (i + 1), rules.priorities.contains(4 - i));
    EditText priorityMin = number(box, "Minimum priority matches", rules.priorityMin);
    CheckBox due = check(box, "Attention for overdue and upcoming due dates", rules.due);
    EditText dueDays = number(box, "Due within days (0 = today and overdue)", rules.dueDays),
        dueMin = number(box, "Minimum due matches", rules.dueMin);
    CheckBox deadline = check(box, "Attention for overdue and upcoming deadlines", rules.deadline);
    EditText deadlineDays = number(box, "Deadline within days", rules.deadlineDays),
        deadlineMin = number(box, "Minimum deadline matches", rules.deadlineMin);
    ScrollView scroll = new ScrollView(this);
    scroll.addView(box);
    AlertDialog dialog =
        new AlertDialog.Builder(this)
            .setTitle("Attention rules · this device")
            .setView(scroll)
            .setPositiveButton("Save", null)
            .setNegativeButton("Cancel", null)
            .create();
    dialog.setOnShowListener(
        view ->
            dialog
                .getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(
                    button -> {
                      try {
                        rules.priorityMin = positive(priorityMin, 1);
                        rules.dueDays = positive(dueDays, 0);
                        rules.dueMin = positive(dueMin, 1);
                        rules.deadlineDays = positive(deadlineDays, 0);
                        rules.deadlineMin = positive(deadlineMin, 1);
                      } catch (IllegalArgumentException invalid) {
                        return;
                      }
                      rules.enabled = enabled.isChecked();
                      rules.fire = fire.isChecked();
                      rules.fireLabels = labels.getText().toString();
                      rules.priority = priorities.isChecked();
                      rules.due = due.isChecked();
                      rules.deadline = deadline.isChecked();
                      rules.priorities.clear();
                      for (int i = 0; i < selected.length; i++)
                        if (selected[i].isChecked()) rules.priorities.add(4 - i);
                      getSharedPreferences("rules", MODE_PRIVATE)
                          .edit()
                          .putString("config", rules.json())
                          .apply();
                      rebuildRows(false);
                      dialog.dismiss();
                    }));
    dialog.show();
  }

  private int positive(EditText field, int minimum) {
    try {
      int value = Integer.parseInt(field.getText().toString());
      if (value < minimum || value > 100000) throw new NumberFormatException();
      return value;
    } catch (NumberFormatException invalid) {
      field.setError("Enter a whole number from " + minimum + " to 100000");
      field.requestFocus();
      throw new IllegalArgumentException(invalid);
    }
  }

  private int dp(float value) {
    return Ui.dp(this, value);
  }

  @Override
  protected void onSaveInstanceState(Bundle out) {
    out.putInt("tab", tab);
    out.putInt("priority", priorityValue);
    out.putInt("week", selectedWeek);
    out.putStringArray("queries", queries);
    out.putStringArrayList("expanded", new ArrayList<>(expanded));
    out.putParcelable("scroll", layout.onSaveInstanceState());
    super.onSaveInstanceState(out);
  }

  @Override
  protected void onDestroy() {
    handler.removeCallbacks(updateSearch);
    super.onDestroy();
  }
}
