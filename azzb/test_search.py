from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import relations
from post.services import delete_post, edit_post, publish_post, toggle_repost
from azzb.testing import ACTIVE

User = get_user_model()


class SearchTests(TestCase):
	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob_builder', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.bob.profile.username = 'Боб Строитель'
		self.bob.profile.save()
		self.client.force_login(self.ann)

	def search(self, q, **params):
		return self.client.get(reverse('search'), {'q': q, **params})

	def test_posts_russian_morphology_and_operators(self):
		post = publish_post(self.bob.profile, 'Проверяю уведомления на сайте')
		publish_post(self.bob.profile, 'Уведомления и реклама')
		self.assertEqual(self.search('уведомлений -реклама').context['posts'], [post])
		self.assertEqual(self.search('"на сайте"').context['posts'], [post])

	def test_posts_follow_visibility_and_skip_reposts(self):
		post = publish_post(self.bob.profile, 'секретный рецепт')
		toggle_repost(post, self.ann.profile)
		self.assertEqual(self.search('рецепт').context['posts'], [post])
		relations.mute(self.ann.profile, self.bob.profile)
		self.assertEqual(self.search('рецепт').context['posts'], [])
		relations.unmute(self.ann.profile, self.bob.profile)
		edit_post(post, 'другой текст')
		self.assertEqual(self.search('рецепт').context['posts'], [])
		delete_post(post)
		self.assertEqual(self.search('текст').context['posts'], [])

	def test_people_by_login_name_and_typo(self):
		for query in ('@bob', 'строитель', 'bob_bulder'):
			self.assertEqual(list(self.search(query, tab='people').context['people']), [self.bob.profile], query)
		self.bob.banned_until = timezone.now() + timedelta(days=1)
		self.bob.save()
		self.assertEqual(list(self.search('bob', tab='people').context['people']), [])
		self.bob.banned_until = None
		self.bob.save()
		relations.block(self.bob.profile, self.ann.profile)
		self.assertEqual(list(self.search('bob', tab='people').context['people']), [])

	def test_tags_by_prefix_and_popularity(self):
		publish_post(self.bob.profile, '#котики')
		publish_post(self.bob.profile, '#котики и #коты')
		removed = publish_post(self.bob.profile, '#котлеты')
		delete_post(removed)
		response = self.search('#кот')
		self.assertEqual(response.context['tab'], 'tags')
		self.assertEqual([(tag.name, tag.uses) for tag in response.context['tags']], [('котики', 2), ('коты', 1)])

	def test_tab_guess_empty_query_and_guest(self):
		self.assertEqual(self.search('@ann').context['tab'], 'people')
		self.assertContains(self.search(''), 'Что ищем?')
		self.client.logout()
		publish_post(self.bob.profile, 'открытый пост')
		self.assertEqual(len(self.search('открытый').context['posts']), 1)
		self.assertContains(self.search('ничегонет'), 'Ничего не нашлось')
