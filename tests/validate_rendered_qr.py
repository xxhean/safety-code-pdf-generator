from pathlib import Path

from PIL import Image
import zxingcpp


render_dir = Path(__file__).resolve().parent / "rendered"
pages = sorted(render_dir.glob("*.png"))
decoded = []

for page in pages:
    results = zxingcpp.read_barcodes(Image.open(page))
    decoded.append((page.name, [item.text for item in results]))

print(f"rendered_pages={len(decoded)}")
print(f"decoded_pages={sum(bool(items) for _, items in decoded)}")
for name, items in decoded[:3]:
    print(f"{name}: {items[0] if items else 'FAIL'}")

assert len(decoded) == 21, "PDF页数不是21"
assert all(items for _, items in decoded), "至少有一页成品二维码无法回扫"
