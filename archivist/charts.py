import io
import itertools

from PIL import Image, ImageDraw, ImageFont

PALETTE = [
    (231, 76, 60), (52, 152, 219), (46, 204, 113), (241, 196, 15),
    (155, 89, 182), (26, 188, 156), (230, 126, 34), (149, 165, 166),
    (192, 57, 43), (41, 128, 185), (39, 174, 96), (243, 156, 18),
]


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def pie_chart(slices: list[tuple[str, int]], title: str, max_slices: int = 10) -> io.BytesIO:
    """slices: list of (legend_label, value). Groups the smallest entries beyond
    max_slices into an 'Ostatní' bucket. Returns a PNG image buffer."""
    data = sorted((s for s in slices if s[1] > 0), key=lambda s: -s[1])
    if len(data) > max_slices:
        head = data[: max_slices - 1]
        rest_total = sum(v for _, v in data[max_slices - 1 :])
        data = head + [("Ostatní", rest_total)]

    total = sum(v for _, v in data) or 1
    width = 740
    height = max(420, 70 + 26 * len(data))

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    title_font = _font(20, bold=True)
    label_font = _font(15)

    draw.text((20, 16), title, fill=(20, 20, 20), font=title_font)

    cx, cy, r = 210, height // 2 + 10, 160
    start = -90.0
    colors = itertools.cycle(PALETTE)
    legend_y = 60

    for label, value in data:
        angle = 360.0 * value / total
        color = next(colors)
        draw.pieslice([cx - r, cy - r, cx + r, cy + r], start, start + angle, fill=color, outline=(255, 255, 255))
        draw.rectangle([460, legend_y + 2, 478, legend_y + 20], fill=color)
        draw.text((488, legend_y), label, fill=(20, 20, 20), font=label_font)
        legend_y += 26
        start += angle

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def profile_card(
    name: str, tier_name: str, tier_color: tuple[int, int, int], stats: list[tuple[str, str]]
) -> io.BytesIO:
    width = 700
    header_h = 110
    row_h = 42
    pad = 24
    height = header_h + pad * 2 + row_h * len(stats)

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, header_h], fill=tier_color)
    name_font = _font(34, bold=True)
    tier_font = _font(20)
    draw.text((28, 22), name, fill=(255, 255, 255), font=name_font)
    draw.text((28, 66), tier_name, fill=(255, 255, 255), font=tier_font)

    label_font = _font(18)
    value_font = _font(18, bold=True)
    y = header_h + pad
    for i, (label, value) in enumerate(stats):
        if i > 0:
            draw.line([(pad, y), (width - pad, y)], fill=(230, 230, 230), width=1)
        draw.text((pad, y + 10), label, fill=(90, 90, 90), font=label_font)
        bbox = draw.textbbox((0, 0), value, font=value_font)
        value_w = bbox[2] - bbox[0]
        draw.text((width - pad - value_w, y + 8), value, fill=(20, 20, 20), font=value_font)
        y += row_h

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
