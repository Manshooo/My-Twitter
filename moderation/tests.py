from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from post.models import Post

from . import services
from .models import Ban, Reason, Report

# Сама модель, а не get_user_model(): так редактор знает про create_user и поля аккаунта.
User = CustomUser


def make_user(login):
	return User.objects.create_user(login, f'{login}@example.com', 'pass-12345')


class ModerationTests(TestCase):
	"""E4: жалобы, очередь, скрытие постов, баны."""

	def setUp(self):
		self.alice = make_user('alice')
		self.bob = make_user('bob')
		self.mod = make_user('mod')
		self.mod.groups.add(Group.objects.get(name='Модераторы'))
		self.post = Post.objects.create(author=self.bob.profile, text='плохой пост')

	def report_post(self, user=None, reason='spam'):
		self.client.force_login(user or self.alice)
		return self.client.post(f'/p/{self.post.pk}/report/', {'reason': reason, 'comment': 'вот', 'next': '/'})

	def test_report_post_creates_one_open_report_per_reporter(self):
		self.assertEqual(self.client.get(f'/p/{self.post.pk}/report/').status_code, 302, 'гостя — на вход')
		self.client.force_login(self.alice)
		self.assertContains(self.client.get(f'/p/{self.post.pk}/report/'), 'Спам или реклама')
		self.assertRedirects(self.report_post(), '/', fetch_redirect_response=False)
		self.report_post(reason='abuse')
		report = Report.objects.get()
		self.assertEqual(report.reason, Reason.ABUSE)
		self.assertEqual(report.profile, self.bob.profile)

	def test_report_profile_and_not_self(self):
		self.client.force_login(self.alice)
		self.client.post('/users/bob/report/', {'reason': 'impersonation'})
		self.assertTrue(Report.objects.filter(profile=self.bob.profile, post=None).exists())
		self.client.post('/users/alice/report/', {'reason': 'spam'})
		self.assertEqual(Report.objects.count(), 1)

	def test_card_menu_has_report_link(self):
		self.client.force_login(self.alice)
		self.assertContains(self.client.get('/'), f'/p/{self.post.pk}/report/')

	def test_queue_only_for_moderators(self):
		self.report_post()
		self.client.force_login(self.alice)
		self.assertEqual(self.client.get('/moderation/').status_code, 404)
		self.assertNotContains(self.client.get('/'), '/moderation/')
		self.client.force_login(self.mod)
		page = self.client.get('/moderation/')
		self.assertContains(page, 'плохой пост')
		self.assertContains(page, '1 жалоба')
		self.assertContains(self.client.get('/'), '/moderation/')

	def test_hide_post(self):
		self.report_post()
		self.client.force_login(self.mod)
		self.client.post('/moderation/act/', {
			'action': 'hide', 'profile': self.bob.profile.pk, 'post': self.post.pk, 'reason': 'Спам',
		})
		self.post.refresh_from_db()
		self.assertIsNotNone(self.post.hidden_at)
		self.assertEqual(Report.objects.get().status, Report.Status.RESOLVED)
		self.assertNotIn(self.post, Post.objects.visible_to(self.alice))
		self.assertNotIn(self.post, Post.objects.visible_to(None))
		# Автор видит свой скрытый пост с пометкой.
		self.client.force_login(self.bob)
		self.assertContains(self.client.get('/users/bob/'), 'Скрыт модератором: Спам')

	def test_hide_requires_reason(self):
		self.report_post()
		self.client.force_login(self.mod)
		self.client.post('/moderation/act/', {'action': 'hide', 'profile': self.bob.profile.pk, 'post': self.post.pk})
		self.post.refresh_from_db()
		self.assertIsNone(self.post.hidden_at)

	def test_dismiss(self):
		self.report_post()
		self.report_post(user=self.mod)
		self.client.force_login(self.mod)
		self.client.post('/moderation/act/', {'action': 'dismiss', 'profile': self.bob.profile.pk, 'post': self.post.pk})
		self.assertFalse(Report.objects.filter(status=Report.Status.OPEN).exists())
		self.assertIn(self.post, Post.objects.visible_to(self.alice))

	def test_temporary_ban(self):
		self.report_post()
		self.client.force_login(self.mod)
		self.client.post('/moderation/act/', {
			'action': 'ban', 'profile': self.bob.profile.pk, 'reason': 'Спам', 'term': '7d',
		})
		self.bob.refresh_from_db()
		self.assertTrue(self.bob.is_banned)
		self.assertFalse(self.bob.ban_is_permanent)
		self.assertEqual(Ban.objects.get().created_by, self.mod)
		self.assertFalse(Report.objects.filter(status=Report.Status.OPEN).exists())
		# Посты забаненного не видит никто.
		self.assertNotIn(self.post, Post.objects.visible_to(self.alice))
		self.client.force_login(self.alice)
		self.assertContains(self.client.get('/users/bob/'), 'Аккаунт заблокирован')
		# Сам забаненный видит только экран бана, но может прочитать правила и выйти.
		self.client.force_login(self.bob)
		page = self.client.get('/')
		self.assertEqual(page.status_code, 403)
		self.assertContains(page, 'Спам', status_code=403)
		self.assertEqual(self.client.get('/compose/').status_code, 403)
		self.assertEqual(self.client.get('/rules/').status_code, 200)
		self.assertEqual(self.client.get('/settings/account/').status_code, 200)
		self.assertRedirects(self.client.post('/auth/logout/'), '/', fetch_redirect_response=False)

	def test_ban_expires_by_itself(self):
		services.ban_user(self.mod, self.bob, 'Спам', '1d')
		User.objects.filter(pk=self.bob.pk).update(banned_until=timezone.now() - timedelta(minutes=1))
		self.bob.refresh_from_db()
		self.assertFalse(self.bob.is_banned)
		self.assertIn(self.post, Post.objects.visible_to(self.alice))

	def test_permanent_ban_and_unban(self):
		services.ban_user(self.mod, self.bob, 'Угрозы', 'forever')
		self.bob.refresh_from_db()
		self.assertTrue(self.bob.ban_is_permanent)
		self.client.force_login(self.mod)
		self.client.post('/moderation/unban/bob/')
		self.bob.refresh_from_db()
		self.assertFalse(self.bob.is_banned)
		self.assertIsNotNone(Ban.objects.get().lifted_at)

	def test_cannot_ban_superuser_or_self(self):
		boss = User.objects.create_superuser('boss', 'boss@example.com', 'pass-12345')
		self.client.force_login(self.mod)
		for user in (boss, self.mod):
			self.client.post('/moderation/act/', {'action': 'ban', 'profile': user.profile.pk, 'reason': 'x', 'term': '1d'})
		self.assertFalse(Ban.objects.exists())

	def test_report_rate_limit(self):
		self.client.force_login(self.alice)
		for i in range(11):
			user = make_user(f'spam{i}')
			response = self.client.post(f'/users/{user.username}/report/', {'reason': 'spam'})
		self.assertEqual(response.status_code, 429)
		self.assertEqual(Report.objects.count(), 10)
