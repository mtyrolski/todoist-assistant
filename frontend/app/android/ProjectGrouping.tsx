"use client";

import { useEffect, useMemo, useRef } from "react";
import { command, type MobileModel } from "../lib/mobile";

/** Saved rules are keyed by project name, like the desktop export. */
export function ProjectGrouping({ model, enabled, busy, message, draft, onDraftChange }: {
  model: MobileModel | null;
  enabled: boolean;
  busy: boolean;
  message: string;
  draft: { search: string; source: string; target: string; customSource: string; customTarget: string };
  onDraftChange: (draft: { search: string; source: string; target: string; customSource: string; customTarget: string }) => void;
}) {
  const { search, source, target, customSource, customTarget } = draft;
  const change = (value: Partial<typeof draft>) => onDraftChange({ ...draft, ...value });
  const adjustments = model?.adjustments;
  const mappings = adjustments?.mappings ?? {};
  const archivedParents = adjustments?.archivedParents ?? [];
  const hierarchy = model?.plotData?.hierarchy ?? [];
  const savedMapping = (name: string) => Object.prototype.hasOwnProperty.call(mappings, name) ? mappings[name] : undefined;
  const sources = useMemo(() => [...new Set([
    ...hierarchy.filter((project) => project.archived).map((project) => project.name),
    ...Object.keys(mappings),
    ...archivedParents,
    source,
  ].filter(Boolean))].sort((a, b) => a.localeCompare(b)), [hierarchy, mappings, archivedParents, source]);
  const targets = useMemo(() => [...new Set([
    ...hierarchy.map((project) => project.rootName).filter((name) => name && name !== "Unknown project"),
    ...archivedParents,
    ...Object.values(mappings),
    target,
  ].filter(Boolean))].sort((a, b) => a.localeCompare(b)), [hierarchy, mappings, archivedParents, target]);
  const nameCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const project of hierarchy) counts.set(project.name, (counts.get(project.name) ?? 0) + 1);
    return counts;
  }, [hierarchy]);
  const matchingProjects = hierarchy.filter((project) => project.name === source);
  const roots = [...new Set(matchingProjects.map((project) => project.rootName).filter(Boolean))];
  const existing = savedMapping(source);
  const ownGroup = archivedParents.includes(source);
  const sourceKnown = matchingProjects.length > 0;
  const activeOnly = sourceKnown && matchingProjects.every((project) => !project.archived);
  const activeChildOnly = activeOnly && matchingProjects.some((project) => Boolean(project.parentId));
  const mixedStatus = matchingProjects.some((project) => project.archived) && matchingProjects.some((project) => !project.archived);
  const currentGrouping = roots.length > 1 ? "Multiple groups" : activeOnly && roots.length === 1 ? roots[0] : ownGroup ? "Own group" : existing ? existing : roots.length === 1 ? `${roots[0]} (automatic)` : "Automatic";
  const editable = enabled && !busy;
  const previous = useRef({ source, mapping: existing });

  useEffect(() => {
    const old = previous.current;
    previous.current = { source, mapping: existing };
    // Keep a distinct unsaved target when a refresh or import changes the saved mapping.
    if (old.source === source && old.mapping !== existing && target === (old.mapping ?? ""))
      onDraftChange({ ...draft, target: existing ?? "" });
  }, [source, existing, target, draft, onDraftChange]);

  const save = (nextMappings: Record<string, string>, nextParents: string[]) => {
    command("save-adjustments", JSON.stringify({
      format: "todoist-assistant-project-adjustments-v1",
      mappings: nextMappings,
      archivedParents: nextParents,
    }));
  };
  const assign = () => {
    if (!editable || activeChildOnly || !source || !target || source === target) return;
    save({ ...mappings, [source]: target }, archivedParents.filter((name) => name !== source));
  };
  const makeOwnGroup = () => {
    if (!editable || activeOnly || !source) return;
    const next = { ...mappings };
    delete next[source];
    save(next, [...new Set([...archivedParents, source])]);
  };
  const useAutomatic = () => {
    if (!editable || !source) return;
    const next = { ...mappings };
    delete next[source];
    save(next, archivedParents.filter((name) => name !== source));
  };

  return (
    <section className="card" aria-label="Project grouping">
      <header className="cardHeader"><h2>Project grouping</h2></header>
      <p className="muted tiny">Archived projects follow their known Todoist parent. Change a grouping here when the parent is missing or needs correcting.</p>
      {!enabled ? <p className="muted tiny">Connect your account to edit or import groupings.</p> : (
        <>
          <label className="control">Find an archived project
            <input className="textInput" type="search" placeholder="Search project names" value={search} onChange={(event) => change({ search: event.target.value })} disabled={!editable} />
          </label>
          <label className="control">Archived project
            <select className="select" value={source} onChange={(event) => change({ source: event.target.value, target: savedMapping(event.target.value) ?? "" })} disabled={!editable || !sources.length}>
              <option value="">Select a project</option>
              {sources.filter((name) => name === source || name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())).map((name) => {
                const matches = nameCounts.get(name) ?? 0;
                return <option key={name} value={name}>{name}{matches > 1 ? ` (${matches} projects)` : matches === 0 ? " (not in synced projects)" : ""}</option>;
              })}
            </select>
          </label>
          {!sources.length && <p className="muted tiny">No archived projects found. Sync your account or import a desktop file.</p>}
          <details>
            <summary>Project not listed?</summary>
            <p className="muted tiny">Enter its exact name. Rules apply to every project with that name.</p>
            <label className="control">Project name<input className="textInput" value={customSource} onChange={(event) => change({ customSource: event.target.value })} disabled={!editable} /></label>
            <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || !customSource.trim()} onClick={() => change({ source: customSource.trim(), search: "", target: savedMapping(customSource.trim()) ?? "" })}>Use project name</button>
          </details>
          {source && (
            <>
              {matchingProjects.length > 1 && <p className="pill pill-warn">{matchingProjects.length} projects share this name. Rules use names, so this change may affect all of them.</p>}
              {!sourceKnown && <p className="muted tiny">This saved project name is not in the current project list. Its rule is preserved.</p>}
              {activeChildOnly && <p className="pill pill-warn">This active subproject follows its Todoist parent. It can be assigned here after archiving.</p>}
              {activeOnly && !activeChildOnly && <p className="muted tiny">This active root can be assigned to another group; only archived projects can be marked as their own group.</p>}
              {mixedStatus && <p className="pill pill-warn">Active subprojects follow their Todoist parents. A rule for this name may apply differently to active and archived projects.</p>}
              <p className="muted tiny">Current grouping: {currentGrouping}</p>
              {ownGroup && activeOnly && <p className="muted tiny">“Own group” is saved for this name and takes effect after the project is archived.</p>}
              {ownGroup && existing && !activeOnly && <p className="muted tiny">A saved assignment to {existing} is also present. “Own group” takes priority for archived projects until you assign it again.</p>}
              <label className="control">Group under
                <select className="select" value={target} onChange={(event) => change({ target: event.target.value })} disabled={!editable}>
                  <option value="">Select a group</option>
                  {targets.filter((name) => name !== source || name === existing).map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
              <details>
                <summary>Group not listed?</summary>
                <label className="control">Group name<input className="textInput" value={customTarget} onChange={(event) => change({ customTarget: event.target.value })} disabled={!editable} /></label>
                <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || !customTarget.trim() || customTarget.trim() === source} onClick={() => change({ target: customTarget.trim() })}>Use group name</button>
              </details>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <button type="button" className="button buttonSmall" disabled={!editable || activeChildOnly || !target || target === source || (target === existing && !ownGroup)} onClick={assign}>Assign to group</button>
                <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || activeOnly || ownGroup} onClick={makeOwnGroup}>Make its own group</button>
                <button type="button" className="button buttonSmall buttonGhost" disabled={!editable || (!existing && !ownGroup)} onClick={useAutomatic}>Use automatic grouping</button>
              </div>
            </>
          )}
        </>
      )}
      {(Object.keys(mappings).length > 0 || archivedParents.length > 0) && (
        <details>
          <summary>Saved groupings · {Object.keys(mappings).length} assignments, {archivedParents.length} own groups</summary>
          {Object.entries(mappings).sort(([a], [b]) => a.localeCompare(b)).map(([name, group]) => (
            <div key={`mapping:${name}`} style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8 }}>
              <span>{name} → {group}{archivedParents.includes(name) ? " (own group takes priority when archived)" : ""}</span>
              <button type="button" className="button buttonSmall buttonGhost" disabled={!editable} onClick={() => change({ source: name, search: "", target: savedMapping(name) ?? "" })}>Edit {name}</button>
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
        <p className="muted tiny">On your computer, open Project Adjustments and choose “Export saved mappings for Android”. Transfer the JSON file to this phone, then select it below. Import keeps phone-only rules; file rules win when both places define the same project.</p>
        <button type="button" className="button buttonSmall buttonGhost" disabled={!editable} onClick={() => command("import-adjustments")}>Choose desktop export</button>
      </details>
      {(message.startsWith("Project adjustments ") || message.startsWith("Could not import adjustments") || message.startsWith("Could not save project adjustments")) && <p className="muted tiny" aria-live="polite">{message}</p>}
    </section>
  );
}
