package com.todoistassistant;

import android.app.Application;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import androidx.lifecycle.AndroidViewModel;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import java.time.Clock;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.json.JSONObject;

/** Owns IO and survives Activity recreation. No Activity or View is retained. */
public final class DashboardViewModel extends AndroidViewModel {
  static final class State {
    final DashboardModel model;
    final boolean loading, syncing, demo, connected;
    final String message;

    State(
        DashboardModel model,
        boolean loading,
        boolean syncing,
        boolean demo,
        boolean connected,
        String message) {
      this.model = model;
      this.loading = loading;
      this.syncing = syncing;
      this.demo = demo;
      this.connected = connected;
      this.message = message;
    }
  }

  private final MutableLiveData<State> state =
      new MutableLiveData<>(new State(null, true, false, false, false, "Opening saved history…"));
  private final ExecutorService worker = Executors.newSingleThreadExecutor();
  private final Handler main = new Handler(Looper.getMainLooper());
  private final TokenStore tokens;
  private final SnapshotStore store;
  private final java.util.function.Function<String, ApiTransport> transports;
  private final AtomicInteger generation = new AtomicInteger();
  private final AtomicBoolean committing = new AtomicBoolean();
  private volatile ApiTransport transport;
  private Future<?> task;
  private JSONObject snapshot = new JSONObject();
  private String token = "";
  private DashboardModel savedModel;

  public DashboardViewModel(Application application) {
    this(application, HttpTransport::new);
  }

  DashboardViewModel(
      Application application, java.util.function.Function<String, ApiTransport> transports) {
    super(application);
    this.transports = transports;
    tokens = new TokenStore(application);
    store = new SnapshotStore(application);
    task =
        worker.submit(
            () -> {
              String warning = "";
              try {
                token = tokens.load();
                snapshot = store.load(token);
                if (snapshot.has("syncedAt"))
                  savedModel = new DashboardModel(snapshot, Clock.systemDefaultZone());
              } catch (Exception exception) {
                warning =
                    "Saved history could not be opened. Sync to recover it, or reconnect in Control Panel.";
              }
              String message = warning;
              main.post(
                  () -> {
                    state.setValue(
                        new State(savedModel, false, false, false, !token.isEmpty(), message));
                    if (!token.isEmpty() && message.isEmpty()) sync("");
                  });
            });
  }

  LiveData<State> state() {
    return state;
  }

  void sync(String candidate) {
    State current = state.getValue();
    if (current == null || current.syncing || current.loading) return;
    String requestedToken = candidate.trim().isEmpty() ? token : candidate.trim();
    if (requestedToken.isEmpty()) return;
    int request = generation.incrementAndGet();
    boolean trustLegacy = requestedToken.equals(token);
    DashboardModel visible = current.demo ? savedModel : current.model;
    state.setValue(
        new State(visible, false, true, false, !token.isEmpty(), "Connecting to Todoist…"));
    task =
        worker.submit(
            () -> {
              ApiTransport active = transports.apply(requestedToken);
              transport = active;
              try {
                TodoistClient client =
                    new TodoistClient(
                        active,
                        Clock.systemDefaultZone(),
                        message ->
                            post(
                                request,
                                new State(visible, false, true, false, !token.isEmpty(), message)));
                JSONObject next =
                    client.snapshot(
                        snapshot,
                        trustLegacy,
                        partial -> {
                          String owner = snapshot.optString("userId");
                          if (snapshot.has("syncedAt")
                              && !(owner.equals(partial.optString("userId"))
                                  || (owner.isEmpty() && trustLegacy))) return;
                          if (generation.get() != request || Thread.currentThread().isInterrupted())
                            throw new SyncCancelledException();
                          committing.set(true);
                          try {
                            if (generation.get() != request) throw new SyncCancelledException();
                            JSONObject saved = new JSONObject(partial.toString());
                            store.save(
                                saved,
                                requestedToken,
                                () -> {
                                  if (!requestedToken.equals(token)) tokens.save(requestedToken);
                                });
                            token = requestedToken;
                            snapshot = saved;
                            savedModel = new DashboardModel(saved, Clock.systemDefaultZone());
                          } finally {
                            committing.set(false);
                          }
                        });
                post(
                    request,
                    new State(
                        visible,
                        false,
                        true,
                        false,
                        !token.isEmpty(),
                        "Preparing your dashboard…"));
                DashboardModel model = new DashboardModel(next, Clock.systemDefaultZone());
                if (generation.get() != request || Thread.currentThread().isInterrupted()) return;
                committing.set(true);
                try {
                  if (generation.get() != request) return;
                  post(
                      request,
                      new State(
                          visible, false, true, false, !token.isEmpty(), "Saving on this device…"));
                  store.save(
                      next,
                      requestedToken,
                      () -> {
                        if (!requestedToken.equals(token)) tokens.save(requestedToken);
                      });
                  token = requestedToken;
                  snapshot = next;
                  savedModel = model;
                  post(
                      request,
                      new State(
                          model,
                          false,
                          false,
                          false,
                          true,
                          model.historyWarning.isEmpty()
                              ? "Sync complete. Your history is available offline."
                              : "Saved on device. Some history details could not be refreshed."));
                } finally {
                  committing.set(false);
                }
              } catch (Exception exception) {
                if (generation.get() == request)
                  post(
                      request,
                      new State(
                          savedModel == null ? visible : savedModel,
                          false,
                          false,
                          false,
                          !token.isEmpty(),
                          errorMessage(exception)));
              } finally {
                if (transport == active) transport = null;
              }
            });
  }

  void cancelSync() {
    State current = state.getValue();
    if (current == null || !current.syncing || committing.get()) return;
    generation.incrementAndGet();
    ApiTransport active = transport;
    if (active != null) active.cancel();
    if (task != null) task.cancel(true);
    state.setValue(
        new State(
            savedModel == null ? current.model : savedModel,
            false,
            false,
            false,
            !token.isEmpty(),
            "Sync cancelled. Saved history is still available."));
  }

  void showDemo() {
    State current = state.getValue();
    if (current == null || current.syncing || current.loading) return;
    int request = generation.incrementAndGet();
    state.setValue(
        new State(
            current.model, true, false, false, !token.isEmpty(), "Preparing an offline example…"));
    task =
        worker.submit(
            () -> {
              try {
                DashboardModel model =
                    new DashboardModel(
                        DemoData.create(Clock.systemDefaultZone()), Clock.systemDefaultZone());
                post(
                    request,
                    new State(
                        model,
                        false,
                        false,
                        true,
                        !token.isEmpty(),
                        "Demo data · your saved account history is unchanged."));
              } catch (Exception exception) {
                post(
                    request,
                    new State(
                        savedModel,
                        false,
                        false,
                        false,
                        !token.isEmpty(),
                        "Could not open the example."));
              }
            });
  }

  void exitDemo() {
    generation.incrementAndGet();
    state.setValue(new State(savedModel, false, false, false, !token.isEmpty(), ""));
  }

  void importAdjustments(Uri uri) {
    State current = state.getValue();
    if (current == null
        || current.syncing
        || current.loading
        || current.demo
        || token.isEmpty()
        || savedModel == null) return;
    int request = generation.incrementAndGet();
    state.setValue(
        new State(current.model, true, false, false, true, "Importing project adjustments…"));
    task =
        worker.submit(
            () -> {
              try (var input = getApplication().getContentResolver().openInputStream(uri);
                  var output = new java.io.ByteArrayOutputStream()) {
                if (input == null) throw new java.io.IOException("File unavailable");
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) != -1) {
                  if (output.size() + count > 256 * 1024)
                    throw new java.io.IOException("File too large");
                  output.write(buffer, 0, count);
                }
                JSONObject next = new JSONObject(snapshot.toString());
                next.put(
                    "adjustments",
                    ProjectAdjustments.parse(
                        output.toString(java.nio.charset.StandardCharsets.UTF_8.name())));
                DashboardModel model = new DashboardModel(next, Clock.systemDefaultZone());
                if (generation.get() != request || Thread.currentThread().isInterrupted()) return;
                store.save(next, token);
                snapshot = next;
                savedModel = model;
                post(
                    request,
                    new State(model, false, false, false, true, "Project adjustments imported."));
              } catch (Exception exception) {
                post(
                    request,
                    new State(
                        current.model,
                        false,
                        false,
                        false,
                        true,
                        "Could not import adjustments. Choose the JSON file exported from the desktop dashboard."));
              }
            });
  }

  void disconnect() {
    generation.incrementAndGet();
    ApiTransport active = transport;
    if (active != null) active.cancel();
    if (task != null && !committing.get()) task.cancel(true);
    state.setValue(new State(null, true, false, false, false, "Removing local account data…"));
    task =
        worker.submit(
            () -> {
              store.clear();
              tokens.clear();
              boolean settingsCleared =
                  getApplication()
                      .getSharedPreferences("rules", android.content.Context.MODE_PRIVATE)
                      .edit()
                      .clear()
                      .commit();
              token = "";
              snapshot = new JSONObject();
              savedModel = null;
              main.post(
                  () ->
                      state.setValue(
                          new State(
                              null,
                              false,
                              false,
                              false,
                              false,
                              settingsCleared
                                  ? "Account disconnected. Local history and settings have been removed."
                                  : "Account disconnected. Could not remove local settings; clear app data in Android Settings.")));
            });
  }

  private void post(int request, State value) {
    main.post(
        () -> {
          if (generation.get() == request) state.setValue(value);
        });
  }

  private static String errorMessage(Exception exception) {
    if (exception instanceof java.net.UnknownHostException
        || exception instanceof java.net.ConnectException)
      return "You're offline or Todoist is unreachable. Saved data is still available; try Sync when connected.";
    if (exception instanceof java.net.SocketTimeoutException)
      return "The connection timed out. Saved data is unchanged; try again on a stable connection.";
    if (exception instanceof InterruptedException || exception instanceof SyncCancelledException)
      return "Sync cancelled. Saved data is unchanged.";
    return exception.getMessage() == null
        ? "Sync failed. Saved data is unchanged. Please retry."
        : exception.getMessage();
  }

  @Override
  protected void onCleared() {
    generation.incrementAndGet();
    ApiTransport active = transport;
    if (active != null) active.cancel();
    worker.shutdownNow();
  }
}
