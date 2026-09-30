from __future__ import annotations

import base64
import io
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .generator import LAYOUTS, PAGE_SIZES, DecodedUpload, build_pdf, decode_image, format_code


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MAX_FILES = 200
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 120 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "application/octet-stream"}

app = FastAPI(title="特种设备安全码生成器", version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/guide", include_in_schema=False)
@app.get("/guide/", include_in_schema=False)
def guide() -> FileResponse:
    return FileResponse(STATIC_DIR / "guide.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def read_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一张二维码图片")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=413, detail=f"单次最多上传{MAX_FILES}张图片")
    total = 0
    uploads: list[tuple[str, bytes]] = []
    for file in files:
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=415, detail=f"{file.filename} 不是支持的图片格式")
        data = await file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"{file.filename} 超过10MB")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="本批图片总大小超过120MB")
        uploads.append((file.filename or "未命名图片", data))
    return uploads


def decode_uploads(uploads: list[tuple[str, bytes]]) -> tuple[list[DecodedUpload], list[dict[str, str | None]]]:
    decoded: list[DecodedUpload] = []
    rows: list[dict[str, str | None]] = []
    for filename, data in uploads:
        try:
            item = decode_image(data, filename)
            decoded.append(item)
            rows.append({"filename": filename, "code": item.code, "formatted_code": format_code(item.code), "status": "ok", "error": None})
        except Exception as exc:
            rows.append({"filename": filename, "code": None, "formatted_code": None, "status": "error", "error": str(exc)})

    counts = Counter(item.code for item in decoded)
    duplicate_codes = {code for code, count in counts.items() if count > 1}
    if duplicate_codes:
        for row in rows:
            if row["code"] in duplicate_codes:
                row["status"] = "duplicate"
                row["error"] = "安全码重复"
    return decoded, rows


def preview_data_url(item: DecodedUpload) -> str:
    preview = item.image.copy()
    preview.thumbnail((420, 420))
    output = io.BytesIO()
    preview.save(output, format="PNG", optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@app.post("/api/inspect")
async def inspect(files: list[UploadFile] = File(...)) -> dict[str, object]:
    uploads = await read_uploads(files)
    decoded, rows = decode_uploads(uploads)
    valid_codes = [row["code"] for row in rows if row["status"] == "ok"]
    valid_code_set = set(valid_codes)
    first_valid = next((item for item in decoded if item.code in valid_code_set), None)
    return {
        "items": rows,
        "preview_image": preview_data_url(first_valid) if first_valid else None,
        "summary": {
            "total": len(rows),
            "valid": len(valid_codes),
            "invalid": sum(row["status"] == "error" for row in rows),
            "duplicates": sum(row["status"] == "duplicate" for row in rows),
            "unique_codes": len(set(code for code in valid_codes if code)),
        },
        "supported_sizes": PAGE_SIZES,
        "supported_layouts": LAYOUTS,
    }


@app.post("/api/generate")
async def generate(
    files: list[UploadFile] = File(...),
    size_key: str = Form("standard"),
    layout_key: str = Form("left"),
    rescue_phone: str = Form(""),
    sort_codes: bool = Form(True),
) -> Response:
    if size_key not in PAGE_SIZES:
        raise HTTPException(status_code=422, detail="请选择有效的标识牌尺寸")
    if layout_key not in LAYOUTS:
        raise HTTPException(status_code=422, detail="请选择有效的排版模板")
    phone = re.sub(r"\s+", "", rescue_phone)
    if phone and not re.fullmatch(r"[0-9+\-]{5,20}", phone):
        raise HTTPException(status_code=422, detail="救援电话格式不正确")

    uploads = await read_uploads(files)
    decoded, rows = decode_uploads(uploads)
    problems = [row for row in rows if row["status"] != "ok"]
    if problems:
        detail = "；".join(f"{row['filename']}：{row['error']}" for row in problems[:8])
        if len(problems) > 8:
            detail += f"；另有{len(problems) - 8}项错误"
        raise HTTPException(status_code=422, detail=detail)
    if sort_codes:
        decoded.sort(key=lambda item: item.code)

    pdf_bytes = build_pdf(decoded, size_key=size_key, rescue_phone=phone, layout_key=layout_key)
    config = PAGE_SIZES[size_key]
    layout_label = LAYOUTS[layout_key]["label"]
    filename = f"特种设备安全码_{layout_label}_{int(config['width'])}x{int(config['height'])}mm_{len(decoded)}张.pdf"
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition, "X-Safety-Code-Count": str(len(decoded))},
    )
