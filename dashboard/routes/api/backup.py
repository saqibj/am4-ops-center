"""Backup download and restore upload (multipart)."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from dashboard.auth import check_auth_token
from dashboard.server import templates
from dashboard.services.backup import (
    BackupError,
    RestoreError,
    create_backup,
    restore_backup,
)

router = APIRouter()

_MAX_RESTORE_BYTES = 100 * 1024 * 1024


def _cleanup_backup_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _is_htmx(request: Request) -> bool:
    return (request.headers.get("hx-request") or "").strip().lower() == "true"


@router.get("/backup")
def get_api_backup(background_tasks: BackgroundTasks):
    """Stream a backup ``.zip`` (database snapshot + manifest + optional logo)."""
    try:
        zip_path = create_backup()
    except BackupError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    background_tasks.add_task(_cleanup_backup_dir, str(zip_path.parent.resolve()))
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )


@router.post("/restore")
async def post_api_restore(request: Request, backup_file: UploadFile = File(...)):
    """Accept a ``.zip`` backup and replace the current database (and logo when present)."""
    check_auth_token(request)

    name = (backup_file.filename or "").lower()
    if not name.endswith(".zip"):
        msg = "Upload must be a .zip backup file."
        if _is_htmx(request):
            return templates.TemplateResponse(
                request,
                "partials/restore_result.html",
                {"ok": False, "message": msg, "warnings": []},
                status_code=200,
            )
        raise HTTPException(status_code=400, detail=msg)

    body = await backup_file.read()
    if len(body) > _MAX_RESTORE_BYTES:
        msg = "Backup file is too large (max 100MB)."
        if _is_htmx(request):
            return templates.TemplateResponse(
                request,
                "partials/restore_result.html",
                {"ok": False, "message": msg, "warnings": []},
                status_code=200,
            )
        raise HTTPException(status_code=400, detail=msg)

    fd, tmp_name = tempfile.mkstemp(prefix="am4-restore-upload-", suffix=".zip")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_bytes(body)
        try:
            result = restore_backup(tmp)
        except RestoreError as e:
            msg = str(e)
            if _is_htmx(request):
                return templates.TemplateResponse(
                    request,
                    "partials/restore_result.html",
                    {"ok": False, "message": msg, "warnings": []},
                    status_code=200,
                )
            if "newer version" in msg.lower():
                raise HTTPException(status_code=409, detail=msg) from e
            raise HTTPException(status_code=400, detail=msg) from e

        warnings = list(result.pop("warnings", []))
        manifest = result
        payload = {
            "status": "success",
            "manifest": manifest,
            "warnings": warnings,
            "message": "Restore complete. Please restart the application for changes to take effect.",
        }
        if _is_htmx(request):
            return templates.TemplateResponse(
                request,
                "partials/restore_result.html",
                {
                    "ok": True,
                    "message": payload["message"],
                    "warnings": warnings,
                    "manifest": manifest,
                },
                status_code=200,
            )
        return JSONResponse(payload)
    finally:
        tmp.unlink(missing_ok=True)
