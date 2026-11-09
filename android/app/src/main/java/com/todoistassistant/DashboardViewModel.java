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
  private final ExecutorService requests =
      new java.util.concurrent.ThreadPoolExecutor(
          0,
          2,
          30,
          java.util.concurrent.TimeUnit.SECONDS,
          new java.util.concurrent.SynchronousQueue<>());
  private final Object requestLock = new Object();
  private final Handler main = new Handler(Looper.getMainLooper());
  private final TokenStore tokens;
  private final SnapshotStore store;
  private final java.util.function.Function<String, ApiTransport> transports;
  private final AtomicInteger generation = new AtomicInteger();
  private final AtomicBoolean committing = new AtomicBoolean();
  private volatile ApiTransport transport;
  private Future<?> task;
  private volatile JSONObject snapshot = new JSONObject();
  private volatile String token = "";
  private volatile DashboardModel savedModel;
  private volatile long retryAfter;
  private volatile boolean rejected, hasSavedHistory, recoveryRequired;
  private volatile String rejectedToken = "";

  public DashboardViewModel(Application application) {
    this(application, HttpTransport::new);
  }

  DashboardViewModel(
      Application application, java.util.function.Function<String, ApiTransport> transports) {
    this(application, transports, new TokenStore(application), new SnapshotStore(application));
  }

  DashboardViewModel(
      Application application,
      java.util.function.Function<String, ApiTransport> transports,
      TokenStore tokens,
      SnapshotStore store) {
    super(application);
    this.transports = transports;
    this.tokens = tokens;
    this.store = store;
    task =
        worker.submit(
            () -> {
              String warning = "";
              hasSavedHistory = store.exists();
              try {
                String pending = "";
                try {
                  pending = tokens.loadPending();
                } catch (Exception invalidPending) {
                  android.util.Log.w("Todometry", "Staged credential could not be opened");
                }
                boolean pendingMatches = false;
                if (!pending.isEmpty()) {
                  try {
                    pendingMatches = store.isBoundTo(pending);
                  } catch (Exception invalidHistory) {
                    // The normal load below reports the history error without deleting anything.
                  }
                }
                if (pendingMatches) {
                  JSONObject recovered = store.load(pending);
                  DashboardModel recoveredModel =
                      new DashboardModel(recovered, Clock.systemDefaultZone());
                  tokens.promotePending();
                  token = pending;
                  snapshot = recovered;
                  savedModel = recoveredModel;
                } else {
                  token = tokens.load();
                  snapshot = store.load(token);
                  if (snapshot.has("syncedAt"))
                    savedModel = new DashboardModel(snapshot, Clock.systemDefaultZone());
                  if (!pending.isEmpty()) tokens.discardPending();
                }
              } catch (Exception exception) {
                warning =
                    "Saved credentials or history could not be opened. Enter your token to recover,"
                        + " or disconnect to remove saved data.";
              }
              rejected = tokens.isRejected();
              if (rejected && !token.isEmpty() && warning.isEmpty())
                warning =
                    "Your saved Todoist token was rejected. Enter a new token in Control Panel.";
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

  boolean hasSavedHistory() {
    return hasSavedHistory;
  }

  void sync(String candidate) {
    State current = state.getValue();
    if (current == null || current.syncing || current.loading) return;
    if (recoveryRequired) {
      state.setValue(
          new State(
              savedModel,
              false,
              false,
              false,
              !token.isEmpty(),
              "Credential update needs recovery. Restart the app before syncing."));
      return;
    }
    String requestedToken = candidate.trim().isEmpty() ? token : candidate.trim();
    if (requestedToken.isEmpty()) return;
    if (requestedToken
        .chars()
        .anyMatch(c -> Character.isWhitespace(c) || Character.isISOControl(c))) {
      state.setValue(
          new State(
              current.demo ? savedModel : current.model,
              false,
              false,
              false,
              !token.isEmpty(),
              "A Todoist token cannot contain spaces or control characters."));
      return;
    }
    if ((rejected && requestedToken.equals(token)) || requestedToken.equals(rejectedToken)) {
      state.setValue(
          new State(
              current.demo ? savedModel : current.model,
              false,
              false,
              false,
              !token.isEmpty(),
              "This Todoist token was rejected. Enter a different token to reconnect."));
      return;
    }
    if (android.os.SystemClock.elapsedRealtime() < retryAfter) {
      state.setValue(
          new State(
              current.demo ? savedModel : current.model,
              false,
              false,
              false,
              !token.isEmpty(),
              "Todoist asked the app to wait before retrying. Saved data is unchanged."));
      return;
    }
    int request = generation.incrementAndGet();
    boolean trustLegacy = requestedToken.equals(token);
    JSONObject baseline = snapshot;
    DashboardModel visible = current.demo ? savedModel : current.model;
    state.setValue(
        new State(visible, false, true, false, !token.isEmpty(), "Connecting to Todoist…"));
    try {
      task =
          requests.submit(
              () -> {
                ApiTransport active = null;
                try {
                  active = transports.apply(requestedToken);
                  synchronized (requestLock) {
                    if (generation.get() != request || Thread.currentThread().isInterrupted()) {
                      active.cancel();
                      return;
                    }
                    transport = active;
                  }
                  JSONObject previous = baseline;
                  if (hasSavedHistory && !baseline.has("syncedAt")) {
                    try {
                      String currentToken = token;
                      previous =
                          worker
                              .submit(
                                  () -> {
                                    boolean candidateMatches = store.isBoundTo(requestedToken);
                                    if (!candidateMatches && currentToken.isEmpty())
                                      throw new java.io.IOException(
                                          "History does not match credential");
                                    String historyToken =
                                        candidateMatches ? requestedToken : currentToken;
                                    JSONObject recovered = store.load(historyToken);
                                    new DashboardModel(recovered, Clock.systemDefaultZone());
                                    return recovered;
                                  })
                              .get();
                    } catch (java.util.concurrent.ExecutionException invalidHistory) {
                      throw new HttpTransport.Failure(
                          "Saved history could not be verified with this token. Re-enter the original token or disconnect to remove saved data.");
                    }
                  }
                  JSONObject previousSnapshot = previous;
                  TodoistClient client =
                      new TodoistClient(
                          active,
                          Clock.systemDefaultZone(),
                          message ->
                              post(
                                  request,
                                  new State(
                                      savedModel == null ? visible : savedModel,
                                      false,
                                      true,
                                      false,
                                      !token.isEmpty(),
                                      message)));
                  JSONObject next =
                      client.snapshot(
                          previousSnapshot,
                          trustLegacy,
                          partial -> {
                            String owner = previousSnapshot.optString("userId");
                            if (previousSnapshot.has("syncedAt")
                                && !(owner.equals(partial.optString("userId"))
                                    || (owner.isEmpty() && trustLegacy))) return;
                            commitSnapshot(
                                new JSONObject(partial.toString()), requestedToken, request);
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
                  post(
                      request,
                      new State(
                          visible, false, true, false, !token.isEmpty(), "Saving on this device…"));
                  DashboardModel model = commitSnapshot(next, requestedToken, request);
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
                } catch (Exception exception) {
                  if (exception instanceof HttpTransport.AuthenticationFailure) {
                    boolean savedTokenRejected;
                    synchronized (requestLock) {
                      savedTokenRejected =
                          generation.get() == request && requestedToken.equals(token);
                      if (generation.get() == request) rejectedToken = requestedToken;
                      if (savedTokenRejected) rejected = true;
                    }
                    if (savedTokenRejected) {
                      try {
                        worker
                            .submit(
                                () -> {
                                  if (requestedToken.equals(token)) tokens.markRejected();
                                  return null;
                                })
                            .get();
                      } catch (Exception failure) {
                        android.util.Log.w("Todometry", "Could not persist authentication status");
                      }
                    }
                  }
                  if (exception instanceof HttpTransport.Failure) {
                    synchronized (requestLock) {
                      long delay = ((HttpTransport.Failure) exception).retryAfterMillis;
                      long now = android.os.SystemClock.elapsedRealtime();
                      if (delay > 0 && generation.get() == request)
                        retryAfter = delay > Long.MAX_VALUE - now ? Long.MAX_VALUE : now + delay;
                    }
                  }
                  if (generation.get() == request) {
                    android.util.Log.w(
                        "Todometry", "Sync failed: " + exception.getClass().getSimpleName());
                    post(
                        request,
                        new State(
                            savedModel == null ? visible : savedModel,
                            false,
                            false,
                            false,
                            !token.isEmpty(),
                            errorMessage(exception)));
                  }
                } finally {
                  synchronized (requestLock) {
                    if (transport == active) transport = null;
                  }
                }
              });
    } catch (java.util.concurrent.RejectedExecutionException busy) {
      if (generation.get() == request)
        state.setValue(
            new State(
                savedModel == null ? visible : savedModel,
                false,
                false,
                false,
                !token.isEmpty(),
                "Previous syncs are still stopping. Please retry in a moment."));
    }
  }

  private DashboardModel commitSnapshot(JSONObject next, String requestedToken, int request)
      throws Exception {
    try {
      return worker
          .submit(
              () -> {
                synchronized (requestLock) {
                  if (generation.get() != request || Thread.currentThread().isInterrupted())
                    throw new SyncCancelledException();
                  committing.set(true);
                }
                try {
                  DashboardModel model = new DashboardModel(next, Clock.systemDefaultZone());
                  store.save(
                      next,
                      requestedToken,
                      () -> {
                        if (!requestedToken.equals(token)) tokens.stage(requestedToken);
                      });
                  hasSavedHistory = true;
                  if (!requestedToken.equals(token)) {
                    try {
                      if (!store.isBoundTo(requestedToken))
                        throw new java.io.IOException("Could not verify the saved history");
                      tokens.promotePending();
                    } catch (Exception failure) {
                      recoveryRequired = true;
                      throw new HttpTransport.Failure(
                          "Credential update needs recovery. Restart the app before syncing.");
                    }
                  }
                  token = requestedToken;
                  snapshot = next;
                  savedModel = model;
                  rejected = false;
                  rejectedToken = "";
                  return model;
                } finally {
                  committing.set(false);
                }
              })
          .get();
    } catch (java.util.concurrent.ExecutionException failure) {
      if (failure.getCause() instanceof Exception) throw (Exception) failure.getCause();
      throw new IllegalStateException("Could not save the dashboard", failure.getCause());
    }
  }

  void cancelSync() {
    State current = state.getValue();
    if (current == null || !current.syncing) return;
    ApiTransport active;
    synchronized (requestLock) {
      if (committing.get()) return;
      generation.incrementAndGet();
      active = transport;
    }
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
    refreshClock();
  }

  void refreshClock() {
    refreshClock(Clock.systemDefaultZone());
  }

  void refreshClock(Clock clock) {
    State current = state.getValue();
    if (current == null || current.loading || current.syncing || current.model == null) return;
    if (current.model.zoneId.equals(clock.getZone())
        && current.model.renderedOn.equals(java.time.LocalDate.now(clock))) return;
    int request = generation.incrementAndGet();
    JSONObject saved = snapshot;
    state.setValue(
        new State(
            current.model, true, false, current.demo, !token.isEmpty(), "Updating local dates…"));
    task =
        worker.submit(
            () -> {
              try {
                DashboardModel updated =
                    new DashboardModel(current.demo ? DemoData.create(clock) : saved, clock);
                if (generation.get() != request || Thread.currentThread().isInterrupted()) return;
                if (!current.demo) savedModel = updated;
                post(
                    request,
                    new State(
                        updated, false, false, current.demo, !token.isEmpty(), current.message));
              } catch (Exception invalid) {
                post(
                    request,
                    new State(
                        current.model,
                        false,
                        false,
                        current.demo,
                        !token.isEmpty(),
                        "Could not update local dates. Saved data is unchanged."));
              }
            });
  }

  void importAdjustments(Uri uri) {
    State current = state.getValue();
    if (!canEditAdjustments(current)) return;
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
                applyAdjustments(
                    ProjectAdjustments.merge(
                        snapshot.optJSONObject("adjustments"),
                        ProjectAdjustments.parse(
                            output.toString(java.nio.charset.StandardCharsets.UTF_8.name()))),
                    request,
                    "Project adjustments imported.");
              } catch (Exception exception) {
                post(
                    request,
                    new State(
                        current.model,
                        false,
                        false,
                        false,
                        true,
                        "Could not import adjustments. Choose the JSON file exported from the"
                            + " desktop dashboard."));
              }
            });
  }

  void saveAdjustments(String text) {
    State current = state.getValue();
    if (!canEditAdjustments(current)) return;
    int request = generation.incrementAndGet();
    state.setValue(
        new State(current.model, true, false, false, true, "Saving project adjustments…"));
    task =
        worker.submit(
            () -> {
              try {
                if (text == null
                    || text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 256 * 1024)
                  throw new IllegalArgumentException("Invalid adjustments");
                applyAdjustments(
                    ProjectAdjustments.parse(text), request, "Project adjustments saved.");
              } catch (Exception exception) {
                post(
                    request,
                    new State(
                        current.model,
                        false,
                        false,
                        false,
                        true,
                        "Could not save project adjustments. Check the project names and try"
                            + " again."));
              }
            });
  }

  private boolean canEditAdjustments(State current) {
    return current != null
        && !current.syncing
        && !current.loading
        && !current.demo
        && !recoveryRequired
        && !token.isEmpty()
        && savedModel != null;
  }

  private void applyAdjustments(JSONObject adjustments, int request, String message)
      throws Exception {
    JSONObject next = new JSONObject(snapshot.toString()).put("adjustments", adjustments);
    DashboardModel model = new DashboardModel(next, Clock.systemDefaultZone());
    if (generation.get() != request || Thread.currentThread().isInterrupted()) return;
    committing.set(true);
    try {
      if (generation.get() != request) return;
      store.save(next, token);
      snapshot = next;
      savedModel = model;
      post(request, new State(model, false, false, false, true, message));
    } finally {
      committing.set(false);
    }
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
              boolean historyCleared = !store.exists();
              boolean credentialsCleared = tokens.clear();
              boolean settingsCleared =
                  getApplication()
                      .getSharedPreferences("rules", android.content.Context.MODE_PRIVATE)
                      .edit()
                      .clear()
                      .commit();
              token = "";
              snapshot = new JSONObject();
              savedModel = null;
              hasSavedHistory = !historyCleared;
              rejected = false;
              rejectedToken = "";
              recoveryRequired = false;
              main.post(
                  () ->
                      state.setValue(
                          new State(
                              null,
                              false,
                              false,
                              false,
                              false,
                              !credentialsCleared || !historyCleared
                                  ? "Could not remove all saved account data. Clear app data in Android Settings."
                                  : settingsCleared
                                      ? "Account disconnected. Local history and settings have been"
                                          + " removed."
                                      : "Account disconnected. Could not remove local settings; clear"
                                          + " app data in Android Settings.")));
            });
  }

  private void post(int request, State value) {
    main.post(
        () -> {
          if (generation.get() == request) state.setValue(value);
        });
  }

  private String errorMessage(Exception exception) {
    if (exception instanceof java.net.SocketTimeoutException)
      return "The connection timed out. Saved data is unchanged; try again on a stable connection.";
    if (exception instanceof java.io.EOFException)
      return "The connection to Todoist was interrupted. Saved data is unchanged; retry sync.";
    if (exception instanceof java.net.UnknownHostException
        || exception instanceof java.net.SocketException) {
      android.net.ConnectivityManager manager =
          getApplication().getSystemService(android.net.ConnectivityManager.class);
      android.net.Network network = manager == null ? null : manager.getActiveNetwork();
      android.net.NetworkCapabilities capabilities =
          network == null ? null : manager.getNetworkCapabilities(network);
      if (capabilities == null
          || !capabilities.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET))
        return "No network connection. Saved data is unchanged; reconnect and retry sync.";
      return "Todoist is unreachable. Saved data is unchanged; retry sync when it is available.";
    }
    if (exception instanceof InterruptedException || exception instanceof SyncCancelledException)
      return "Sync cancelled. Saved data is unchanged.";
    if (exception instanceof HttpTransport.Failure || exception instanceof DataAccessException)
      return exception.getMessage();
    if (exception instanceof org.json.JSONException
        || exception instanceof java.time.format.DateTimeParseException)
      return "Todoist returned an incompatible response. Saved data is unchanged; please retry.";
    return "Sync failed. Saved data is unchanged. Please retry.";
  }

  @Override
  protected void onCleared() {
    generation.incrementAndGet();
    ApiTransport active = transport;
    if (active != null) active.cancel();
    requests.shutdownNow();
    worker.shutdownNow();
  }
}
