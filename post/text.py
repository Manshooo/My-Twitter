"""Разбор хэштегов, упоминаний и веб-адресов в пользовательском тексте."""
import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

HASHTAG_MAX_LENGTH = 64
# \w в Python — с кириллицей. Перед знаком не должно быть буквы: «a#b» и «почта@site.ru» — не теги.
HASHTAG_RE = re.compile(r'(?<![\w#])#(\w{1,%d})' % HASHTAG_MAX_LENGTH)
# Те же символы, что разрешены в логине (accounts.models.UsernameValidator).
MENTION_RE = re.compile(r'(?<![\w@])@([a-zA-Z0-9_.-]{1,30})')
TOKEN_RE = re.compile(f'{HASHTAG_RE.pattern}|{MENTION_RE.pattern}')
# Граница исключает домены внутри почтовых адресов и ссылок с другими схемами.
WEB_URL_RE = re.compile(
	r'''(?<![\w@#.:/\\-])(?:https?://|[^\W_][\w-]*\.(?=[^\W_]))[^\s<>"'«»„“”‘’]+''',
	re.IGNORECASE,
)
validate_web_url = URLValidator(schemes=['http', 'https'])
WRAPPING_PUNCTUATION = {')': '(', ']': '[', '}': '{'}


def _mention(raw):
	# Точка и дефис в конце — чаще знаки препинания («спасибо, @ann.»), чем часть логина.
	return raw.rstrip('.-')


def _is_tag(name):
	# «#1» и «#2024» — номера, а не теги.
	return not name.replace('_', '').isdigit()


def _trim_url(raw):
	url = raw.rstrip('.,:;!?…')
	while url and (opening := WRAPPING_PUNCTUATION.get(url[-1])) and url.count(url[-1]) > url.count(opening):
		url = url[:-1].rstrip('.,:;!?…')
	return url


def _split_web_urls(text):
	start = 0
	for match in WEB_URL_RE.finditer(text):
		if len(match[0]) > validate_web_url.max_length:
			continue
		url = _trim_url(match[0])
		href = url if url.lower().startswith(('https://', 'http://')) else f'https://{url}'
		try:
			validate_web_url(href)
		except ValidationError:
			continue
		if '\\' in url or urlsplit(href).username is not None:
			continue
		yield text[start:match.start()], None
		yield url, href
		start = match.start() + len(url)
	yield text[start:], None


def _find_entities(pattern, text):
	for part, href in _split_web_urls(text or ''):
		if href is None:
			yield from pattern.findall(part)


def hashtags(text):
	"""Теги поста в нижнем регистре, без повторов, в порядке появления."""
	names = (match.lower() for match in _find_entities(HASHTAG_RE, text))
	return list(dict.fromkeys(name for name in names if _is_tag(name)))


def mentions(text):
	"""Логины из @упоминаний, без повторов. Существуют ли такие люди, проверяет вызывающий."""
	names = (_mention(match) for match in _find_entities(MENTION_RE, text))
	return list(dict.fromkeys(name for name in names if name))


def _link_entities(text):
	parts, last = [], 0
	for match in TOKEN_RE.finditer(text):
		tag, login = match.group(1), match.group(2)
		if tag is not None:
			if not _is_tag(tag):
				continue
			start, end = match.span()
			link = f'<a class="tag-link" href="{reverse("hashtag", args=[tag.lower()])}">#{escape(tag)}</a>'
		else:
			login = _mention(login)
			if not login:
				continue
			start, end = match.start(), match.start() + 1 + len(login)
			link = f'<a class="mention-link" href="{reverse("profile", args=[login])}">@{escape(login)}</a>'
		parts.append(escape(text[last:start]))
		parts.append(link)
		last = end
	parts.append(escape(text[last:]))
	return ''.join(parts)


def linkify(text, *, urls=True, entities=True):
	text = text or ''
	if not urls:
		return mark_safe(_link_entities(text) if entities else escape(text))
	parts = []
	for part, href in _split_web_urls(text):
		if href is not None:
			parts.append(format_html('<a class="url-link" href="{}" rel="ugc nofollow">{}</a>', href, part))
		else:
			parts.append(_link_entities(part) if entities else escape(part))
	return mark_safe(''.join(parts))
