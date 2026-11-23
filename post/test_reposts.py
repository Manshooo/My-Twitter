from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import relations
from azzb.testing import ACTIVE
from notifications.models import Notification

from .models import Post
from .services import delete_post, publish_post, toggle_repost

User = get_user_model()
HX = {'HTTP_HX_REQUEST': 'true'}


class RepostTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.ann, cls.bob, cls.cat = (
			User.objects.create_user(name, f'{name}@example.com', **ACTIVE) for name in ('ann', 'bob', 'cat')
		)
		cls.post = publish_post(cls.ann.profile, 'исходный пост')

	def reposts_count(self):
		self.post.refresh_from_db()
		return self.post.reposts_count

	def test_toggle_counts_and_notifies(self):
		self.assertEqual(toggle_repost(self.post, self.bob.profile), (True, 1))
		self.assertTrue(Notification.objects.filter(verb=Notification.Verb.REPOST, post=self.post).exists())
		self.assertEqual(toggle_repost(self.post, self.bob.profile), (False, 0))
		self.assertFalse(Notification.objects.exists())
		# Отменённый репост мягко удалён и не мешает сделать новый.
		self.assertEqual(Post.objects.filter(repost_of=self.post, deleted_at__isnull=False).count(), 1)
		self.assertEqual(toggle_repost(self.post, self.bob.profile), (True, 1))

	def test_repost_hidden_with_original(self):
		toggle_repost(self.post, self.bob.profile)
		self.client.force_login(self.cat)

		def visible_reposts():
			return Post.objects.visible_to(self.cat).filter(is_repost=True)

		self.assertEqual(visible_reposts().count(), 1)
		relations.block(self.cat.profile, self.ann.profile)
		self.assertFalse(visible_reposts().exists())
		relations.unblock(self.cat.profile, self.ann.profile)
		relations.mute(self.cat.profile, self.ann.profile)
		self.assertFalse(visible_reposts().without_muted(self.cat).exists())
		relations.unmute(self.cat.profile, self.ann.profile)
		delete_post(self.post)
		self.assertFalse(visible_reposts().exists())


class QuoteTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.ann = User.objects.create_user('ann', 'ann@example.com', **ACTIVE)
		cls.bob = User.objects.create_user('bob', 'bob@example.com', **ACTIVE)
		cls.post = publish_post(cls.ann.profile, 'исходный пост')

	def test_quote_via_composer(self):
		self.client.force_login(self.bob)
		response = self.client.post(reverse('compose'), {'text': 'мой комментарий', 'quote_of': str(self.post.pk)}, **HX)
		self.assertContains(response, 'quote-card')
		self.assertContains(response, 'исходный пост')
		quote = Post.objects.get(quote_of=self.post)
		self.assertTrue(Notification.objects.filter(verb=Notification.Verb.QUOTE, post=quote).exists())
		self.post.refresh_from_db()
		self.assertEqual(self.post.reposts_count, 1)

	def test_unavailable_quote_shows_placeholder(self):
		quote = publish_post(self.bob.profile, 'цитата', quote_of=self.post)
		delete_post(self.post)
		self.client.force_login(self.bob)
		response = self.client.get(reverse('post', args=[quote.pk]))
		self.assertContains(response, 'Цитируемый пост недоступен')
		self.assertNotContains(response, 'исходный пост')
