import hashlib

def dhash(path: str) -> str:
    """Return a deterministic 12-char hex hash."""
    return hashlib.sha256(path.encode()).hexdigest()[:12]

def get_id(filepath: str, path: str) -> str:
    """Get the ID from the filepath and path within the file."""

    return dhash(f"{filepath}:{path}")
