# Copilot Instructions for iacs

Purpose: Help AI agents work effectively in this repo.

## Overview
- Single-page, client-only web app: [index.html](../index.html) loads [yaml-parser.js](../yaml-parser.js) then [app.js](../app.js) with styles from [styles.css](../styles.css).
- No backend, no build system, no external deps.
- Core flow: YAML -> parse -> validate -> layout -> draw (Canvas) -> export PNG.

## How It Works
- YAML parsing: `jsyaml.load()` in [yaml-parser.js](../yaml-parser.js) implements a minimal subset.
  - Supports: key/value pairs, arrays (including arrays of single-key objects), numbers/booleans/null, quoted strings.
  - Limitations: no anchors/aliases, no multi-line strings, limited nested structures.
- App logic: `InfrastructureDesigner` in [app.js](../app.js)
  - UI wiring, validation (`validateInfrastructure()`), grid layout (`layoutComponents()`), render (`drawInfrastructure()`), PNG export (`exportCanvas()`).
  - Color mapping via `TYPE_COLORS` (service, database, storage, network, compute, gateway, cache, queue, default).
  - Canvas title and elements drawn with Canvas API; `roundRect` polyfill included for compatibility.

## Run & Debug
- Quick start: open [index.html](../index.html) in a browser.
- If your browser restricts `file://` access, serve locally:
```bash
python3 -m http.server 8000
open http://localhost:8000/index.html
```
- Errors surface two ways: thrown exceptions and the inline banner `#errorMessage` (see `showError()` in [app.js](../app.js)). Use DevTools console for parse/paint issues.

## Data Model (YAML)
- Root: `name` (string), `description` (string), `components` (array, required).
- Component: `name` (required), `type` (optional), `properties` (array of single-key objects), `connections` (array of `{ target: Name }` or plain names).
- Example snippet:
```yaml
components:
  - name: Web Server
    type: service
    properties:
      - runtime: Node.js
    connections:
      - target: Database
```

## Conventions & Patterns
- Script order matters in [index.html](../index.html): load [yaml-parser.js](../yaml-parser.js) before [app.js](../app.js) to expose global `jsyaml`.
- Layout strategy: simple grid in `layoutComponents()`; each component needs `x,y,width,height`.
- Drawing: connections first (dashed lines + arrowheads), then component cards (rounded rect, name wrap, type label).
- Type colors: add/update in `TYPE_COLORS`; unknown types fall back to `default`.
- Text wrapping respects `comp.width - 10`; very long names auto-wrap across multiple lines.

## Extending Safely
- New component types: add a color in `TYPE_COLORS`; no other change required.
- Show properties on cards: extend `drawComponent()` to render `comp.properties` beneath the name (small font, truncated list).
- Parser enhancements: update `parseValue()` and array/object handling; keep backward-compatible with current YAML examples in [README.md](../README.md).
- Alternative layouts: implement a new layout method that still produces `x,y,width,height` per component; call it from `renderInfrastructure()`.

## Gotchas
- Validation requires `components` to be a non-empty array and every component to have `name`.
- Keep Canvas scaling: size via `getBoundingClientRect()` and scale by `devicePixelRatio` in `initializeCanvas()`.
- Export uses `canvas.toDataURL()`; very large diagrams can be memory-heavy.
- Do not remove the `roundRect` polyfill unless targeting only modern browsers.
