"use client";

import { useEffect, useMemo, useRef } from "react";
import { command, normalizeSearch, type MobileModel } from "../lib/mobile";

/** Individual project rules coexist with legacy name-based desktop exports. */
export function ProjectGrouping({ model, enabled, busy, message, draft, onDraftChange }: {
  model: MobileModel | null;
  enabled: boolean;
  busy: boolean;
  message: string;
  draft: { search: string; source: string; target: string; customSource: string; customTarget: string; sourceId: string; targetId: string; targetSearch: string };
  onDraftChange: (draft: { search: string; source: string; target: string; customSource: string; customTarget: string; sourceId: string; targetId: string; targetSearch: string }) => void;
}) {
  const { search, source, target, customSource, customTarget, sourceId, targetId, targetSearch } = draft;
  const change = (value: Partial<typeof draft>) => onDraftChange({ ...draft, ...value });
  const adjustments = model?.adjustments;
  const mappings = adjustments?.mappings ?? {};
  const archivedParents = adjustments?.archivedParents ?? [];
  const projectMappings = adjustments?.projectMappings ?? {};
  const hierarchy = model?.plotData?.hierarchy ?? [];
  const savedMapping = (name: string) => Object.prototype.hasOwnProperty.call(mappings, name) ? mappings[name] : undefined;
  const savedProjectRule = (id: string) => Object.prototype.hasOwnProperty.call(projectMappings, id) ? projectMappings[id] : undefined;
  const sources = useMemo(() => [...new Set([
    ...hierarchy.filter((project) => project.archived).map((project) => project.name),
    ...Object.keys(mappings),
    ...archivedParents,
    source,
  ].filter(Boolean))].sort((a, b) => a.localeCompare(b)), [hierarchy, mappings, archivedParents, source]);
  const targets = useMemo(() => {
    const identityLabels = new Set([
      ...hierarchy.map((project) => `${project.name} · ${project.id}`),
      ...Object.values(projectMappings).map((rule) => `${rule.targetName} · ${rule.targetId}`),
    ]);
    return [...new Set([
      ...hierarchy.filter((project) => project.metadataKnown !== false && project.name !== "Unknown project").map((project) => project.name),
      ...hierarchy.map((project) => project.rootName).filter((name) => name && name !== "Unknown project" && !identityLabels.has(name)),
      ...archivedParents,
      ...Object.values(mappings),
      target,
    ].filter(Boolean))].sort((a, b) => a.localeCompare(b));
  }, [hierarchy, mappings, archivedParents, projectMappings, target]);
  const nameCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const project of hierarchy) counts.set(project.name, (counts.get(project.name) ?? 0) + 1);
    return counts;
  }, [hierarchy]);
  const archivedNames = useMemo(() => new Set(hierarchy.filter((project) => project.archived).map((project) => project.name)), [hierarchy]);
  const previousNames = useMemo(() => {
    const names = new Map<string, Set<string>>();
    for (const project of hierarchy) {
      if (!names.has(project.name)) names.set(project.name, new Set());
      for (const name of project.previousNames ?? []) names.get(project.name)?.add(name);
    }
    return names;
  }, [hierarchy]);
  const formerMatch = (name: string, query: string) => {
    const term = normalizeSearch(query);
    if (!term || normalizeSearch(name).includes(term)) return "";
    return [...(previousNames.get(name) ?? [])].find((old) => normalizeSearch(old).includes(term)) ?? "";
  };
  const matchesSearch = (name: string, query: string) => normalizeSearch(name).includes(normalizeSearch(query)) || Boolean(formerMatch(name, query));
  const namedProjects = hierarchy.filter((project) => project.name === source);
  const matchingProjects = sourceId ? namedProjects.filter((project) => project.id === sourceId) : namedProjects;
  const targetProjects = hierarchy.filter((project) => project.name === target);
  const idSource = sourceId ? hierarchy.find((project) => project.id === sourceId) : undefined;
  const invalidSourceId = Boolean(sourceId && !matchingProjects.length);
  const idTarget = targetId ? hierarchy.find((project) => project.id === targetId) : undefined;
  const invalidTargetId = Boolean(targetId && (!idTarget || idTarget.name !== target));
  const targetProjectId = targetId || (targetProjects.length === 1 ? targetProjects[0].id : "");
  const sourceRule = sourceId ? savedProjectRule(sourceId) : undefined;
  const ruleName = (rule: { targetId: string; targetName: string }) => hierarchy.find((project) => project.id === rule.targetId)?.name ?? rule.targetName;
  const roots = [...new Set(matchingProjects.map((project) => project.rootName).filter(Boolean))];
  const existing = savedMapping(source);
  const ownGroup = archivedParents.includes(source);
  const sourceKnown = matchingProjects.length > 0;
  const activeOnly = sourceKnown && matchingProjects.every((project) => !project.archived);
  const activeChildOnly = activeOnly && matchingProjects.some((project) => Boolean(project.parentId));
  const mixedStatus = matchingProjects.some((project) => project.archived) && matchingProjects.some((project) => !project.archived);
  const noRecordedParent = sourceKnown && matchingProjects.every((project) => project.archived && !project.parentId && (project.rootName === source || project.rootName === `${source} · ${project.id}`));
  const currentGrouping = sourceRule ? sourceRule.targetId === sourceId ? "Own group (this project)" : `${ruleName(sourceRule)} (this project)` : roots.length > 1 ? "Multiple groups" : activeOnly && roots.length === 1 ? roots[0] : ownGroup ? "Own group" : existing ? `${existing} (name rule)` : noRecordedParent ? "No parent recorded; shown under its own name" : roots.length === 1 ? `${roots[0]} (from available project data)` : "No parent recorded";
  const editable = enabled && !busy;
  const filteredSources = sources.filter((name) => matchesSearch(name, search));
  const availableTargets = targets.filter((name) => name !== source || name === existing || (sourceId && namedProjects.length > 1));
  const filteredTargets = availableTargets.filter((name) => matchesSearch(name, targetSearch));
  const wouldCreateCycle = (() => {
    if (sourceId && targetProjectId) {
      const seen = new Set<string>();
      let id = targetProjectId;
      while (id && !seen.has(id)) {
        if (id === sourceId) return true;
        seen.add(id);
        const mapped = savedProjectRule(id)?.targetId;
        if (mapped === id) return false;
        const project = hierarchy.find((item) => item.id === id);
        if (project && (project.rootName === `${source} · ${sourceId}` || (namedProjects.length === 1 && project.rootName === source))) return true;
        id = mapped || project?.parentId || "";
      }
      return false;
    }
    const seen = new Set<string>();
    let name = target;
    while (source && name && !seen.has(name)) {
      if (name === source) return true;
      seen.add(name);
      const matches = hierarchy.filter((project) => project.name === name);
      const active = matches.filter((project) => !project.archived);
      const archived = matches.filter((project) => project.archived);
      const project = active.length === 1 ? active[0] : active.length === 0 && archived.length === 1 ? archived[0] : undefined;
      if (project?.archived && archivedParents.includes(name)) return false;
      if (project?.rootName === source) return true;
      if (project && !project.archived && project.parentId) return false;
      const next = savedMapping(name);
      if (!next || next === name) return false;
      name = next;
    }
    return false;
  })();
  const previous = useRef({ source, mapping: existing });
  useEffect(() => {
    const renamedSource = idSource && idSource.name !== source ? idSource.name : undefined;
    const renamedTarget = idTarget && idTarget.name !== target ? idTarget.name : undefined;
    if (renamedSource || renamedTarget) onDraftChange({ ...draft, ...(renamedSource ? { source: renamedSource } : {}), ...(renamedTarget ? { target: renamedTarget } : {}) });
  }, [idSource?.name, idTarget?.name, source, target, draft, onDraftChange]);
  useEffect(() => {
    const old = previous.current;
    previous.current = { source, mapping: existing };
    // Keep a distinct unsaved target when a refresh or import changes the saved mapping.
    if (!sourceId && old.source === source && old.mapping !== existing && target === (old.mapping ?? ""))
      onDraftChange({ ...draft, target: existing ?? "" });
  }, [source, sourceId, existing, target, draft, onDraftChange]);

  const save = (nextMappings: Record<string, string>, nextParents: string[], nextProjects = projectMappings) => {
    command("save-adjustments", JSON.stringify({
      format: "todoist-assistant-project-adjustments-v1",
      mappings: nextMappings,
      archivedParents: nextParents,
      projectMappings: nextProjects,
    }));
  };
  const assign = () => {
    if (!editable || invalidSourceId || invalidTargetId || activeChildOnly || !source || !target || (namedProjects.length > 1 && !sourceId) || (targetProjects.length > 1 && (!targetId || !sourceId)) || wouldCreateCycle) return;
    if (sourceId && targetProjectId) {
      save(mappings, archivedParents, { ...projectMappings, [sourceId]: { targetId: targetProjectId, targetName: target } });
      return;
    }
    if (sourceId || source === target) return;
    save({ ...mappings, [source]: target }, archivedParents.filter((name) => name !== source));
  };
  const makeOwnGroup = () => {
    if (!editable || invalidSourceId || activeOnly || !source || (namedProjects.length > 1 && !sourceId)) return;
    if (sourceId) {
      save(mappings, archivedParents, { ...projectMappings, [sourceId]: { targetId: sourceId, targetName: source } });
      return;
    }
    const next = { ...mappings };
    delete next[source];
    save(next, [...new Set([...archivedParents, source])]);
  };
  const useAutomatic = () => {
    if (!editable || invalidSourceId || !source || (namedProjects.length > 1 && !sourceId)) return;
    if (sourceId) {
      const next = { ...projectMappings };
      delete next[sourceId];
      save(mappings, archivedParents, next);
      return;
    }
    const next = { ...mappings };
    delete next[source];
    save(next, archivedParents.filter((name) => name !== source));
  };
  const projectLabel = (project: typeof hierarchy[number]) => {
    const names = [project.name];
    const seen = new Set([project.id]);
    let parentId = project.parentId;
    while (parentId && !seen.has(parentId)) {
      seen.add(parentId);
      const parent = hierarchy.find((item) => item.id === parentId);
      if (!parent) break;
      names.unshift(parent.name);
      parentId = parent.parentId;
    }
    const former = project.previousNames?.length ? ` · formerly ${project.previousNames.join(", ")}` : "";
    return `${names.join(" / ")} · ${project.archived ? "archived" : "active"} · ID ${project.id}${former}`;
  };
  const chooseSource = (name: string, nameRule = false, resetSearch = false) => {
    const matches = hierarchy.filter((project) => project.name === name);
    const id = !nameRule && matches.length === 1 ? matches[0].id : "";
    const rule = savedProjectRule(id);
    change({ source: name, sourceId: id, targetId: rule?.targetId ?? "", target: rule ? ruleName(rule) : savedMapping(name) ?? "", ...(resetSearch ? { search: "" } : {}) });
  };

  return (
    <section className="card" aria-label="Project grouping">
      <header className="cardHeader"><h2>Project grouping</h2></header>
      <p className="muted tiny">Todoist does not always retain the parent of an archived project. When a parent is missing or incorrect, choose a project to group it under.</p>
      {!enabled ? <p className="muted tiny">Connect your account to edit or import groupings.</p> : (
        <>
          <label className="control">Find an archived project
            <input className="textInput" type="search" placeholder="Search project names" value={search} onChange={(event) => change({ search: event.target.value })} disabled={!editable} />
          </label>
          <label className="control">Archived project
            <select className="select" value={source} onChange={(event) => chooseSource(event.target.value)} disabled={!editable || !sources.length}>
              <option value="">Select a project</option>
              {sources.filter((name) => name === source || matchesSearch(name, search)).map((name) => {
                const matches = nameCounts.get(name) ?? 0;
                const former = formerMatch(name, search);
                return <option key={name} value={name}>{name}{matches > 1 ? ` (${matches} projects)` : matches === 0 ? " (not in synced projects)" : ""}{former ? ` · formerly ${former}` : ""}</option>;
              })}
            </select>
          </label>
          {search.trim() && !filteredSources.length && <p className="muted tiny" role="status">No archived projects match this search.</p>}
          {!sources.length && <p className="muted tiny">No archived projects found. Sync your account or import a desktop file.</p>}
          <details>
            <summary>Project not listed?</summary>
            <p className="muted tiny">Enter its exact name. Rules apply to every project with that name.</p>
            <label className="control">Project name<input className="textInput" value={customSource} onChange={(event) => change({ customSource: event.target.value })} disabled={!editable} /></label>
            <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || !customSource.trim()} onClick={() => chooseSource(customSource.trim(), false, true)}>Use project name</button>
          </details>
          {source && (
            <>
              {namedProjects.length > 1 && <p className="pill pill-warn">{namedProjects.length} projects share this name. Choose the specific project before saving.</p>}
              {namedProjects.length > 0 && <label className="control">Specific project
                <select aria-label="Specific project" className="select" value={sourceId} onChange={(event) => { const id = event.target.value; const rule = savedProjectRule(id); change({ sourceId: id, targetId: rule?.targetId ?? "", target: rule ? ruleName(rule) : savedMapping(source) ?? "" }); }} disabled={!editable}>
                  <option value="">{namedProjects.length > 1 ? "Select a specific project" : "Use existing name rule"}</option>
                  {namedProjects.map((project) => <option key={project.id} value={project.id}>{projectLabel(project)}</option>)}
                </select>
              </label>}
              {invalidSourceId && <p className="pill pill-warn">The selected project ID is no longer in the synced projects. Select a project again before changing its grouping.</p>}
              {!sourceKnown && <p className="muted tiny">This saved project name is not in the current project list. Its rule is preserved.</p>}
              {activeChildOnly && <p className="pill pill-warn">This active subproject follows its Todoist parent. It can be assigned here after archiving.</p>}
              {activeOnly && !activeChildOnly && <p className="muted tiny">This active root can be assigned to another group; only archived projects can be marked as their own group.</p>}
              {mixedStatus && <p className="pill pill-warn">Active subprojects follow their Todoist parents. A rule for this name may apply differently to active and archived projects.</p>}
              <p className="muted tiny">Current grouping: {currentGrouping}</p>
              {sourceId && sourceRule && (existing || ownGroup) && <p className="muted tiny">Removing the individual rule restores the saved name rule for {source}.</p>}
              {sourceRule && !hierarchy.some((project) => project.id === sourceRule.targetId) && <p className="pill pill-warn">The saved parent is missing from synced projects. It stays separate as {sourceRule.targetName} · {sourceRule.targetId}; it will not be matched to a different project by name.</p>}
              {ownGroup && activeOnly && <p className="muted tiny">“Own group” is saved for this name and takes effect after the project is archived.</p>}
              {ownGroup && existing && !activeOnly && <p className="muted tiny">A saved assignment to {existing} is also present. “Own group” takes priority for archived projects until you assign it again.</p>}
              <label className="control">Find a parent project
                <input className="textInput" type="search" placeholder="Search active and archived projects" value={targetSearch} onChange={(event) => change({ targetSearch: event.target.value })} disabled={!editable} />
              </label>
              <label className="control">Group under
                <select className="select" value={target} onChange={(event) => change({ targetId: "", target: event.target.value })} disabled={!editable}>
                  <option value="">Select a group</option>
                  {availableTargets.filter((name) => name === target || matchesSearch(name, targetSearch)).map((name) => {
                    const count = nameCounts.get(name) ?? 0;
                    const suffix = count > 1 ? ` (${count} projects)` : archivedNames.has(name) ? " (archived)" : "";
                    const former = formerMatch(name, targetSearch);
                    return <option key={name} value={name}>{name}{suffix}{former ? ` · formerly ${former}` : ""}</option>;
                  })}
                </select>
              </label>
              {targetProjects.length > 1 && <label className="control">Specific parent project
                <select aria-label="Specific parent project" className="select" value={targetId} onChange={(event) => change({ targetId: event.target.value })} disabled={!editable}>
                  <option value="">Select a specific parent</option>
                  {targetProjects.map((project) => <option key={project.id} value={project.id}>{projectLabel(project)}</option>)}
                </select>
              </label>}
              {targetSearch.trim() && !filteredTargets.length && <p className="muted tiny" role="status">No parent projects match this search.</p>}
              <p className="muted tiny">Active and archived projects can be selected. A subproject is grouped under its top-level parent.</p>
              {(nameCounts.get(target) ?? 0) > 1 && <p className="pill pill-warn">Multiple projects share this parent name. Choose a specific project before saving.</p>}
              {!sourceId && targetProjects.length > 1 && <p className="muted tiny">Choose a specific source project to assign a parent by ID.</p>}
              {sourceId && target && !targetProjects.length && <p className="muted tiny">This parent is not in the synced projects. Use a name rule or select a known parent.</p>}
              {invalidTargetId && !sourceRule && <p className="pill pill-warn">The selected parent ID is no longer in the synced projects. Select a parent again.</p>}
              {wouldCreateCycle && <p className="pill pill-warn" role="alert">This assignment would create a grouping loop. Choose a different parent.</p>}
              <details>
                <summary>Group not listed?</summary>
                <label className="control">Group name<input className="textInput" value={customTarget} onChange={(event) => change({ customTarget: event.target.value })} disabled={!editable} /></label>
                <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || !customTarget.trim() || customTarget.trim() === source} onClick={() => change({ targetId: "", target: customTarget.trim() })}>Use group name</button>
              </details>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <button type="button" className="button buttonSmall" disabled={!editable || invalidSourceId || invalidTargetId || activeChildOnly || !target || (namedProjects.length > 1 && !sourceId) || (targetProjects.length > 1 && (!targetId || !sourceId)) || (sourceId && !targetProjectId) || (!sourceId && target === source) || wouldCreateCycle || (sourceId ? sourceRule?.targetId === targetProjectId : target === existing && !ownGroup)} onClick={assign}>Assign to group</button>
                <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || invalidSourceId || activeOnly || (namedProjects.length > 1 && !sourceId) || (sourceId ? sourceRule?.targetId === sourceId : ownGroup)} onClick={makeOwnGroup}>Make its own group</button>
                <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || invalidSourceId || (namedProjects.length > 1 && !sourceId) || (sourceId ? !sourceRule : !existing && !ownGroup)} onClick={useAutomatic}>{sourceId ? "Remove individual rule" : "Use automatic grouping"}</button>
              </div>
            </>
          )}
        </>
      )}
      {(Object.keys(mappings).length > 0 || archivedParents.length > 0 || Object.keys(projectMappings).length > 0) && (
        <details>
          <summary>Saved groupings · {Object.keys(projectMappings).length} individual, {Object.keys(mappings).length} name rules, {archivedParents.length} own groups</summary>
          {Object.entries(projectMappings).sort(([a], [b]) => a.localeCompare(b)).map(([id, rule]) => {
            const project = hierarchy.find((item) => item.id === id);
            return <div key={`individual:${id}`} style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8 }}>
              <span>{project ? projectLabel(project) : `Missing project · ID ${id}`} → {rule.targetId === id ? "own group" : `${ruleName(rule)} · ID ${rule.targetId}`}</span>
              <button type="button" className="button buttonSmall buttonGhost" disabled={!editable} onClick={() => { const next = { ...projectMappings }; delete next[id]; save(mappings, archivedParents, next); }}>Remove individual rule for {project?.name ?? id}</button>
            </div>;
          })}
          {Object.entries(mappings).sort(([a], [b]) => a.localeCompare(b)).map(([name, group]) => (
            <div key={`mapping:${name}`} style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8 }}>
              <span>{name} → {group}{archivedParents.includes(name) ? " (own group takes priority when archived)" : ""}</span>
              <button type="button" className="button buttonSmall buttonGhost" disabled={!editable} onClick={() => chooseSource(name, true, true)}>Edit {name}</button>
            </div>
          ))}
          {archivedParents.map((name) => (
            <div key={`parent:${name}`} style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8 }}>
              <span>{name} · own group</span>
              <button type="button" className="button buttonSmall buttonGhost" disabled={!editable} onClick={() => save({ ...mappings }, archivedParents.filter((item) => item !== name))}>Remove own group for {name}</button>
            </div>
          ))}
        </details>
      )}
      <details>
        <summary>Import groupings from your computer</summary>
        <p className="muted tiny">On your computer, open Project Adjustments and choose “Export saved mappings for Android”. Transfer the JSON file to this phone, then select it below. Matching name rules are replaced; individual project rules take priority and are kept unless the file contains the same project IDs.</p>
        <button type="button" className="button buttonSmall buttonGhost" disabled={!editable} onClick={() => command("import-adjustments")}>Choose desktop export</button>
      </details>
      {(message.startsWith("Project adjustments ") || message.startsWith("Could not import adjustments") || message.startsWith("Could not save project adjustments")) && <p className="muted tiny" aria-live="polite">{message}</p>}
    </section>
  );
}
