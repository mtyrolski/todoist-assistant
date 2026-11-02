package com.todoistassistant;

import org.json.JSONArray;
import org.json.JSONObject;

/** Validates the portable project adjustments exported by the desktop dashboard. */
final class ProjectAdjustments {
  static JSONObject parse(String text) throws Exception {
    JSONObject data = new JSONObject(text);
    if (!data.optString("format").equals("todoist-assistant-project-adjustments-v1"))
      throw new IllegalArgumentException("Unexpected file format");
    JSONObject mappings = data.getJSONObject("mappings");
    JSONArray parents = data.getJSONArray("archivedParents");
    for (var keys = mappings.keys(); keys.hasNext(); ) {
      String key = keys.next();
      if (key.trim().isEmpty()
          || !(mappings.opt(key) instanceof String)
          || mappings.getString(key).trim().isEmpty())
        throw new IllegalArgumentException("Invalid project mapping");
    }
    for (int i = 0; i < parents.length(); i++)
      if (!(parents.opt(i) instanceof String) || parents.getString(i).trim().isEmpty())
        throw new IllegalArgumentException("Invalid archived parent");
    return new JSONObject().put("mappings", mappings).put("archivedParents", parents);
  }

  static JSONObject merge(JSONObject existing, JSONObject incoming) throws Exception {
    JSONObject previousMappings = existing == null ? null : existing.optJSONObject("mappings");
    JSONObject mappings =
        previousMappings == null ? new JSONObject() : new JSONObject(previousMappings.toString());
    JSONObject importedMappings = incoming.getJSONObject("mappings");
    for (var keys = importedMappings.keys(); keys.hasNext(); ) {
      String key = keys.next();
      mappings.put(key, importedMappings.getString(key));
    }
    java.util.Set<String> parents = new java.util.LinkedHashSet<>();
    JSONArray previousParents = existing == null ? null : existing.optJSONArray("archivedParents");
    JSONArray importedParents = incoming.getJSONArray("archivedParents");
    java.util.Set<String> importedParentNames = new java.util.LinkedHashSet<>();
    for (int i = 0; i < importedParents.length(); i++)
      importedParentNames.add(importedParents.getString(i));
    if (previousParents != null)
      for (int i = 0; i < previousParents.length(); i++) {
        String parent = previousParents.getString(i);
        if (!importedMappings.has(parent) || importedParentNames.contains(parent))
          parents.add(parent);
      }
    parents.addAll(importedParentNames);
    return new JSONObject()
        .put("mappings", mappings)
        .put("archivedParents", new JSONArray(parents));
  }
}
