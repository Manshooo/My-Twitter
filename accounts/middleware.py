from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.timezone import now

from . import consent, devices

User = get_user_model()

# Не пишем в БД на каждый запрос: «последний визит» с точностью до 5 минут достаточен.
LAST_VISIT_UPDATE_INTERVAL = timedelta(minutes=5)

class SetLastVisitMiddleware:
	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		# Обновляем только на GET: POST-запросы (лайки, посты) не считаются «визитом».
		if request.method == 'GET' and request.user.is_authenticated:
			current_time = now()
			last_visit = request.user.last_visit
			if last_visit is None or current_time - last_visit >= LAST_VISIT_UPDATE_INTERVAL:
				User.objects.filter(pk=request.user.pk).update(last_visit=current_time)
			devices.touch_session(request)
		# Раньше get_response вызывался здесь дважды, и страница рендерилась два раза.
		return self.get_response(request)


# Куда можно, пока не принята новая редакция: сам экран, документы, выход, данные и удаление аккаунта.
CONSENT_ALLOWED_PREFIXES = (
	'/consent/', '/auth/logout/', '/static/', '/media/', '/rules/', '/privacy/', '/cookies/', '/settings/account/',
	'/api/events/', '/sw.js', '/offline/', '/robots.txt', '/healthz', '/favicon.ico',
)


class ConsentMiddleware:
	"""Документы обновились (accounts.consent.EDITION) — вошедший, кто соглашался с прежней редакцией
	или вовсе до появления галочек, сначала видит экран новой редакции (accounts.views.consent_update)."""

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		user = getattr(request, 'user', None)
		if (
			user is not None and user.is_authenticated and not consent.is_current(user)
			and not request.path.startswith(CONSENT_ALLOWED_PREFIXES)
		):
			url = reverse('consent-update')
			if request.method == 'GET':
				url += '?' + urlencode({'next': request.get_full_path()})
			if request.headers.get('HX-Request'):
				response = HttpResponse(status=204)
				response['HX-Redirect'] = url
				return response
			return redirect(url)
		return self.get_response(request)
