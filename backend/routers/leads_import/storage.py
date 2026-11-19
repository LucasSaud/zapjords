"""Private, size-bounded temporary storage for contact files."""
import os
from pathlib import Path
from fastapi import HTTPException

IMPORT_FILES_DIR = str(Path(__file__).resolve().parents[2] / 'var' / 'imports')
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


async def read_upload(file):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, 'O arquivo excede o limite de 5 MB.')
    return content


def clean_import_file(history):
    if history and history.file_path:
        path = Path(history.file_path).resolve()
        if path.parent == Path(IMPORT_FILES_DIR).resolve() and path.exists():
            path.unlink()
        history.file_path = None
