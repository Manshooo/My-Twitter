from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import CustomUser
from azzb.testing import ACTIVE
from post.models import Post

from .models import Ban, Report

# Сама модель, а не get_user_model(): так редактор знает про create_user и поля аккаунта.
User = CustomUser


def make_user(login):
	return User.objects.create_user(login, f'{login}@example.com', **ACTIVE)


class ModerationTests(TestCase):
	"""E4: жалобы, очередь, скрытие постов, баны."""

	@classmethod
	def setUpTestData(cls):
		cls.alice = make_user('alice')
		cls.bob = make_user('bob')
		cls.mod = make_user('mod')
		cls.mod.groups.add(Group.objects.get(name='Модераторы'))
		cls.post = Post.objects.create(author=cls.bob.profile, text='плохой пост')

	def report_post(self, user=None, reason='spam'):
		self.client.force_login(user or self.alice)
		return self.client.post(f'/p/{self.post.pk}/report/', {'reason': reason, 'comment': 'вот', 'next': '/'})

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

	def test_cannot_ban_superuser_or_self(self):
		boss = User.objects.create_superuser('boss', 'boss@example.com', 'pass-12345')
		self.client.force_login(self.mod)
		for user in (boss, self.mod):
			self.client.post('/moderation/act/', {'action': 'ban', 'profile': user.profile.pk, 'reason': 'x', 'term': '1d'})
		self.assertFalse(Ban.objects.exists())
