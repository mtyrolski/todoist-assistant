# Code and dependency audit

Audit performed on 2026-11-01 while fixing completion accounting, chart forecasts, urgency settings and Android packaging.

## Removed

| Item | Evidence and result |
| --- | --- |
| `todoist/dashboard/utils.py` | Legacy Streamlit-format metric/badge strings. No runtime imports; the FastAPI dashboard uses `web/dashboard_payload.py`. Removed this module and tests of the obsolete implementation. |
| `frontend/app/components/Markdown.tsx` | No imports or references outside its definition. |
| `_task_matches_label`, `_task_date_is_due` | No call sites; urgency uses multi-label and date-window helpers. |
| `_config_path_label` | No call sites; API settings provide their own path labels. |
| Old executive review, status update and task ingestion CSS | No matching class references in active TSX/TS. Removed 119 rules and the unused executive-review animation (over 800 lines). Shared selectors/media queries remain. |
| Makefile AI/backend variables | No consumers. |
| `todoist_assistant.*` packaging patterns | No such source package exists; the actual import package is `todoist`. |
| Direct NumPy requirement in the core package | No NumPy imports in core/API/data modules. Pandas still brings NumPy transitively. The desktop package keeps its direct dependency because lifespan plots import it. |

## Frontend dependencies

The app previously installed Plotly's source package and its build/rendering dependency tree, although React only loaded its prebuilt browser distribution. It now uses the official full minified distribution at **Plotly.js 4.0.0**, matching the renderer bundled with the locked Python Plotly 7.0.0, through the supported React factory. An npm alias satisfies the React peer requirement without installing a second source package. There is one shared lazy Plot component.

This reduces lockfile package entries from **409 to 67**, including platform optional packages. The installed count varies by platform. Heatmaps, sunbursts and the rest of the full Plotly trace set remain available. The old JavaScript 2.x renderer did not understand the binary numeric arrays emitted by the current Python serializer; it could mount empty traces without an exception. `scripts/check_versions.py` now checks renderer major compatibility in CI. The renderer update fixes that compatibility issue as well as removing source/build dependencies. The factory integration follows [Plotly's custom bundle instructions](https://github.com/plotly/react-plotly.js#customizing-the-plotlyjs-bundle).

Next.js was updated within the 15.5 line, from 15.5.14 to 15.5.28. PostCSS 8.5.32 and Sharp 0.35.5 overrides address the remaining transitive advisories. The resulting `npm audit` reports **0 vulnerabilities** at audit time. The TypeScript lint command remains active; Next's separate ESLint build hook is disabled because this repository does not configure ESLint.

## Kept after checking use

- Every remaining direct desktop Python dependency has runtime imports. No unused production dependency was found there.
- Optional notebook dependencies remain optional; removing them would change an explicitly offered install extra.
- `core/`, typed API endpoints, cache locks/checkpoints, telemetry, project adjustments, domain models, plotting facade and split FastAPI modules all have live consumers.
- `_sync_api_globals` remains part of the active route/component wiring and test boundary. Replacing it warrants a separate behavior-preserving refactor, not deletion during an unused-code sweep.
- Windows/macOS build scripts remain supported entrypoints.

## Remaining work worth considering separately

- Separate API dependencies explicitly rather than passing module globals, then remove associated Ruff exceptions.
- Replace growing mobile JSON snapshots with an indexed on-device store if long histories make loading/syncing slow. Desktop joblib and Android JSON caches are intentionally separate formats.
- Add mobile device/emulator interaction tests and release signing before distributing production Android builds.

Do not remove further modules solely because they lack an obvious direct import: compatibility exports, module entrypoints, packaging scripts and dynamically injected helpers are active in this repository.
