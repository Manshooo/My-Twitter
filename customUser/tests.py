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


HTMX = {'HX-Request': 'true'}


class ThemeTests(TestCase):
	"""C1: выбор темы хранится в аккаунте, cookie — для гостей и быстрого первого кадра."""

	def setUp(self):
		self.user = User.objects.create_user('dora', 'dora@example.com', 'pass-12345')

	def html_tag(self, response):
		content = response.content.decode()
		return content[content.index('<html'):content.index('>', content.index('<html')) + 1]

	def test_toggle_saves_theme_to_account_and_cookie(self):
		self.client.force_login(self.user)
		response = self.client.post('/settings/theme/', {'theme': 'dark'}, headers=HTMX)
		self.assertEqual(response.status_code, 204)
		self.assertEqual(response.cookies['theme'].value, 'dark')
		self.user.refresh_from_db()
		self.assertEqual(self.user.theme, 'dark')
		# На другом устройстве (без cookie) страница сразу тёмная.
		self.client.cookies.clear()
		self.client.force_login(self.user)
		self.assertIn('data-theme="dark"', self.html_tag(self.client.get('/')))

	def test_account_choice_beats_cookie(self):
		self.user.theme = 'light'
		self.user.save()
		self.client.force_login(self.user)
		self.client.cookies['theme'] = 'dark'
		self.assertIn('data-theme="light"', self.html_tag(self.client.get('/')))

	def test_guest_uses_cookie_and_system_by_default(self):
		self.assertNotIn('data-theme', self.html_tag(self.client.get('/')))
		self.client.cookies['theme'] = 'dark'
		self.assertIn('data-theme="dark"', self.html_tag(self.client.get('/')))
		self.client.cookies['theme'] = 'purple'
		self.assertNotIn('data-theme', self.html_tag(self.client.get('/')))

	def test_toggle_needs_login_and_valid_theme(self):
		self.assertEqual(self.client.post('/settings/theme/', {'theme': 'dark'}, headers=HTMX).status_code, 401)
		self.client.force_login(self.user)
		self.assertEqual(self.client.post('/settings/theme/', {'theme': 'purple'}, headers=HTMX).status_code, 400)
		self.assertEqual(self.client.get('/settings/theme/').status_code, 405)
		self.user.refresh_from_db()
		self.assertEqual(self.user.theme, '')

	def test_settings_page_saves_theme_and_system_drops_cookie(self):
		self.client.force_login(self.user)
		page = self.client.get('/edit/')
		self.assertContains(page, 'data-theme-choice')
		self.assertContains(page, 'Как в системе')
		data = {'username': 'Дора', 'email': 'dora@example.com', 'first_name': '', 'last_name': '', 'bio': ''}
		response = self.client.post('/edit/', {**data, 'theme': 'dark'})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.cookies['theme'].value, 'dark')
		self.user.refresh_from_db()
		self.assertEqual(self.user.theme, 'dark')
		response = self.client.post('/edit/', {**data, 'theme': ''})
		self.assertEqual(response.cookies['theme'].value, '')  # delete_cookie
		self.user.refresh_from_db()
		self.assertEqual(self.user.theme, '')

	def test_toggle_url_only_for_signed_in(self):
		self.assertNotContains(self.client.get('/'), 'data-theme-url')
		self.client.force_login(self.user)
		self.assertContains(self.client.get('/'), 'data-theme-url="/settings/theme/"')


class BrandTests(TestCase):
	"""C6: знак «Круг» в вёрстке, иконки и превью ссылок."""

	def test_logo_and_icons_on_pages(self):
		for url in ('/', '/auth/login/'):
			response = self.client.get(url)
			self.assertContains(response, 'class="logo-mark"')
			self.assertNotContains(response, '<span class="logo-mark"')
			self.assertContains(response, 'favicon.svg')
			self.assertContains(response, 'apple-touch-icon.png')
			self.assertContains(response, 'site.webmanifest')
			self.assertContains(response, 'og-default.png')

	def test_icon_files_exist(self):
		from django.contrib.staticfiles import finders
		for name in ('favicon.ico', 'favicon.svg', 'apple-touch-icon.png', 'icon-192.png', 'icon-512.png',
				'icon-maskable-512.png', 'site.webmanifest', 'og-default.png'):
			self.assertTrue(finders.find(name), name)
		with PILImage.open(finders.find('favicon.ico')) as ico:
			self.assertEqual(ico.info['sizes'], {(16, 16), (32, 32), (48, 48)})
		with PILImage.open(finders.find('apple-touch-icon.png')) as icon:
			self.assertEqual(icon.size, (180, 180))
		with PILImage.open(finders.find('og-default.png')) as og:
			self.assertEqual(og.size, (1200, 630))
