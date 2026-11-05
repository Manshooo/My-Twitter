from datetime import timedelta

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils.timezone import now

from .middleware import SetLastVisitMiddleware
from .models import Profile

User = get_user_model()


class ProfileSignalTests(TestCase):
	def test_user_gets_exactly_one_profile_without_self_follow(self):
		user = User.objects.create_user('alice', 'alice@example.com', 'pass-12345')
		self.assertEqual(Profile.objects.filter(user=user).count(), 1)
		self.assertEqual(user.profile.username, 'alice')
		self.assertFalse(user.profile.follows.exists())


class SetLastVisitMiddlewareTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user('bob', 'bob@example.com', 'pass-12345')
		self.calls = 0

		def get_response(request):
			self.calls += 1
			return HttpResponse('ok')

		self.middleware = SetLastVisitMiddleware(get_response)

	def make_request(self, method='get'):
		request = getattr(RequestFactory(), method)('/')
		request.user = User.objects.get(pk=self.user.pk)
		return request

	def test_view_is_called_once_and_last_visit_set(self):
		self.middleware(self.make_request())
		self.assertEqual(self.calls, 1)
		self.user.refresh_from_db()
		self.assertIsNotNone(self.user.last_visit)

	def test_post_does_not_update_last_visit(self):
		self.middleware(self.make_request('post'))
		self.assertEqual(self.calls, 1)
		self.user.refresh_from_db()
		self.assertIsNone(self.user.last_visit)

	def test_recent_visit_is_not_rewritten(self):
		recent = now() - timedelta(minutes=1)
		User.objects.filter(pk=self.user.pk).update(last_visit=recent)
		self.middleware(self.make_request())
		self.user.refresh_from_db()
		self.assertEqual(self.user.last_visit, recent)

	def test_stale_visit_is_updated(self):
		stale = now() - timedelta(hours=1)
		User.objects.filter(pk=self.user.pk).update(last_visit=stale)
		self.middleware(self.make_request())
		self.user.refresh_from_db()
		self.assertGreater(self.user.last_visit, stale)
