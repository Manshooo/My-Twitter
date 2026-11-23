import json
import re

from allauth.account.models import EmailAddress
from django.core import mail
from django.core.cache import cache
from django.test import TestCase

from accounts.forms import SignupForm
from accounts.models import CustomUser, FollowThrough
from azzb.testing import ACTIVE
from post.models import Post

# Сама модель, а не get_user_model(): так редактор знает про create_user и поля аккаунта.
User = CustomUser


def make_user(login, **extra):
	return User.objects.create_user(login, f'{login}@example.com', 'pass-12345', **ACTIVE, **extra)


class FeedPagesTests(TestCase):
	def setUp(self):
		self.alice = make_user('alice')
		Post.objects.create(author=self.alice.profile, text='Привет\nвторая строка')

	def test_guest_home_is_showcase(self):
		response = self.client.get('/')
		self.assertTemplateUsed(response, 'azzb/guest_home.html')
		self.assertContains(response, '<h1 class="land-kicker">AzzB — социальная сеть коротких постов</h1>', html=True)
		self.assertContains(response, 'Присоединяйтесь к сообществу!')
		self.assertContains(response, 'Привет\nвторая строка')  # популярные посты — живой контент
		self.assertContains(response, 'href="/auth/signup/"')
		self.assertNotContains(response, 'id="composer"')
		self.assertNotContains(response, 'class="tabbar"')
		self.assertContains(response, 'WebSite')

	def test_guest_is_sent_to_login_from_following_feed(self):
		response = self.client.get('/following/')
		self.assertEqual(response.status_code, 302)
		self.assertIn('/auth/login', response['Location'])


class ProfilePageTests(TestCase):
	def setUp(self):
		self.alice = make_user('alice')
		self.bob = make_user('bob')
		self.post = Post.objects.create(author=self.bob.profile, text='Пост Боба')
		self.post.likes.add(self.alice.profile)

	def test_likes_tab_hidden_from_others_by_default(self):
		self.client.force_login(self.bob)
		response = self.client.get('/users/alice/')
		self.assertNotContains(response, '?tab=likes')
		response = self.client.get('/users/alice/?tab=likes')
		self.assertContains(response, 'Лайки скрыты')
		self.assertNotContains(response, 'Пост Боба')

	def test_follow_redirects_to_safe_next_only(self):
		self.client.force_login(self.alice)
		response = self.client.post('/users/bob/', {'subscribe': '', 'next': '/hot/'})
		self.assertRedirects(response, '/hot/', fetch_redirect_response=False)
		self.assertTrue(FollowThrough.objects.filter(follower=self.alice.profile, followee=self.bob.profile).exists())
		response = self.client.post('/users/bob/', {'unsubscribe': '', 'next': 'https://evil.example/'})
		self.assertRedirects(response, '/users/bob/', fetch_redirect_response=False)


class AuthPagesTests(TestCase):
	def test_consents_required_and_recorded(self):
		form = SignupForm(data={
			'username': 'ok', 'email': 'ok@example.com',
			'password1': 'Very-strong-pass-42', 'password2': 'Very-strong-pass-42',
		})
		self.assertFalse(form.is_valid())
		self.assertIn('accept_rules', form.errors)
		self.assertIn('pd_consent', form.errors)
		page = self.client.get('/auth/signup/')
		self.assertContains(page, 'href="/rules/"')
		self.assertContains(page, 'href="/privacy/consent/"')


class EmailVerificationTests(TestCase):
	"""E1: без подтверждённой почты войти нельзя, ссылка из письма подтверждает и впускает."""

	def setUp(self):
		# Лимиты allauth (например, одно письмо подтверждения на адрес за 3 минуты) живут в кэше.
		cache.clear()

	def signup(self, username='newbie', email='newbie@example.com'):
		return self.client.post('/auth/signup/', {
			'username': username, 'email': email,
			'password1': 'Very-strong-pass-42', 'password2': 'Very-strong-pass-42',
			'accept_rules': 'on', 'pd_consent': 'on',
		})

	def test_signup_sends_confirmation_and_does_not_log_in(self):
		response = self.signup()
		self.assertRedirects(response, '/auth/confirm-email/', fetch_redirect_response=False)
		self.assertEqual(len(mail.outbox), 1)
		self.assertIn('newbie@example.com', mail.outbox[0].to)
		self.assertNotIn('_auth_user_id', self.client.session)
		user = User.objects.get(username='newbie')
		self.assertTrue(hasattr(user, 'profile'))
		self.assertIsNotNone(user.terms_accepted_at)
		self.assertIsNotNone(user.pd_consent_at)
		self.assertFalse(EmailAddress.objects.get(user=user).verified)

	def test_unverified_user_cannot_log_in(self):
		self.signup()
		mail.outbox.clear()
		cache.clear()  # иначе повторное письмо упрётся в лимит «одно за 3 минуты»
		response = self.client.post('/auth/login/', {'login': 'newbie', 'password': 'Very-strong-pass-42'})
		self.assertNotIn('_auth_user_id', self.client.session)
		self.assertRedirects(response, '/auth/confirm-email/', fetch_redirect_response=False)
		self.assertEqual(len(mail.outbox), 1, 'письмо отправляется повторно')

	def test_confirmation_link_verifies_and_logs_in(self):
		self.signup()
		link = re.search(r'https?://[^/\s]+(/auth/confirm-email/[^\s]+/)', mail.outbox[0].body).group(1)
		self.assertEqual(self.client.get(link).status_code, 200)
		self.client.post(link)
		self.assertTrue(EmailAddress.objects.get(email='newbie@example.com').verified)
		self.assertEqual(int(self.client.session['_auth_user_id']), User.objects.get(username='newbie').pk)

	def test_duplicate_email_rejected(self):
		user = make_user('alice')
		EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
		response = self.signup(email='Alice@Example.com')
		# Чтобы по форме нельзя было проверить, зарегистрирован ли адрес, allauth отвечает как обычно,
		# а владельцу почты пишет, что аккаунт уже есть.
		self.assertRedirects(response, '/auth/confirm-email/', fetch_redirect_response=False)
		self.assertFalse(User.objects.filter(username='newbie').exists())
		self.assertEqual(mail.outbox[0].to, ['alice@example.com'])

	def test_verified_user_logs_in_by_username_or_email(self):
		user = make_user('alice')
		EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
		for login in ('alice', 'alice@example.com'):
			self.client.logout()
			response = self.client.post('/auth/login/', {'login': login, 'password': 'pass-12345'})
			self.assertRedirects(response, '/', fetch_redirect_response=False)
			self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

	def test_logout_by_post(self):
		self.client.force_login(make_user('alice'))
		self.assertRedirects(self.client.post('/auth/logout/'), '/', fetch_redirect_response=False)
		self.assertNotIn('_auth_user_id', self.client.session)


class CreatePostLimitsTests(TestCase):
	def setUp(self):
		self.client.force_login(make_user('alice'))

	def post_text(self, text):
		return self.client.post('/api/new-post/', json.dumps({'text': text}), content_type='application/json')

	def test_blank_and_too_long_rejected(self):
		self.assertEqual(self.post_text('   ').status_code, 400)
		self.assertEqual(self.post_text('x' * 501).status_code, 400)
		self.assertEqual(self.post_text('x' * 500).status_code, 200)


class RateLimitTests(TestCase):
	"""Лимит публикаций и капча при регистрации."""

	def setUp(self):
		from unittest import mock
		cache.clear()
		# Окна лимитов привязаны к часам: без фиксированного времени тест, начатый в конце минуты,
		# попал бы в два окна и не дошёл бы до лимита.
		clock = mock.patch('azzb.ratelimit._now', return_value=1_800_000_000.0)
		clock.start()
		self.addCleanup(clock.stop)
		self.alice = make_user('alice')
		self.client.force_login(self.alice)

	def test_posting_is_limited_per_minute(self):
		from post.views import POST_RATES
		limit = int(POST_RATES[0].split('/')[0])
		headers = {'HX-Request': 'true'}
		for i in range(limit):
			response = self.client.post('/compose/', {'text': f'пост {i}'}, headers=headers)
			self.assertEqual(response.status_code, 200, i)
		response = self.client.post('/compose/', {'text': 'лишний'}, headers=headers)
		self.assertEqual(response.status_code, 429)
		self.assertIn('errors', json.loads(response.content))
		self.assertEqual(Post.objects.filter(author=self.alice.profile).count(), limit)
		# API считается вместе с composer.
		self.assertEqual(self.client.post('/api/new-post/', {'text': 'через API'}).status_code, 429)

	def test_signup_requires_captcha_when_enabled(self):
		from unittest import mock

		from django.test import override_settings
		self.client.logout()
		data = {
			'username': 'newbie', 'email': 'newbie@example.com',
			'password1': 'Very-strong-pass-42', 'password2': 'Very-strong-pass-42',
			'accept_rules': 'on', 'pd_consent': 'on',
		}
		with override_settings(SMARTCAPTCHA_CLIENT_KEY='client', SMARTCAPTCHA_SERVER_KEY='server'):
			self.assertContains(self.client.get('/auth/signup/'), 'data-sitekey="client"')
			with mock.patch('accounts.captcha.check', return_value=False) as check:
				response = self.client.post('/auth/signup/', data)
			self.assertContains(response, 'не робот')
			self.assertFalse(User.objects.filter(username='newbie').exists())
			with mock.patch('accounts.captcha.check', return_value=True):
				self.client.post('/auth/signup/', {**data, 'smart-token': 'ok'})
			self.assertTrue(User.objects.filter(username='newbie').exists())
		check.assert_called_once()


class DeployTests(TestCase):
	"""Проверка живости для выкладки."""

	def test_healthz(self):
		response = self.client.get('/healthz')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.content, b'ok')
