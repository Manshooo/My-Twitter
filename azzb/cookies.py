"""Согласие на необязательные cookie (баннер, страница /cookies/).

Выбор хранится в cookie посетителя: «v1:analytics» — разрешена аналитика, «v1:necessary» — только
необходимые. Ставит её azzb.js, сервер только читает: без выбора показывает баннер, с выбором
«analytics» отдаёт счётчик Яндекс Метрики. Новая версия (v2…) — когда появится новая категория:
старые ответы перестанут считаться, и баннер спросит заново.
"""
CONSENT_COOKIE = 'cookie_consent'
CONSENT_VERSION = 'v1'
CATEGORIES = ('analytics',)


def cookie_choice(request):
	"""Разрешённые необязательные категории (frozenset) или None, если посетитель ещё не выбирал."""
	raw = request.COOKIES.get(CONSENT_COOKIE, '')
	version, _, rest = raw.partition(':')
	if version != CONSENT_VERSION or not rest:
		return None
	allowed = frozenset(rest.split(',')) & frozenset(CATEGORIES)
	return allowed if rest == 'necessary' or allowed else None
