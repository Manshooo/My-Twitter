from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import relations
from notifications.models import Notification

from .models import Post
from .services import delete_post, publish_post, toggle_like, toggle_repost

User = get_user_model()
HX = {'HTTP_HX_REQUEST': 'true'}


class RepostTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = (
			User.objects.create_user(name, f'{name}@example.com', 'pass-12345') for name in ('ann', 'bob', 'cat')
		)
		self.post = publish_post(self.ann.profile, 'исходный пост')

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

	def test_repost_view_resolves_repost_to_original(self):
		toggle_repost(self.post, self.bob.profile)
		row = Post.objects.get(repost_of=self.post)
		self.client.force_login(self.cat)
		response = self.client.post(reverse('post-repost', args=[row.pk]), **HX)
		self.assertContains(response, 'Отменить репост')
		self.assertEqual(self.reposts_count(), 2)
		self.assertEqual(Post.objects.filter(repost_of=row).count(), 0)
		# Лайк репоста — лайк исходного.
		self.client.post(reverse('post-like', args=[row.pk]), **HX)
		self.assertEqual(self.post.likes.count(), 1)

	def test_feed_shows_repost_card_with_original_stats(self):
		toggle_like(self.post, self.cat.profile)
		toggle_repost(self.post, self.bob.profile)
		self.client.force_login(self.cat)
		response = self.client.get(reverse('index'))
		self.assertContains(response, 'сделал(а) репост')
		self.assertContains(response, 'исходный пост', count=2)
		row = Post.objects.get(repost_of=self.post)
		cards = {post.pk: post for post in response.context['posts']}
		self.assertEqual(cards[row.pk].likes_n, 1)
		self.assertTrue(cards[row.pk].is_liked)
		self.assertFalse(cards[row.pk].is_reposted)
		# «Горячее» без репостов: пост там один раз.
		self.assertEqual([post.pk for post in self.client.get(reverse('hot-news')).context['posts']], [self.post.pk])

	def test_repost_hidden_with_original(self):
		toggle_repost(self.post, self.bob.profile)
		self.client.force_login(self.cat)
		visible = lambda: list(Post.objects.visible_to(self.cat).filter(is_repost=True))
		self.assertEqual(len(visible()), 1)
		relations.block(self.cat.profile, self.ann.profile)
		self.assertEqual(visible(), [])
		relations.unblock(self.cat.profile, self.ann.profile)
		relations.mute(self.cat.profile, self.ann.profile)
		self.assertEqual(list(Post.objects.visible_to(self.cat).without_muted(self.cat).filter(is_repost=True)), [])
		relations.unmute(self.cat.profile, self.ann.profile)
		delete_post(self.post)
		self.assertEqual(visible(), [])

	def test_hidden_post_cannot_be_reposted_or_quoted(self):
		self.post.hidden_at = timezone.now()
		self.post.save()
		self.client.force_login(self.ann)
		self.assertEqual(self.client.post(reverse('post-repost', args=[self.post.pk]), **HX).status_code, 403)
		response = self.client.post(reverse('compose'), {'text': 'цитата', 'quote_of': str(self.post.pk)}, **HX)
		self.assertEqual(response.status_code, 404)

	def test_repost_page_redirects_and_cannot_be_edited(self):
		toggle_repost(self.post, self.bob.profile)
		row = Post.objects.get(repost_of=self.post)
		self.client.force_login(self.bob)
		self.assertRedirects(self.client.get(reverse('post', args=[row.pk])), reverse('post', args=[self.post.pk]))
		response = self.client.post(reverse('compose'), {'edit': str(row.pk), 'text': 'текст'}, **HX)
		self.assertEqual(response.status_code, 403)

	def test_deleting_repost_or_quote_decrements_counter(self):
		toggle_repost(self.post, self.bob.profile)
		quote = publish_post(self.cat.profile, 'цитата', quote_of=self.post)
		self.assertEqual(self.reposts_count(), 2)
		delete_post(quote)
		delete_post(Post.objects.get(repost_of=self.post))
		self.assertEqual(self.reposts_count(), 0)


class QuoteTests(TestCase):
	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', 'pass-12345')
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345')
		self.post = publish_post(self.ann.profile, 'исходный пост')

	def test_quote_via_composer(self):
		self.client.force_login(self.bob)
		response = self.client.post(reverse('compose'), {'text': 'мой комментарий', 'quote_of': str(self.post.pk)}, **HX)
		self.assertContains(response, 'quote-card')
		self.assertContains(response, 'исходный пост')
		quote = Post.objects.get(quote_of=self.post)
		self.assertTrue(Notification.objects.filter(verb=Notification.Verb.QUOTE, post=quote).exists())
		self.post.refresh_from_db()
		self.assertEqual(self.post.reposts_count, 1)

	def test_quote_of_repost_quotes_original(self):
		toggle_repost(self.post, self.bob.profile)
		row = Post.objects.get(repost_of=self.post)
		self.client.force_login(self.bob)
		self.client.post(reverse('compose'), {'text': 'к', 'quote_of': str(row.pk)}, **HX)
		self.assertEqual(Post.objects.get(text='к').quote_of_id, self.post.pk)

	def test_unavailable_quote_shows_placeholder(self):
		quote = publish_post(self.bob.profile, 'цитата', quote_of=self.post)
		delete_post(self.post)
		self.client.force_login(self.bob)
		response = self.client.get(reverse('post', args=[quote.pk]))
		self.assertContains(response, 'Цитируемый пост недоступен')
		self.assertNotContains(response, 'исходный пост')
