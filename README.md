# IACS minimal Flask app

This repo now serves a small Flask app that reads `examples/minimal.yaml` and displays the resources plus any `solution of` relationships.

## Setup

Using uv (recommended):
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

## Run

```bash
python app.py
```
Then open http://localhost:8000/ to see the visualization.

## How it works

- `app.py` loads `examples/minimal.yaml`, extracts top-level resources, and builds edges from any `solution of` fields.
- The data is rendered by `templates/index.html` with minimal styling in `static/style.css`.
