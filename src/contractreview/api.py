from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, UploadFile

from .review import ContractReviewer, to_markdown

app = FastAPI(title="Contract Review", version="0.1.0")
reviewer = ContractReviewer()


@app.post("/review")
async def review(file: UploadFile = File(...)):
    suffix = Path(file.filename or "c.txt").suffix or ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
    try:
        r = reviewer.review(tmp.name)
        return {"review": asdict(r), "markdown": to_markdown(r)}
    finally:
        Path(tmp.name).unlink(missing_ok=True)
