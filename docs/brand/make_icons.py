"""Иконки сайта из знака «Круг» (docs/brand/logo.svg).

Запуск из корня проекта: python docs/brand/make_icons.py
Пишет в azzb/static/: favicon.ico (16/32/48, жирная версия — как в favicon.svg), apple-touch-icon.png (180),
icon-192.png, icon-512.png, icon-maskable-512.png. favicon.svg и manifest правятся руками,
картинка для превью ссылок (og-default.png, 1200×630) рисуется отдельно, на canvas в браузере:
ей нужен шрифт Unbounded, а у Pillow его нет.

Pillow не рисует SVG, поэтому геометрия знака повторена здесь: рисуем в 16 раз крупнее
и уменьшаем — так края получаются сглаженными.
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[2] / "azzb" / "static"
CIRCLE = "#13302f"  # --primary светлой темы
INK = "#b6dfdf"  # --brand
SS = 16  # во сколько раз крупнее рисуем перед уменьшением


# Геометрия знака в viewBox 64×64: вершина буквы, толщина линии, центр и радиус точки.
REGULAR = {"apex": 16, "width": 6.5, "dot_y": 38, "dot_r": 3.6}  # docs/brand/logo.svg
# Фавиконка жирнее: в 16 px обычная толщина сливается в серое пятно (azzb/static/favicon.svg).
HEAVY = {"apex": 15, "width": 8, "dot_y": 38.5, "dot_r": 4.6}


def mark(size, *, square=False, scale=1.0, geo=REGULAR):
	"""Знак size×size. square — фон на весь квадрат (iOS и Android сами скругляют углы),
	scale — уменьшить букву к центру, чтобы она влезла в «безопасную зону» маскируемой иконки,
	geo — REGULAR или HEAVY (для фавиконки)."""
	big = size * SS
	k = big / 64  # единица viewBox 64×64
	img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
	draw = ImageDraw.Draw(img)
	if square:
		draw.rectangle((0, 0, big, big), fill=CIRCLE)
	else:
		draw.ellipse((0, 0, big - 1, big - 1), fill=CIRCLE)

	def p(x, y):
		return (32 + (x - 32) * scale) * k, (32 + (y - 32) * scale) * k

	width = geo["width"] * scale * k
	points = [p(19, 47), p(32, geo["apex"]), p(45, 47)]
	draw.line(points, fill=INK, width=round(width), joint="curve")
	for x, y in points:  # скруглённые концы и вершина (stroke-linecap/linejoin: round)
		r = width / 2
		draw.ellipse((x - r, y - r, x + r, y + r), fill=INK)
	cx, cy = p(32, geo["dot_y"])
	r = geo["dot_r"] * scale * k
	draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
	return img.resize((size, size), Image.LANCZOS)


def main():
	sizes = (16, 32, 48)
	icons = [mark(s, geo=HEAVY) for s in sizes]
	icons[-1].save(OUT / "favicon.ico", sizes=[(s, s) for s in sizes], append_images=icons[:-1])
	mark(180, square=True).convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)
	mark(192).save(OUT / "icon-192.png", optimize=True)
	mark(512).save(OUT / "icon-512.png", optimize=True)
	# Безопасная зона маскируемой иконки — круг диаметром 80% стороны.
	mark(512, square=True, scale=0.8).convert("RGB").save(OUT / "icon-maskable-512.png", optimize=True)
	print("Готово:", OUT)


if __name__ == "__main__":
	main()
