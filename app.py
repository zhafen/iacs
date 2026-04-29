from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from iacs.architect import Architect
from iacs.views.requirement_tree import build_requirement_tree

BASE_DIR = Path(__file__).parent
BUILTINS_DIR = BASE_DIR / "builtins"
STATIC_DIR = BASE_DIR / "static"
DEFAULT_ANCESTOR = "be_a_powerful_tool_for_solutions_architecture"


@asynccontextmanager
async def lifespan(app):
    app.state.architect = Architect.from_manifest(str(BUILTINS_DIR))
    yield


app = FastAPI(lifespan=lifespan)

@app.get("/api/view/{component_type}")
def view_component(component_type: str):
    df = app.state.architect.view(component_type).execute()
    return df.to_dict()

@app.get("/api/tree")
def get_tree(ancestor_key: str = Query(default=DEFAULT_ANCESTOR)):
    try:
        return build_requirement_tree(app.state.architect, ancestor_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/files")
def list_files():
    return [str(p.relative_to(BUILTINS_DIR)) for p in BUILTINS_DIR.rglob("*.yaml")]


@app.get("/api/files/{filepath:path}")
def get_file(filepath: str):
    target = (BUILTINS_DIR / filepath).resolve()
    if not str(target).startswith(str(BUILTINS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return PlainTextResponse(target.read_text())


@app.put("/api/files/{filepath:path}")
async def put_file(filepath: str, request):
    import yaml
    target = (BUILTINS_DIR / filepath).resolve()
    if not str(target).startswith(str(BUILTINS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    body = await request.body()
    text = body.decode()
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    target.write_text(text)
    app.state.architect = Architect.from_manifest(str(BUILTINS_DIR))
    return {"status": "ok"}


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
