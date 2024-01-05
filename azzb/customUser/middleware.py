from django.contrib.auth import get_user_model
from django.utils.timezone import now

User = get_user_model()

class SetLastVisitMiddleware(object):
	def __init__(self, get_response):
		self.get_response = get_response
	def __call__(self, request):
		# Code to be executed for each request before
		# the view (and later middleware) are called.
		#
		# ...
		# response = self.get_response(request)
		# ...
		#
		# Code to be executed for each request/response after
		# the view is called.

		# Middleware НЕ ДОЛЖЕН ОБРАБАТЫВАТЬ POST ЗАПРОСЫ!!!

		if request.method == 'GET':
			if request.user.is_authenticated:
				# Update last visit time after request finished processing.
				User.objects.filter(pk=request.user.pk).update(last_visit=now())
				response = self.get_response(request)
		response = self.get_response(request)
		return response

		