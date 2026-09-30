from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import zxingcpp
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


Image.MAX_IMAGE_PIXELS = 40_000_000

GREEN = (35, 150, 83)
BLACK = (8, 10, 12)
NUMBER_BLUE = (22, 46, 72)
LIGHT_GRAY = (214, 218, 220)
PAGE_SIZES = {
    "mini": {"label": "迷你款", "width": 60.0, "height": 90.0, "qr_pattern": 35.0, "qr_box": 41.0},
    "standard": {"label": "标准款", "width": 80.0, "height": 120.0, "qr_pattern": 43.0, "qr_box": 49.0},
    "large": {"label": "加大款", "width": 100.0, "height": 150.0, "qr_pattern": 60.0, "qr_box": 66.0},
}
LAYOUTS = {
    "left": {"label": "左竖排"},
    "right": {"label": "右竖排"},
}


@dataclass(slots=True)
class DecodedUpload:
    filename: str
    code: str
    qr_text: str
    image: Image.Image


def mm(value: float, dpi: int) -> int:
    return round(value / 25.4 * dpi)


def _font_path(bold: bool = False) -> Path:
    candidates = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("服务器未安装可用的中文字体，请安装 Noto Sans CJK。")


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_font_path(bold)), size=max(8, size))


def parse_safety_code(qr_text: str) -> str:
    text = qr_text.strip()
    if re.fullmatch(r"\d{20}", text):
        return text
    parsed = urlparse(text)
    query_text = parsed.query
    if not query_text and "?" in parsed.fragment:
        query_text = parsed.fragment.split("?", 1)[1]
    values = parse_qs(query_text).get("code", [])
    if len(values) != 1 or not re.fullmatch(r"\d{20}", values[0].strip()):
        raise ValueError("二维码中未找到唯一的20位安全码")
    return values[0].strip()


def _crop_detected_qr(source: Image.Image, result: object) -> Image.Image:
    """Crop only the QR modules using ZXing's detected corner coordinates.

    Some official exports now include a title and safety-code number below the
    QR symbol.  Content-based cropping cannot distinguish those captions from
    the symbol, so use the decoder's geometry and leave the label renderer to
    add its own quiet zone.
    """
    try:
        position = result.position
        points = (
            position.top_left,
            position.top_right,
            position.bottom_right,
            position.bottom_left,
        )
        left = max(0, min(point.x for point in points))
        top = max(0, min(point.y for point in points))
        right = min(source.width, max(point.x for point in points) + 1)
        bottom = min(source.height, max(point.y for point in points) + 1)
    except (AttributeError, TypeError, ValueError):
        return _extract_qr_pattern(source)

    width = right - left
    height = bottom - top
    if width < 21 or height < 21 or not 0.65 <= width / height <= 1.55:
        return _extract_qr_pattern(source)

    # Make the crop square without extending beyond the image.  Straight
    # website exports normally already are square; this also tolerates a few
    # pixels of detector rounding or mild rotation.
    side = max(width, height)
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    square_left = round(center_x - side / 2)
    square_top = round(center_y - side / 2)
    square_left = min(max(0, square_left), max(0, source.width - side))
    square_top = min(max(0, square_top), max(0, source.height - side))
    square_right = min(source.width, square_left + side)
    square_bottom = min(source.height, square_top + side)
    return source.crop((square_left, square_top, square_right, square_bottom)).convert("RGB")


def decode_image(data: bytes, filename: str) -> DecodedUpload:
    try:
        source = Image.open(io.BytesIO(data)).convert("RGB")
        source.load()
    except Exception as exc:
        raise ValueError("文件不是有效图片") from exc
    results = [
        item
        for item in zxingcpp.read_barcodes(source)
        if item.format == zxingcpp.BarcodeFormat.QRCode
    ]
    if not results:
        raise ValueError("未识别到二维码")
    if len(results) > 1:
        raise ValueError("图片中检测到多个二维码，请每张图片只保留一个")
    result = results[0]
    qr_text = result.text
    qr_image = _crop_detected_qr(source, result)
    return DecodedUpload(filename=filename, code=parse_safety_code(qr_text), qr_text=qr_text, image=qr_image)


def format_code(code: str) -> str:
    return " ".join(code[index : index + 4] for index in range(0, len(code), 4))


def _content_bbox(image: Image.Image, y1: int | None = None) -> tuple[int, int, int, int] | None:
    crop = image.crop((0, 0, image.width, y1 or image.height)).convert("L")
    mask = crop.point(lambda pixel: 255 if pixel < 242 else 0)
    return mask.getbbox()


def _extract_qr_pattern(source: Image.Image) -> Image.Image:
    is_square = 0.85 <= source.width / source.height <= 1.15
    search_bottom = source.height if is_square else round(source.height * 0.76)
    bbox = _content_bbox(source, search_bottom)
    if bbox is None:
        raise ValueError("无法定位二维码图案")
    left, top, right, bottom = bbox
    side = max(right - left, bottom - top)
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    left = max(0, round(center_x - side / 2))
    top = max(0, round(center_y - side / 2))
    right = min(source.width, left + side)
    crop_limit = source.height if is_square else round(source.height * 0.78)
    bottom = min(crop_limit, top + side)
    return source.crop((left, top, right, bottom)).convert("RGB")


def _green_qr(source: Image.Image, size: int) -> Image.Image:
    qr = _extract_qr_pattern(source).resize((size, size), Image.Resampling.NEAREST)
    gray = qr.convert("L")
    ink_mask = gray.point(lambda pixel: 255 if pixel < 238 else 0)
    white = Image.new("RGB", (size, size), "white")
    green = Image.new("RGB", (size, size), GREEN)
    return Image.composite(green, white, ink_mask)


def _draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text((xy[0] - width / 2, xy[1] - height / 2 - box[1]), text, font=font, fill=fill)


def _draw_scan_icon(draw: ImageDraw.ImageDraw, dpi: int, scale: float) -> None:
    x0, y0 = mm(9.5 * scale, dpi), mm(96.0 * scale, dpi)
    # Keep this mark identical to the approved print template: two open
    # scanning brackets around a smaller rounded square and green tick.
    icon = mm(13.0 * scale, dpi)
    stroke = max(3, mm(0.55 * scale, dpi))
    draw.arc((x0, y0, x0 + icon, y0 + icon), 90, 185, fill=BLACK, width=stroke)
    draw.arc((x0, y0, x0 + icon, y0 + icon), 270, 365, fill=BLACK, width=stroke)
    inner = (x0 + mm(3.0 * scale, dpi), y0 + mm(3.0 * scale, dpi), x0 + icon - mm(3.0 * scale, dpi), y0 + icon - mm(3.0 * scale, dpi))
    draw.rounded_rectangle(inner, radius=mm(1.7 * scale, dpi), outline=BLACK, width=max(2, stroke - 1))
    p1 = (x0 + mm(5.0 * scale, dpi), y0 + mm(7.0 * scale, dpi))
    p2 = (x0 + mm(6.7 * scale, dpi), y0 + mm(8.7 * scale, dpi))
    p3 = (x0 + mm(10.1 * scale, dpi), y0 + mm(5.0 * scale, dpi))
    draw.line((p1, p2, p3), fill=GREEN, width=stroke, joint="curve")


def _draw_nfc_icon(draw: ImageDraw.ImageDraw, dpi: int, scale: float) -> None:
    x0, y0 = mm(10.2 * scale, dpi), mm(91.0 * scale, dpi)
    size = mm(11.8 * scale, dpi)
    stroke = max(3, mm(0.5 * scale, dpi))
    draw.rounded_rectangle((x0, y0, x0 + size, y0 + size), radius=mm(1.5 * scale, dpi), outline=BLACK, width=stroke)
    center_x = x0 + mm(5.1 * scale, dpi)
    center_y = y0 + mm(5.3 * scale, dpi)
    dot_r = max(2, mm(0.45 * scale, dpi))
    draw.ellipse((center_x - dot_r, center_y - dot_r, center_x + dot_r, center_y + dot_r), fill=BLACK)
    for radius_mm, start in ((2.0, 278), (3.5, 280), (5.0, 282)):
        radius = mm(radius_mm * scale, dpi)
        draw.arc((center_x - radius, center_y - radius, center_x + radius, center_y + radius), start=start, end=355, fill=BLACK, width=stroke)
    radius = mm(3.6 * scale, dpi)
    draw.arc((center_x - radius, center_y - radius, center_x + radius, center_y + radius), start=100, end=180, fill=BLACK, width=stroke)


def _create_right_label(item: DecodedUpload, size_key: str, dpi: int, rescue_phone: str) -> Image.Image:
    config = PAGE_SIZES[size_key]
    page_w_mm, page_h_mm = config["width"], config["height"]
    scale = page_w_mm / 80.0
    page_w, page_h = mm(page_w_mm, dpi), mm(page_h_mm, dpi)
    label = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(label)

    inset = mm(1.2 * scale, dpi)
    draw.rounded_rectangle(
        (inset, inset, page_w - inset - 1, page_h - inset - 1),
        radius=mm(6.0 * scale, dpi), outline=LIGHT_GRAY,
        width=max(2, mm(0.3 * scale, dpi)), fill="white",
    )

    qr_box = mm(48.0 * scale, dpi)
    qr_pattern = mm(42.0 * scale, dpi)
    quiet = Image.new("RGB", (qr_box, qr_box), "white")
    green_qr = _green_qr(item.image, qr_pattern)
    quiet.paste(green_qr, ((qr_box - qr_pattern) // 2, (qr_box - qr_pattern) // 2))
    label.paste(quiet, (mm(6.0 * scale, dpi), mm(9.0 * scale, dpi)))

    vertical_font = load_font(mm(10.1 * scale, dpi), bold=True)
    for index, char in enumerate("码上知详情"):
        _draw_centered(
            draw, (mm(65.5 * scale, dpi), mm((13.0 + index * 11.0) * scale, dpi)),
            char, vertical_font, GREEN if char == "情" else BLACK,
        )

    title_font = load_font(mm(4.8 * scale, dpi), bold=True)
    _draw_centered(draw, (mm(30.0 * scale, dpi), mm(65.0 * scale, dpi)), "特种设备安全码", title_font, BLACK)
    number_font = load_font(mm(3.4 * scale, dpi), bold=True)
    _draw_centered(draw, (mm(30.0 * scale, dpi), mm(75.5 * scale, dpi)), format_code(item.code), number_font, NUMBER_BLUE)
    if rescue_phone:
        rescue_font = load_font(mm(3.0 * scale, dpi), bold=True)
        _draw_centered(draw, (mm(30.0 * scale, dpi), mm(84.5 * scale, dpi)), f"救援电话:{rescue_phone}", rescue_font, BLACK)

    points = [
        (mm(55.5 * scale, dpi), mm(8.0 * scale, dpi)),
        (mm(55.5 * scale, dpi), mm(82.0 * scale, dpi)),
        (mm(43.5 * scale, dpi), mm(95.0 * scale, dpi)),
        (mm(23.0 * scale, dpi), mm(95.0 * scale, dpi)),
    ]
    draw.line(points, fill=(34, 37, 39), width=max(2, mm(0.35 * scale, dpi)), joint="curve")
    _draw_nfc_icon(draw, dpi, scale)
    return label


def create_label(item: DecodedUpload, size_key: str, dpi: int = 300, rescue_phone: str = "", layout_key: str = "left") -> Image.Image:
    if size_key not in PAGE_SIZES:
        raise ValueError("不支持的标识牌尺寸")
    if layout_key not in LAYOUTS:
        raise ValueError("不支持的版式")
    if layout_key == "right":
        return _create_right_label(item, size_key, dpi, rescue_phone)
    config = PAGE_SIZES[size_key]
    page_w_mm, page_h_mm = config["width"], config["height"]
    scale = page_w_mm / 80.0
    page_w, page_h = mm(page_w_mm, dpi), mm(page_h_mm, dpi)
    label = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(label)

    inset = mm(1.2 * scale, dpi)
    draw.rounded_rectangle(
        (inset, inset, page_w - inset - 1, page_h - inset - 1),
        radius=mm(6.0 * scale, dpi),
        outline=LIGHT_GRAY,
        width=max(2, mm(0.3 * scale, dpi)),
        fill="white",
    )

    vertical_font = load_font(mm(10.4 * scale, dpi), bold=True)
    for index, char in enumerate("码上知详情"):
        _draw_centered(
            draw,
            (mm(12.9 * scale, dpi), mm((12.0 + index * 11.8) * scale, dpi)),
            char,
            vertical_font,
            GREEN if char == "情" else BLACK,
        )

    line_x = mm(26.5 * scale, dpi)
    draw.line(
        (line_x, mm(48.0 * scale, dpi), line_x, mm(109.0 * scale, dpi)),
        fill=(42, 45, 47),
        width=max(2, mm(0.35 * scale, dpi)),
    )
    _draw_scan_icon(draw, dpi, scale)

    qr_box = mm(config["qr_box"], dpi)
    qr_pattern = mm(config["qr_pattern"], dpi)
    quiet = Image.new("RGB", (qr_box, qr_box), "white")
    green_qr = _green_qr(item.image, qr_pattern)
    offset = (qr_box - qr_pattern) // 2
    quiet.paste(green_qr, (offset, offset))
    qr_center_x = mm(53.0 * scale, dpi)
    qr_x = qr_center_x - qr_box // 2
    qr_y = mm(7.5 * scale, dpi)
    label.paste(quiet, (qr_x, qr_y))

    title_font = load_font(mm(5.7 * scale, dpi), bold=True)
    _draw_centered(draw, (mm(53.0 * scale, dpi), mm(70.8 * scale, dpi)), "特种设备安全码", title_font, BLACK)
    number_font = load_font(mm(3.4 * scale, dpi), bold=True)
    _draw_centered(draw, (mm(53.0 * scale, dpi), mm(88.0 * scale, dpi)), format_code(item.code), number_font, NUMBER_BLUE)
    note_font = load_font(mm(2.45 * scale, dpi), bold=False)
    _draw_centered(draw, (mm(53.0 * scale, dpi), mm(100.0 * scale, dpi)), "扫码查询设备信息 · 一机一码", note_font, NUMBER_BLUE)
    if rescue_phone:
        rescue_font = load_font(mm(3.25 * scale, dpi), bold=True)
        _draw_centered(draw, (mm(53.0 * scale, dpi), mm(107.0 * scale, dpi)), f"救援电话:{rescue_phone}", rescue_font, BLACK)
    return label


def build_pdf(items: list[DecodedUpload], size_key: str, rescue_phone: str = "", dpi: int = 300, layout_key: str = "left") -> bytes:
    config = PAGE_SIZES[size_key]
    points_per_mm = 72.0 / 25.4
    page_size = (config["width"] * points_per_mm, config["height"] * points_per_mm)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=page_size, pageCompression=1)
    for item in items:
        label = create_label(item, size_key=size_key, dpi=dpi, rescue_phone=rescue_phone, layout_key=layout_key)
        image_buffer = io.BytesIO()
        label.save(image_buffer, format="PNG", dpi=(dpi, dpi), optimize=True)
        image_buffer.seek(0)
        pdf.drawImage(ImageReader(image_buffer), 0, 0, width=page_size[0], height=page_size[1])
        pdf.showPage()
    pdf.save()
    return output.getvalue()
