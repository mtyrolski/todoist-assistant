package com.todoistassistant;

import org.json.JSONArray;
import org.json.JSONObject;

/** Projects immutable cached data into the shared web dashboard. Never includes credentials. */
final class MobilePayload {
  static JSONObject model(DashboardModel model) throws Exception {
    JSONArray tasks = new JSONArray(), projects = new JSONArray(), activity = new JSONArray();
    for (var task : model.tasks)
      tasks.put(
          new JSONObject()
              .put("id", task.id)
              .put("projectId", task.projectId)
              .put("content", task.content)
              .put("project", task.project)
              .put("priority", task.priority)
              .put("due", task.due)
              .put("deadline", task.deadline)
              .put("labels", new JSONArray(task.labels)));
    for (var project : model.projects)
      projects.put(new JSONObject().put("id", project.id).put("path", project.path));
    for (var event : model.recent)
      activity.put(
          new JSONObject()
              .put("id", event.id)
              .put("kind", event.kind)
              .put("content", event.content)
              .put("project", event.project)
              .put("date", event.date.toString()));
    JSONArray weeks = new JSONArray();
    for (var counts : model.weeklyProjects) weeks.put(new JSONObject(counts));
    JSONObject payload =
        new JSONObject()
            .put("syncedAt", model.syncedAt.toString())
            .put("weekStart", model.weekStart.toString())
            .put("weeks", new JSONArray(model.weeks))
            .put("priorities", new JSONArray(model.priorities))
            .put("forecast", model.forecast)
            .put("forecastAvailable", model.forecastAvailable)
            .put("historyAvailable", model.historyAvailable)
            .put("historyWarning", model.historyWarning)
            .put("plotData", model.plotData)
            .put("weeklyProjects", weeks)
            .put("projectForecasts", new JSONObject(model.projectForecasts))
            .put("projectColors", new JSONObject(model.projectColors))
            .put("adjustments", model.adjustments)
            .put("tasks", tasks)
            .put("projects", projects)
            .put("activity", activity);
    if (model.historyAvailable && model.activitySyncExclusive)
      payload.put("activitySyncedAt", model.activitySyncedAt.toString());
    return payload;
  }
}
