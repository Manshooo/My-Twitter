import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from customUser.forms import CustomUserCreationForm
from customUser.models import FollowThrough
from customUser.templatetags.azzb_ui import ago, plural_ru
from post.models import Post

User = get_user_model()


def make_user(login, **extra):
	return User.objects.create_user(login, f'{login}@example.com', 'pass-12345', **extra)


class FeedPagesTests(TestCase):
	def setUp(self):
		self.alice = make_user('alice')
		Post.objects.create(author=self.alice.profile, text='Привет\nвторая строка')

	def test_guest_sees_feeds_and_signup_card(self):
		for url in ('/', '/hot/'):
			response = self.client.get(url)
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, 'Впервые на AzzB?')
			self.assertContains(response, 'Привет\nвторая строка')
			self.assertNotContains(response, 'id="composer"')

	def test_guest_is_sent_to_login_from_following_feed(self):
		response = self.client.get('/follows-updates/')
		self.assertEqual(response.status_code, 302)
		self.assertIn('/auth/login', response['Location'])

	def test_authed_feed_has_composer_and_own_delete_menu(self):
		self.client.force_login(self.alice)
		response = self.client.get('/')
		self.assertContains(response, 'id="composer"')
		self.assertContains(response, 'data-delete')
		self.assertContains(response, 'data-feed-prepend')

	def test_other_users_post_has_no_delete_menu(self):
		self.client.force_login(make_user('bob'))
		self.assertNotContains(self.client.get('/'), 'data-delete')

	def test_following_feed_empty_state(self):
		self.client.force_login(make_user('bob'))
		self.assertContains(self.client.get('/follows-updates/'), 'Здесь пока тихо')

	def test_theme_cookie_sets_data_theme(self):
		self.client.cookies['theme'] = 'dark'
		self.assertContains(self.client.get('/'), '<html lang="ru" data-theme="dark">')
		self.client.cookies['theme'] = '"><script>'
		self.assertContains(self.client.get('/'), '<html lang="ru">')

	def test_badges(self):
		self.alice.is_staff = True
		self.alice.save()
		self.alice.profile.is_verified = True
		self.alice.profile.save()
		response = self.client.get('/')
		self.assertContains(response, 'aria-label="Подтверждённый аккаунт"')
		self.assertContains(response, 'aria-label="Команда AzzB"')

	def test_custom_404(self):
		response = self.client.get('/no-such-page/')
		self.assertEqual(response.status_code, 404)
		self.assertContains(response, 'Такой страницы нет', status_code=404)


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

	def test_owner_always_sees_own_likes(self):
		self.client.force_login(self.alice)
		response = self.client.get('/users/alice/?tab=likes')
		self.assertContains(response, 'Пост Боба')

	def test_public_likes_visible_to_others(self):
		self.alice.profile.likes_public = True
		self.alice.profile.save()
		self.client.force_login(self.bob)
		self.assertContains(self.client.get('/users/alice/?tab=likes'), 'Пост Боба')

	def test_following_and_followers_tabs(self):
		FollowThrough.objects.create(follower=self.alice.profile, followee=self.bob.profile)
		self.client.force_login(self.alice)
		self.assertContains(self.client.get('/users/alice/?tab=following'), '@bob')
		self.assertContains(self.client.get('/users/bob/?tab=followers'), '@alice')

	def test_follow_redirects_to_safe_next_only(self):
		self.client.force_login(self.alice)
		response = self.client.post('/users/bob/', {'subscribe': '', 'next': '/hot/'})
		self.assertRedirects(response, '/hot/', fetch_redirect_response=False)
		self.assertTrue(FollowThrough.objects.filter(follower=self.alice.profile, followee=self.bob.profile).exists())
		response = self.client.post('/users/bob/', {'unsubscribe': '', 'next': 'https://evil.example/'})
		self.assertRedirects(response, '/users/bob/', fetch_redirect_response=False)

	def test_self_subscribe_does_not_crash(self):
		self.client.force_login(self.alice)
		response = self.client.post('/users/alice/', {'subscribe': ''})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(FollowThrough.objects.exists())

	def test_edit_profile_saves_names_and_likes_privacy(self):
		self.client.force_login(self.alice)
		self.assertEqual(self.client.get('/edit/').status_code, 200)
		response = self.client.post('/edit/', {
			'username': 'Алиса', 'first_name': 'Алиса', 'last_name': 'Иванова',
			'email': 'alice@example.com', 'bio': 'О себе', 'likes_public': 'on',
		})
		self.assertEqual(response.status_code, 302)
		self.alice.refresh_from_db()
		self.assertEqual(self.alice.last_name, 'Иванова')
		self.assertEqual(self.alice.profile.username, 'Алиса')
		self.assertTrue(self.alice.profile.likes_public)


class AuthPagesTests(TestCase):
	def test_auth_pages_render(self):
		for url in ('/auth/login/', '/auth/signup/', '/auth/password_reset/'):
			self.assertEqual(self.client.get(url).status_code, 200, url)

	def signup_form(self, username):
		return CustomUserCreationForm(data={
			'username': username, 'email': 'new@example.com',
			'password1': 'Very-strong-pass-42', 'password2': 'Very-strong-pass-42',
		})

	def test_username_rules(self):
		self.assertTrue(self.signup_form('ok_name.1-x').is_valid())
		for bad in ('bad@name', 'plus+name', 'кириллица', 'a' * 31):
			self.assertFalse(self.signup_form(bad).is_valid(), bad)


class CreatePostLimitsTests(TestCase):
	def setUp(self):
		self.client.force_login(make_user('alice'))

	def post_text(self, text):
		return self.client.post('/api/new-post/', json.dumps({'text': text}), content_type='application/json')

	def test_blank_and_too_long_rejected(self):
		self.assertEqual(self.post_text('   ').status_code, 400)
		self.assertEqual(self.post_text('x' * 501).status_code, 400)
		self.assertEqual(self.post_text('x' * 500).status_code, 200)


class PluralFilterTests(TestCase):
	def test_forms(self):
		forms = 'подписка,подписки,подписок'
		expected = {0: 'подписок', 1: 'подписка', 2: 'подписки', 5: 'подписок', 11: 'подписок', 12: 'подписок', 21: 'подписка', 22: 'подписки', 111: 'подписок'}
		for n, word in expected.items():
			self.assertEqual(plural_ru(n, forms), word, n)


class AgoFilterTests(TestCase):
	def test_units(self):
		now = timezone.now()
		self.assertEqual(ago(now), 'сейчас')
		self.assertEqual(ago(now - timedelta(minutes=5)), '5 мин')
		self.assertEqual(ago(now - timedelta(minutes=5), 'long'), '5 мин назад')
		self.assertEqual(ago(None), '')
		self.assertTrue(ago(now - timedelta(days=400)).endswith(str(timezone.localtime(now - timedelta(days=400)).year)))
