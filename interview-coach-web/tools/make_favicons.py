"""MockMate 파비콘 생성 스크립트 (일회용 도구, 서버와 무관)

실행 (interview-coach-web 폴더에서):
    backend/venv/bin/pip install -r backend/requirements-dev.txt   # Pillow, 처음 한 번
    backend/venv/bin/python tools/make_favicons.py

하는 일
1. 원본 정리 → frontend/public/brand/mockmate-icon-clean.png (원본은 덮어쓰지 않음)
   - 반투명 가장자리 픽셀(α 4~250)의 색을 안쪽 남색 배경색으로 맞춤
     (밝은 배경 위에서 흰/회색 테두리처럼 보이는 것을 방지)
   - 바깥의 거의 안 보이는 잡티(α ≤ 3)는 완전 투명으로
   - 안쪽 면의 α 252~253(살짝 비침)은 255(불투명)로
2. 16·32px용 단순화 버전 → frontend/public/brand/mockmate-icon-simple.png
   - 그물망 → 흰 면, 빛(glow) 효과 제거, 모서리 선·받침대 선 굵게, 요소 사이 간격 넓힘
   - 원본에서 잰 위치(1254px 기준 좌표)를 바탕으로 직접 다시 그림
3. 파비콘: favicon-16/32.png(단순화), favicon.ico(16·32 단순화 + 48 정리본),
   apple-touch-icon.png(180), icon-192.png, icon-512.png(정리본)
4. 비교 이미지: tools/favicon-compare.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
BRAND = PUBLIC / "brand"
ORIGINAL = BRAND / "mockmate-icon-original.png"
CLEAN = BRAND / "mockmate-icon-clean.png"
SIMPLE = BRAND / "mockmate-icon-simple.png"
COMPARE = ROOT / "tools" / "favicon-compare.png"

# 원본에서 측정한 색
NAVY = (1, 11, 39)
CYAN = (31, 246, 252)  # 왼쪽 모서리 선
INDIGO = (89, 99, 255)  # 오른쪽 모서리 선
WHITE = (255, 255, 255)


# ── 1. 원본 정리 ───────────────────────────────────────────────────────────
def clean_original(src: Image.Image) -> Image.Image:
    im = src.convert("RGBA")
    px = im.load()
    w, h = im.size
    stats = {"edge_recolored": 0, "noise_cleared": 0, "made_opaque": 0}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if a <= 3:
                px[x, y] = (0, 0, 0, 0)
                stats["noise_cleared"] += 1
            elif a <= 250:
                # 반투명 픽셀은 둥근 사각형 바깥 테두리에만 있다(안쪽 면은 모두 α 252 이상).
                px[x, y] = (*NAVY, a)
                stats["edge_recolored"] += 1
            elif a < 255:
                px[x, y] = (r, g, b, 255)
                stats["made_opaque"] += 1
    print("정리 결과:", stats)
    return im


# ── 2. 단순화 버전 그리기 ──────────────────────────────────────────────────
def draw_simple(size: int = 1254) -> Image.Image:
    """원본과 같은 1254px 좌표계에서 그린 뒤 필요한 크기로 줄인다."""
    S = 4  # 4배로 크게 그렸다가 줄여서 가장자리를 매끄럽게(안티앨리어싱)
    im = Image.new("RGBA", (1254 * S, 1254 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def box(x1, y1, x2, y2):
        return [x1 * S, y1 * S, x2 * S, y2 * S]

    # 배경: 남색 둥근 사각형 (원본 외곽 31~1213 × 32~1221)
    d.rounded_rectangle(box(31, 32, 1213, 1221), radius=230 * S, fill=(*NAVY, 255))

    # 모서리 선: 원본 두께 14 → 58 (위치는 원본과 같게, 바깥쪽으로 약간 이동)
    t, L = 58, 150
    corners = [
        (300, 190, 1, 1, CYAN), (954, 190, -1, 1, INDIGO),
        (300, 925, 1, -1, CYAN), (954, 925, -1, -1, INDIGO),
    ]
    for x, y, sx, sy, color in corners:
        xa, xb = sorted([x, x + sx * L])
        ya, yb = sorted([y, y + sy * L])
        xt1, xt2 = sorted([x, x + sx * t])
        yt1, yt2 = sorted([y, y + sy * t])
        d.rounded_rectangle(box(xa, yt1, xb, yt2), radius=t // 2 * S, fill=(*color, 255))
        d.rounded_rectangle(box(xt1, ya, xt2, yb), radius=t // 2 * S, fill=(*color, 255))

    # 마이크 몸통: 그물망 대신 흰 면 (원본 x 492~760보다 조금 좁혀서 받침대와 간격 확보)
    d.rounded_rectangle(box(512, 250, 742, 745), radius=115 * S, fill=(*WHITE, 255))
    # 카메라 렌즈: 빛 효과 없이 남색 테두리 + 시안 원
    d.ellipse(box(627 - 78, 560 - 78, 627 + 78, 560 + 78), fill=(*NAVY, 255))
    d.ellipse(box(627 - 50, 560 - 50, 627 + 50, 560 + 50), fill=(*CYAN, 255))
    # U자 받침대: 원본 두께 26 → 50, 몸통과 간격 넓힘
    stroke = 50
    cx, cy, r = 627, 610, 205  # 반원의 중심과 반지름(선 중심 기준)
    d.arc(box(cx - r - stroke / 2, cy - r - stroke / 2, cx + r + stroke / 2, cy + r + stroke / 2),
          start=0, end=180, fill=(*WHITE, 255), width=stroke * S)
    for ax in (cx - r - stroke / 2, cx + r - stroke / 2):  # 양쪽 팔(위로 올라가는 부분)
        # 위쪽 끝만 둥글게: 둥근 막대 + 아래 절반을 덮는 직사각형(반원과 이어지는 부분에 홈이 생기지 않게)
        d.rounded_rectangle(box(ax, 500, ax + stroke, cy), radius=stroke // 2 * S, fill=(*WHITE, 255))
        d.rectangle(box(ax, 560, ax + stroke, cy + 10), fill=(*WHITE, 255))
    # 기둥과 받침
    d.rectangle(box(594, cy + r - 5, 660, 960), fill=(*WHITE, 255))
    d.chord(box(470, 930, 784, 1090), start=180, end=360, fill=(*WHITE, 255))

    return im.resize((size, size), Image.LANCZOS)


# ── 3. 파비콘 저장 ─────────────────────────────────────────────────────────
def resized(im: Image.Image, s: int) -> Image.Image:
    # Pillow는 RGBA를 줄일 때 내부적으로 '미리 곱한 알파'로 계산해서 가장자리에 검은 테두리가 생기지 않는다.
    return im.resize((s, s), Image.LANCZOS)


def save_icons(clean: Image.Image, simple: Image.Image) -> None:
    resized(simple, 16).save(PUBLIC / "favicon-16.png", optimize=True)
    resized(simple, 32).save(PUBLIC / "favicon-32.png", optimize=True)
    resized(clean, 180).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    resized(clean, 192).save(PUBLIC / "icon-192.png", optimize=True)
    resized(clean, 512).save(PUBLIC / "icon-512.png", optimize=True)
    # ICO: 크기마다 다른 그림을 넣기 위해 append_images 사용 (16·32는 단순화, 48은 정리본)
    resized(clean, 48).save(
        PUBLIC / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[resized(simple, 16), resized(simple, 32)],
    )


# ── 4. 비교 이미지 ─────────────────────────────────────────────────────────
def make_compare(clean: Image.Image, simple: Image.Image) -> None:
    """16/32/64px를 실제 크기와 4배 확대(픽셀 그대로)로 밝은·어두운 배경에 배치."""
    zoom, pad, label_h = 4, 24, 26
    font = ImageFont.load_default(size=15)
    rows = [("clean", clean, [16, 32, 64]), ("simple (16-32px)", simple, [16, 32, 64])]
    backgrounds = [((255, 255, 255), (40, 40, 40)), ((32, 33, 36), (230, 230, 230))]
    col_w = [s * zoom + pad for s in (16, 32, 64)]
    real_w = 16 + 32 + 64 + pad * 3
    W = pad + sum(col_w) + real_w + pad
    block_h = label_h + 64 * zoom + pad
    H = (block_h * len(rows)) * len(backgrounds) + pad
    out = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(out)
    y = 0
    for bg, fg in backgrounds:
        for name, src, sizes in rows:
            d.rectangle([0, y, W, y + block_h], fill=bg)
            d.text((pad, y + 6), f"{name}  |  4x zoom: 16 / 32 / 64px   |   actual size", fill=fg, font=font)
            x = pad
            for s in sizes:
                small = resized(src, s)
                big = small.resize((s * zoom, s * zoom), Image.NEAREST)
                out.paste(big, (x, y + label_h), big)
                x += s * zoom + pad
            for s in sizes:  # 실제 크기
                small = resized(src, s)
                out.paste(small, (x, y + label_h), small)
                x += s + pad
            y += block_h
    out.save(COMPARE, optimize=True)


def main() -> None:
    original = Image.open(ORIGINAL)
    clean = clean_original(original)
    clean.save(CLEAN, optimize=True)
    simple = draw_simple()
    simple.save(SIMPLE, optimize=True)
    save_icons(clean, simple)
    make_compare(clean, simple)
    print("완료:", CLEAN.name, SIMPLE.name, "파비콘 6종", COMPARE.name)


if __name__ == "__main__":
    main()
