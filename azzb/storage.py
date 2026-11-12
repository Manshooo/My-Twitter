import os

from django.core.files.base import ContentFile
from rcssmin import cssmin
from rjsmin import jsmin
from whitenoise.storage import CompressedManifestStaticFilesStorage

MINIFIERS = {'.css': cssmin, '.js': jsmin}
# Только свои файлы: статику админки, DRF и вендоров не трогаем.
OWN_PREFIXES = ('css/', 'js/')


def minifier_for(name):
	name = name.replace(os.sep, '/')
	if not name.startswith(OWN_PREFIXES) or '.min.' in name:
		return None
	return MINIFIERS.get(os.path.splitext(name)[1])


class MinifiedStaticFilesStorage(CompressedManifestStaticFilesStorage):
	"""Манифест с хешами и gzip/brotli от whitenoise; свои CSS/JS — ещё и минифицированные.

	Минифицирует в _save: через него проходят и копия при collectstatic, и файл с хешем
	из post_process, так что хеш и сжатие считаются уже от минифицированного содержимого.
	"""

	def _save(self, name, content):
		minify = minifier_for(name)
		if minify:
			# post_process передаёт файл, уже прочитанный до конца ради хеша.
			content.seek(0)
			content = ContentFile(minify(content.read().decode('utf-8')).encode('utf-8'))
		return super()._save(name, content)
