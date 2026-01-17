# IACS minimal Flask app

This repo now serves a small Flask app that reads `examples/minimal.yaml` and displays the resources plus any `implements` relationships.

## Setup

1. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install flask pyyaml
   ```

## Run

```bash
python app.py
```
Then open http://localhost:5000/ to see the visualization.

## How it works

- `app.py` loads `examples/minimal.yaml`, extracts top-level resources, and builds edges from any `implements` fields.
- The data is rendered by `templates/index.html` with minimal styling in `static/style.css`.
