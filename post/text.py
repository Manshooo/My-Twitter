"""#хэштеги и @упоминания в тексте поста (D2): разбор при сохранении и ссылки при выводе."""
import re

from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

HASHTAG_MAX_LENGTH = 64
# \w в Python — с кириллицей. Перед знаком не должно быть буквы: «a#b» и «почта@site.ru» — не теги.
HASHTAG_RE = re.compile(r'(?<![\w#])#(\w{1,%d})' % HASHTAG_MAX_LENGTH)
# Те же символы, что разрешены в логине (accounts.models.UsernameValidator).
MENTION_RE = re.compile(r'(?<![\w@])@([a-zA-Z0-9_.-]{1,30})')
TOKEN_RE = re.compile(f'{HASHTAG_RE.pattern}|{MENTION_RE.pattern}')


def _mention(raw):
	# Точка и дефис в конце — чаще знаки препинания («спасибо, @ann.»), чем часть логина.
	return raw.rstrip('.-')


def _is_tag(name):
	# «#1» и «#2024» — номера, а не теги.
	return not name.replace('_', '').isdigit()


def hashtags(text):
	"""Теги поста в нижнем регистре, без повторов, в порядке появления."""
	names = (match.lower() for match in HASHTAG_RE.findall(text or ''))
	return list(dict.fromkeys(name for name in names if _is_tag(name)))


def mentions(text):
	"""Логины из @упоминаний, без повторов. Существуют ли такие люди, проверяет вызывающий."""
	names = (_mention(match) for match in MENTION_RE.findall(text or ''))
	return list(dict.fromkeys(name for name in names if name))


def linkify(text):
	"""Текст поста в HTML: теги и упоминания — ссылки, остальное экранировано.
	Ссылку на @логин ставим по виду, без запроса к базе: несуществующий логин откроет 404."""
	text = text or ''
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
	return mark_safe(''.join(parts))
