from django.contrib.auth import get_user_model
from django.test import TestCase

from post.services import publish_post
from azzb.testing import ACTIVE

User = get_user_model()


class NavigationTests(TestCase):
	"""R2-B-Nav: шапка телефона, плавающая кнопка, таб-бар."""

	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.post = publish_post(self.bob.profile, 'привет')
		self.client.force_login(self.ann)

	def test_fab_only_on_home_and_own_profile(self):
		for url, shown in (('/', True), ('/following/', True), ('/users/ann/', True), ('/users/bob/', False),
				(f'/p/{self.post.pk}/', False), ('/notifications/', False)):
			with self.subTest(url=url):
				self.assertEqual('class="fab"' in self.client.get(url).content.decode(), shown)

	def test_phone_header_title_on_inner_pages(self):
		self.assertNotContains(self.client.get('/'), 'class="topbar-title')
		self.assertContains(self.client.get(f'/p/{self.post.pk}/'), '<span class="topbar-title clip1">Пост</span>')
		self.assertContains(self.client.get('/notifications/'), '<span class="topbar-title clip1">Уведомления</span>')

	def test_tabbar_has_search_not_hot(self):
		html = self.client.get('/').content.decode()
		tabbar = html[html.index('class="tabbar"'):]
		self.assertIn('href="/search/"', tabbar[:2000])
		self.assertNotIn('/hot/', html)
