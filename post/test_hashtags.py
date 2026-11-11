from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts import relations
from notifications.models import Notification

from .models import Mention
from .services import delete_post, edit_post, publish_post, purge_posts
from .models import Post
from .text import hashtags, linkify, mentions
from azzb.testing import ACTIVE

User = get_user_model()
Verb = Notification.Verb


class ParseTests(SimpleTestCase):
	def test_hashtags(self):
		self.assertEqual(hashtags('#Москва и #москва, #2024, #2024год a#b #snake_case'), ['москва', '2024год', 'snake_case'])

	def test_mentions(self):
		self.assertEqual(mentions('спасибо, @ann. и @bob-, почта me@site.ru, @ann'), ['ann', 'bob'])

	def test_linkify_escapes_and_links(self):
		html = linkify("<b>'#тег'</b> привет @ann.")
		self.assertIn('&lt;b&gt;', html)
		self.assertIn(f'<a class="tag-link" href="{reverse("hashtag", args=["тег"])}">#тег</a>', html)
		self.assertIn('<a class="mention-link" href="/users/ann/">@ann</a>.', html)
		# Экранированный апостроф (&#x27;) не превращается в тег.
		self.assertNotIn('x27</a>', html)


class EntityTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = (
			User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **ACTIVE) for name in ('ann', 'bob', 'cat')
		)

	def mentioned(self, user):
		return Notification.objects.filter(recipient=user.profile, verb=Verb.MENTION)

	def test_publish_creates_tags_mentions_and_notifies(self):
		post = publish_post(self.ann.profile, 'Привет @bob и @nobody и @ann #Тест')
		self.assertEqual([tag.name for tag in post.hashtags.all()], ['тест'])
		self.assertEqual([m.profile for m in post.mentions.all()], [self.bob.profile])
		self.assertEqual(self.mentioned(self.bob).count(), 1)

	def test_reply_author_gets_one_notification(self):
		post = publish_post(self.ann.profile, 'пост')
		publish_post(self.bob.profile, '@ann согласен', reply_to=post)
		self.assertEqual(Notification.objects.filter(recipient=self.ann.profile).count(), 1)
		self.assertFalse(self.mentioned(self.ann).exists())

	def test_edit_syncs_entities(self):
		post = publish_post(self.ann.profile, '@bob #один')
		edit_post(post, '@cat #два')
		self.assertEqual([tag.name for tag in post.hashtags.all()], ['два'])
		self.assertFalse(self.mentioned(self.bob).exists())
		self.assertEqual(self.mentioned(self.cat).count(), 1)
		edit_post(post, '@cat #два и ещё текст')
		self.assertEqual(self.mentioned(self.cat).count(), 1)

	def test_tag_page(self):
		visible = publish_post(self.bob.profile, 'про #Котов')
		reply = publish_post(self.cat.profile, 'и я про #котов', reply_to=visible)
		publish_post(self.cat.profile, 'без тега')
		self.client.force_login(self.ann)
		response = self.client.get(reverse('hashtag', args=['КОТОВ']))
		self.assertEqual(set(response.context['posts']), {visible, reply})
		self.assertContains(response, '#котов')
		relations.mute(self.ann.profile, self.cat.profile)
		self.assertEqual(self.client.get(reverse('hashtag', args=['котов'])).context['posts'], [visible])
		delete_post(visible)
		self.assertEqual(self.client.get(reverse('hashtag', args=['котов'])).context['posts'], [])
		self.client.logout()
		self.assertContains(self.client.get(reverse('hashtag', args=['нет_такого'])), 'Постов с этим тегом пока нет')

	def test_purge_removes_entities(self):
		post = publish_post(self.ann.profile, '@bob #тег')
		delete_post(post)
		purge_posts(Post.objects.filter(pk=post.pk))
		self.assertFalse(post.hashtags.exists())
		self.assertFalse(Mention.objects.exists())

	def test_card_renders_links(self):
		publish_post(self.ann.profile, 'смотри @bob #новости')
		response = self.client.get(reverse('index'))
		self.assertContains(response, 'class="mention-link" href="/users/bob/"')
		self.assertContains(response, 'class="tag-link"')
