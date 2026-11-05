"""Обработка загруженных картинок: проверка, поворот, уменьшение, WebP без метаданных.

Каждая картинка перекодируется заново. Так из файла уходят EXIF и XMP (там бывает
геолокация и модель телефона), а под видом картинки нельзя подсунуть HTML или скрипт:
сервер отдаёт только то, что сам записал в WebP.
"""
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image as PILImage, ImageOps, ImageSequence, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_MB = MAX_UPLOAD_BYTES // (1024 * 1024)
ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}
# В input[accept] и подсказках.
ACCEPT = 'image/jpeg,image/png,image/webp,image/gif'
# Больше 40 Мп на кадр не бывает даже у хороших камер — дальше только «бомбы» на гигабайты памяти.
MAX_PIXELS = 40_000_000
# Сумма пикселей всех кадров анимации: каждый кадр в памяти занимает ширина·высота·4 байта.
MAX_ANIMATION_PIXELS = 100_000_000
MAX_SIDE = 2048
MAX_SIDE_ANIMATED = 1080
WEBP_QUALITY = 82


@dataclass
class ProcessedImage:
	content: ContentFile
	width: int
	height: int


def _open(upload):
	if upload.size > MAX_UPLOAD_BYTES:
		raise ValidationError(f'Картинка «{upload.name}» больше {MAX_UPLOAD_MB} МБ.')
	try:
		upload.seek(0)
		image = PILImage.open(upload)
		# open() читает только заголовок, поэтому размеры известны до распаковки пикселей.
		if image.format not in ALLOWED_FORMATS:
			raise ValidationError(f'«{upload.name}»: поддерживаются JPEG, PNG, WebP и GIF.')
		if image.width * image.height > MAX_PIXELS:
			raise ValidationError(f'«{upload.name}»: слишком большое разрешение.')
		frames = getattr(image, 'n_frames', 1)
		if frames > 1 and image.width * image.height * frames > MAX_ANIMATION_PIXELS:
			raise ValidationError(f'«{upload.name}»: слишком длинная анимация.')
		image.load()
	except ValidationError:
		raise
	except (UnidentifiedImageError, OSError, ValueError, PILImage.DecompressionBombError):
		raise ValidationError(f'«{upload.name}» не похож на картинку или повреждён.')
	return image


def _flatten_mode(image):
	"""RGB или RGBA: WebP не умеет палитры и CMYK."""
	if image.mode in ('RGB', 'RGBA'):
		return image
	has_alpha = image.mode in ('LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info)
	return image.convert('RGBA' if has_alpha else 'RGB')


def _encode(frames, durations=None):
	buffer = BytesIO()
	first = frames[0]
	if len(frames) > 1:
		first.save(
			buffer, 'WEBP', save_all=True, append_images=frames[1:], duration=durations,
			loop=0, quality=WEBP_QUALITY - 6, method=4,
		)
	else:
		first.save(buffer, 'WEBP', quality=WEBP_QUALITY, method=4)
	return ContentFile(buffer.getvalue(), name=f'{uuid4().hex}.webp')


def _crop_box(image, crop):
	"""Область кадрирования в пикселях из долей (x, y, w, h), присланных браузером."""
	x, y, w, h = crop
	left = round(x * image.width)
	top = round(y * image.height)
	right = round((x + w) * image.width)
	bottom = round((y + h) * image.height)
	return left, top, right, bottom


def _center_crop(image, ratio):
	"""Центральная область с соотношением сторон ratio (ширина / высота)."""
	if image.width / image.height > ratio:
		w = round(image.height * ratio)
		left = (image.width - w) // 2
		return left, 0, left + w, image.height
	h = round(image.width / ratio)
	top = (image.height - h) // 2
	return 0, top, image.width, top + h


def parse_crop(value):
	"""«x,y,w,h» в долях от 0 до 1 → кортеж или None, если пусто или испорчено."""
	if not value:
		return None
	try:
		x, y, w, h = (float(part) for part in str(value).split(','))
	except ValueError:
		return None
	if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
		return None
	if x + w > 1.001 or y + h > 1.001:
		return None
	return x, y, min(w, 1 - x), min(h, 1 - y)


def process_post_image(upload):
	"""Картинка для поста: до 2048 px по большей стороне, анимация сохраняется."""
	image = _open(upload)
	if getattr(image, 'n_frames', 1) > 1:
		frames, durations = [], []
		for frame in ImageSequence.Iterator(image):
			durations.append(frame.info.get('duration', 100) or 100)
			frame = frame.convert('RGBA')
			frame.thumbnail((MAX_SIDE_ANIMATED, MAX_SIDE_ANIMATED), PILImage.LANCZOS)
			frames.append(frame)
		return ProcessedImage(_encode(frames, durations), frames[0].width, frames[0].height)

	# Сначала поворачиваем по EXIF (фото с телефона иначе лягут на бок), потом EXIF выкидываем.
	image = _flatten_mode(ImageOps.exif_transpose(image))
	image.thumbnail((MAX_SIDE, MAX_SIDE), PILImage.LANCZOS)
	return ProcessedImage(_encode([image]), image.width, image.height)


def process_cropped_image(upload, size, crop=None):
	"""Аватар или баннер: вырезаем область crop (или центр) и приводим к размеру size.

	Анимация не сохраняется: берётся первый кадр.
	"""
	width, height = size
	image = _flatten_mode(ImageOps.exif_transpose(_open(upload)))
	box = _crop_box(image, crop) if crop else _center_crop(image, width / height)
	image = image.crop(box)
	if image.width < 1 or image.height < 1:
		raise ValidationError('Не удалось обрезать картинку. Выберите область ещё раз.')
	ratio = width / height
	# Браузер присылает область с округлением — добиваем точные пропорции.
	if abs(image.width / image.height - ratio) > 0.01:
		image = image.crop(_center_crop(image, ratio))
	# Маленькие картинки не растягиваем, большие уменьшаем до size.
	if image.width > width:
		image = image.resize(size, PILImage.LANCZOS)
	return ProcessedImage(_encode([image]), image.width, image.height)
