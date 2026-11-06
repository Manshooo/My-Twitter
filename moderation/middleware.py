from django.shortcuts import render

# Куда забаненному можно: выйти, прочитать правила и политику, скачать свои данные
# или удалить аккаунт (E6) — это его право и при бане.
BAN_ALLOWED_PREFIXES = ('/auth/logout/', '/static/', '/media/', '/rules/', '/privacy/', '/settings/account/')


class BanMiddleware:
	"""Забаненный (E4) видит вместо любой страницы экран «Аккаунт заблокирован»
	с причиной и сроком. Его посты скрывает Post.objects.visible_to."""

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		user = getattr(request, 'user', None)
		if user is not None and user.is_authenticated and user.is_banned and not request.path.startswith(BAN_ALLOWED_PREFIXES):
			return render(request, 'moderation/banned.html', status=403)
		return self.get_response(request)
