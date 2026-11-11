from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils.timezone import now

from . import devices

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
