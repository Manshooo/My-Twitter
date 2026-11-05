from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils.timezone import now
from PIL import Image as PILImage

from post.tests import MEDIA_ROOT, make_upload

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


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AvatarAndBannerTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user('carol', 'carol@example.com', 'pass-12345')
		self.client.force_login(self.user)

	def edit(self, **extra):
		data = {'username': 'Кэрол', 'email': 'carol@example.com', 'first_name': '', 'last_name': '', 'bio': ''}
		data.update(extra)
		return self.client.post('/edit/', data)

	def test_upload_with_crop_makes_square_avatar_and_wide_banner(self):
		response = self.edit(
			avatar=make_upload('me.jpg', size=(1200, 600)), avatar_crop='0.25,0,0.5,1',
			banner=make_upload('top.png', size=(3000, 1500), fmt='PNG'),
		)
		self.assertEqual(response.status_code, 302)
		profile = self.user.profile.__class__.objects.get(pk=self.user.profile.pk)
		self.assertTrue(profile.has_custom_avatar)
		with PILImage.open(profile.avatar.path) as avatar:
			self.assertEqual((avatar.format, avatar.size), ('WEBP', (400, 400)))
		with PILImage.open(profile.banner.path) as banner:
			self.assertEqual(banner.size, (1500, 500))
		page = self.client.get('/users/carol/')
		self.assertContains(page, profile.banner.url)
		self.assertContains(page, profile.avatar.url)

	def test_replacing_and_clearing_delete_old_files(self):
		self.edit(avatar=make_upload())
		profile = self.user.profile.__class__.objects.get(pk=self.user.profile.pk)
		first = profile.avatar.path
		with self.captureOnCommitCallbacks(execute=True):
			self.edit(avatar=make_upload())
		profile.refresh_from_db()
		self.assertNotEqual(profile.avatar.path, first)
		self.assertFalse(Path(first).exists())
		second = profile.avatar.path
		with self.captureOnCommitCallbacks(execute=True):
			self.edit(avatar_clear='on')
		profile.refresh_from_db()
		self.assertFalse(profile.has_custom_avatar)
		self.assertFalse(Path(second).exists())

	def test_bad_file_shows_error_and_keeps_profile(self):
		from django.core.files.uploadedfile import SimpleUploadedFile
		response = self.edit(avatar=SimpleUploadedFile('x.jpg', b'nope', content_type='image/jpeg'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'x.jpg')
		self.assertFalse(Profile.objects.get(user=self.user).has_custom_avatar)

	def test_api_cannot_set_avatar_directly(self):
		response = self.client.patch(
			f'/api/profiles/{self.user.profile.pk}/', {'avatar': 'users/evil.svg'}, content_type='application/json',
		)
		self.assertEqual(response.status_code, 200)
		self.assertFalse(Profile.objects.get(user=self.user).has_custom_avatar)
