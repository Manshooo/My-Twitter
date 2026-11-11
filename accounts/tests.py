from datetime import timedelta

from allauth.account.models import EmailAddress
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils.timezone import now
from PIL import Image as PILImage

from post.tests import MEDIA_ROOT, make_upload

from .middleware import SetLastVisitMiddleware
from .models import CustomUser, FollowThrough, Profile
from azzb.testing import ACTIVE

# Сама модель, а не get_user_model(): так редактор знает про create_user и поля аккаунта.
User = CustomUser


class ProfileSignalTests(TestCase):
	def test_user_gets_exactly_one_profile_without_self_follow(self):
		user = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.assertEqual(Profile.objects.filter(user=user).count(), 1)
		self.assertEqual(user.profile.username, 'alice')
		self.assertFalse(user.profile.follows.exists())


class PublicProfilesTests(TestCase):
	"""Profile.objects.public: кто ни разу не входил (брошенная регистрация, бот), не виден другим."""

	def setUp(self):
		self.viewer = User.objects.create_user('viewer', 'viewer@example.com', 'pass-12345', **ACTIVE)
		self.client.force_login(self.viewer)
		# Почта не подтверждена — войти не мог.
		self.pending = User.objects.create_user('pending', 'pending@example.com', 'pass-12345')
		EmailAddress.objects.create(user=self.pending, email='pending@example.com', verified=False, primary=True)
		self.confirmed = User.objects.create_user('confirmed', 'confirmed@example.com', 'pass-12345', **ACTIVE)
		EmailAddress.objects.create(user=self.confirmed, email='confirmed@example.com', verified=True, primary=True)
		# Бот: несколько регистраций с одной почтой разом — аккаунт без записи об адресе, не входил.
		self.bot = User.objects.create_user('jimqilqoht', 'bot@example.com', 'pass-12345')
		# createsuperuser: адресов нет, не входил, но staff.
		self.admin = User.objects.create_user('admin', 'admin@example.com', 'pass-12345', is_staff=True)

	def test_public_shows_only_who_logged_in_and_staff(self):
		logins = set(Profile.objects.public().values_list('user__username', flat=True))
		self.assertEqual(logins, {'viewer', 'confirmed', 'admin'})

	def test_confirmed_but_never_logged_in_appears_after_first_login(self):
		EmailAddress.objects.filter(user=self.pending).update(verified=True)
		self.assertFalse(Profile.objects.public().filter(pk=self.pending.profile.pk).exists())
		self.client.force_login(self.pending)
		self.assertTrue(Profile.objects.public().filter(pk=self.pending.profile.pk).exists())

	def test_changing_email_keeps_profile_visible(self):
		EmailAddress.objects.create(user=self.confirmed, email='new@example.com', verified=False, primary=False)
		self.assertTrue(Profile.objects.public().filter(pk=self.confirmed.profile.pk).exists())

	def test_unconfirmed_profile_page_lists_and_counts(self):
		self.assertEqual(self.client.get('/users/pending/').status_code, 404)
		self.assertEqual(self.client.get('/users/confirmed/').status_code, 200)
		FollowThrough.objects.create(follower=self.pending.profile, followee=self.confirmed.profile)
		FollowThrough.objects.create(follower=self.viewer.profile, followee=self.confirmed.profile)
		response = self.client.get('/users/confirmed/?tab=followers')
		self.assertEqual(response.context['followers_count'], 1)
		self.assertEqual([p.user.username for p in response.context['people']], ['viewer'])

	def test_who_to_follow_skips_unconfirmed(self):
		response = self.client.get('/')
		suggested = {p.user.username for p in response.context['who_to_follow']}
		self.assertNotIn('pending', suggested)
		self.assertIn('confirmed', suggested)


class SetLastVisitMiddlewareTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
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
		self.user = User.objects.create_user('carol', 'carol@example.com', 'pass-12345', **ACTIVE)
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
		with profile.avatar.open('rb'), PILImage.open(profile.avatar) as avatar:
			self.assertEqual((avatar.format, avatar.size), ('WEBP', (400, 400)))
		with profile.banner.open('rb'), PILImage.open(profile.banner) as banner:
			self.assertEqual(banner.size, (1500, 500))
		page = self.client.get('/users/carol/')
		self.assertContains(page, profile.banner.url)
		self.assertContains(page, profile.avatar.url)

	def test_replacing_and_clearing_delete_old_files(self):
		self.edit(avatar=make_upload())
		profile = self.user.profile.__class__.objects.get(pk=self.user.profile.pk)
		storage, first = profile.avatar.storage, profile.avatar.name
		with self.captureOnCommitCallbacks(execute=True):
			self.edit(avatar=make_upload())
		profile.refresh_from_db()
		self.assertNotEqual(profile.avatar.name, first)
		self.assertFalse(storage.exists(first))
		second = profile.avatar.name
		with self.captureOnCommitCallbacks(execute=True):
			self.edit(avatar_clear='on')
		profile.refresh_from_db()
		self.assertFalse(profile.has_custom_avatar)
		self.assertFalse(storage.exists(second))

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
		self.user = User.objects.create_user('dora', 'dora@example.com', 'pass-12345', **ACTIVE)

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


class BlockMuteTests(TestCase):
	"""E3: блокировка скрывает посты в обе стороны и снимает подписки; заглушение — только ленты."""

	def setUp(self):
		from post.models import Post
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.alice_post = Post.objects.create(author=self.alice.profile, text='пост Алисы')
		self.bob_post = Post.objects.create(author=self.bob.profile, text='пост Боба')
		self.client.force_login(self.alice)

	def act(self, action, username='bob', **extra):
		return self.client.post(f'/users/{username}/', {action: '', **extra})

	def test_block_hides_posts_both_ways_and_removes_follows(self):
		from post.models import Post

		from .models import FollowThrough
		FollowThrough.objects.create(follower=self.alice.profile, followee=self.bob.profile)
		FollowThrough.objects.create(follower=self.bob.profile, followee=self.alice.profile)
		self.act('block')
		self.assertFalse(FollowThrough.objects.exists())
		self.assertNotIn(self.bob_post, Post.objects.visible_to(self.alice))
		self.assertNotIn(self.alice_post, Post.objects.visible_to(self.bob))
		self.assertIn(self.bob_post, Post.objects.visible_to(None))
		self.assertNotContains(self.client.get('/'), 'пост Боба')
		page = self.client.get(f'/p/{self.bob_post.pk}/')  # по прямой ссылке — заглушка
		self.assertContains(page, 'Пост недоступен')
		self.assertNotContains(page, 'пост Боба')

	def test_blocked_user_cannot_follow_like_or_reply(self):
		from .models import Block, FollowThrough
		Block.objects.create(blocker=self.alice.profile, blocked=self.bob.profile)
		self.client.force_login(self.bob)
		self.act('subscribe', username='alice')
		self.assertFalse(FollowThrough.objects.exists())
		self.assertEqual(self.client.post(f'/p/{self.alice_post.pk}/like/').status_code, 404)
		response = self.client.post('/compose/', {'text': 'ответ', 'reply_to': str(self.alice_post.pk)}, headers={'HX-Request': 'true'})
		self.assertEqual(response.status_code, 404)
		page = self.client.get('/users/alice/')
		self.assertContains(page, 'ограничил(а) доступ')
		self.assertNotContains(page, 'name="subscribe"')

	def test_unblock(self):
		from .models import Block
		self.act('block')
		page = self.client.get('/users/bob/')
		self.assertContains(page, 'Вы заблокировали @bob')
		self.assertContains(page, 'name="unblock"')
		self.act('unblock')
		self.assertFalse(Block.objects.exists())
		self.assertContains(self.client.get('/'), 'пост Боба')

	def test_mute_hides_from_feeds_only(self):
		from .models import FollowThrough
		FollowThrough.objects.create(follower=self.alice.profile, followee=self.bob.profile)
		response = self.act('mute', next='/hot/')
		self.assertRedirects(response, '/hot/', fetch_redirect_response=False)
		for url in ('/', '/hot/', '/follows-updates/'):
			self.assertNotContains(self.client.get(url), 'пост Боба', msg_prefix=url)
		self.assertContains(self.client.get('/users/bob/'), 'пост Боба')
		self.assertEqual(self.client.get(f'/p/{self.bob_post.pk}/').status_code, 200)
		self.assertTrue(FollowThrough.objects.exists(), 'подписка остаётся')
		self.act('unmute')
		self.assertContains(self.client.get('/'), 'пост Боба')

	def test_card_menu_offers_block_for_others_only(self):
		page = self.client.get('/')
		self.assertContains(page, 'Заблокировать @bob')
		self.assertNotContains(page, 'Заблокировать @alice')

	def test_cannot_block_self(self):
		from .models import Block
		self.act('block', username='alice')
		self.assertFalse(Block.objects.exists())


class BlockedAccountsPageTests(TestCase):
	def test_lists_and_unblocks(self):
		from .models import Block, Mute
		alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		carol = User.objects.create_user('carol', 'carol@example.com', 'pass-12345', **ACTIVE)
		Block.objects.create(blocker=alice.profile, blocked=bob.profile)
		Mute.objects.create(muter=alice.profile, muted=carol.profile)
		self.client.force_login(alice)
		page = self.client.get('/settings/blocked/')
		self.assertContains(page, '@bob')
		self.assertContains(page, '@carol')
		response = self.client.post('/users/bob/', {'unblock': '', 'next': '/settings/blocked/'})
		self.assertRedirects(response, '/settings/blocked/', fetch_redirect_response=False)
		self.assertFalse(Block.objects.exists())


class LegalPagesTests(TestCase):
	"""C5: правила и документы открыты всем, ссылки — в подвале."""

	def test_pages_render_for_guests(self):
		for url in ('/rules/', '/privacy/', '/privacy/consent/'):
			response = self.client.get(url)
			self.assertEqual(response.status_code, 200, url)
			self.assertContains(response, 'Редакция от')
		self.assertContains(self.client.get('/'), 'href="/rules/"')
		self.assertContains(self.client.get('/auth/login/'), 'href="/privacy/"')


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AccountDataTests(TestCase):
	"""E6: выгрузка своих данных и удаление аккаунта."""

	def setUp(self):
		from post.models import Post
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.post = Post.objects.create(author=self.alice.profile, text='мой пост')
		Post.objects.create(author=self.bob.profile, text='пост Боба')
		self.client.force_login(self.alice)

	def test_export_zip(self):
		import io
		import json
		import zipfile
		self.client.post('/compose/', {'text': 'с картинкой', 'images': make_upload()}, headers={'HX-Request': 'true'})
		self.assertEqual(self.client.get('/settings/account/').status_code, 200)
		response = self.client.post('/settings/account/export/')
		self.assertEqual(response.status_code, 200)
		self.assertIn('attachment', response['Content-Disposition'])
		bundle = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
		data = json.loads(bundle.read('data.json'))
		self.assertEqual(data['account']['email'], 'alice@example.com')
		texts = [post['text'] for post in data['posts']]
		self.assertIn('мой пост', texts)
		self.assertNotIn('пост Боба', texts)
		image = next(post for post in data['posts'] if post['images'])['images'][0]['file']
		self.assertIn(image, bundle.namelist())

	def test_delete_requires_password(self):
		response = self.client.post('/settings/account/delete/', {'confirm': 'wrong'})
		self.assertEqual(response.status_code, 400)
		self.assertContains(response, 'Неверный пароль', status_code=400)
		self.assertTrue(User.objects.filter(username='alice').exists())

	def test_delete_account(self):
		# Аккаунт сразу отключается и пропадает, а данные хранятся полгода (azzb/retention.py).
		from post.models import Post
		response = self.client.post('/settings/account/delete/', {'confirm': 'pass-12345'})
		self.assertRedirects(response, '/', fetch_redirect_response=False)
		self.assertNotIn('_auth_user_id', self.client.session)
		alice = User.objects.get(username='alice')
		self.assertFalse(alice.is_active)
		self.assertIsNotNone(alice.deleted_at)
		self.assertIsNotNone(Post.objects.get(text='мой пост').deleted_at)
		self.assertIsNone(Post.objects.get(text='пост Боба').deleted_at)
		self.client.force_login(User.objects.get(username='bob'))
		self.assertEqual(self.client.get('/users/alice/').status_code, 404)
		self.assertNotContains(self.client.get('/'), 'мой пост')
