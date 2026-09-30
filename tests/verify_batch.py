from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import zxingcpp
from PIL import Image
from pypdf import PdfReader


def qr_text(path: Path) -> str:
    items = zxingcpp.read_barcodes(Image.open(path))
    if len(items) != 1:
        raise RuntimeError(f"{path.name}: 识别到{len(items)}个二维码")
    return items[0].text


def safety_code(text: str) -> str:
    parsed = urlparse(text)
    query = parse_qs(parsed.query)
    fragment_query = parse_qs(urlparse(parsed.fragment).query)
    values = query.get("code", []) + fragment_query.get("code", [])
    for value in values:
        if re.fullmatch(r"\d{20}", value):
            return value
    match = re.search(r"(?<!\d)(\d{20})(?!\d)", text)
    if not match:
        raise RuntimeError(f"二维码中没有20位安全码: {text}")
    return match.group(1)


source_dir = Path(sys.argv[1])
pdf_path = Path(sys.argv[2])
render_dir = Path(sys.argv[3])

source_images = sorted(
    path
    for path in source_dir.iterdir()
    if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
)
rendered_pages = sorted(render_dir.glob("*.png"))

source_codes = sorted(safety_code(qr_text(path)) for path in source_images)
rendered_codes = [safety_code(qr_text(path)) for path in rendered_pages]

reader = PdfReader(pdf_path)
page = reader.pages[0]
width_mm = float(page.mediabox.width) * 25.4 / 72
height_mm = float(page.mediabox.height) * 25.4 / 72

assert len(source_codes) == 21, f"源图片数量异常: {len(source_codes)}"
assert len(set(source_codes)) == 21, "源图片存在重复安全码"
assert len(reader.pages) == 21, f"PDF页数异常: {len(reader.pages)}"
assert len(rendered_pages) == 21, f"渲染页数异常: {len(rendered_pages)}"
assert rendered_codes == source_codes, "成品二维码与源安全码不一致或排序错误"
assert abs(width_mm - 80) < 0.01 and abs(height_mm - 120) < 0.01, (
    f"页面尺寸异常: {width_mm:.2f} x {height_mm:.2f} mm"
)

print("source_images=21")
print("unique_codes=21")
print("pdf_pages=21")
print(f"page_size_mm={width_mm:.2f}x{height_mm:.2f}")
print("rendered_qr_decoded=21")
print("source_and_output_codes_match=true")
