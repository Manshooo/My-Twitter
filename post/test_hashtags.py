from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from azzb.testing import ACTIVE
from notifications.models import Notification

from .services import edit_post, publish_post
from .text import linkify

User = get_user_model()
Verb = Notification.Verb


class ParseTests(SimpleTestCase):
	def test_linkify_escapes_and_links(self):
		html = linkify("<b>'#тег'</b> привет @ann.")
		self.assertIn('&lt;b&gt;', html)
		self.assertIn(f'<a class="tag-link" href="{reverse("hashtag", args=["тег"])}">#тег</a>', html)
		self.assertIn('<a class="mention-link" href="/users/ann/">@ann</a>.', html)
		# Экранированный апостроф (&#x27;) не превращается в тег.
		self.assertNotIn('x27</a>', html)

	def test_unsupported_addresses_and_html_remain_text(self):
		text = '<b>javascript:alert(1) ftp://example.org me@example.org</b>'
		self.assertEqual(linkify(text), '&lt;b&gt;javascript:alert(1) ftp://example.org me@example.org&lt;/b&gt;')


class EntityTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.ann, cls.bob, cls.cat = (
			User.objects.create_user(name, f'{name}@example.com', **ACTIVE) for name in ('ann', 'bob', 'cat')
		)

	def mentioned(self, user):
		return Notification.objects.filter(recipient=user.profile, verb=Verb.MENTION)

	def test_publish_creates_tags_mentions_and_notifies(self):
		post = publish_post(self.ann.profile, 'Привет @bob и @nobody и @ann #Тест')
		self.assertEqual([tag.name for tag in post.hashtags.all()], ['тест'])
		self.assertEqual([m.profile for m in post.mentions.all()], [self.bob.profile])
		self.assertEqual(self.mentioned(self.bob).count(), 1)

	def test_edit_syncs_entities(self):
		post = publish_post(self.ann.profile, '@bob #один')
		edit_post(post, '@cat #два')
		self.assertEqual([tag.name for tag in post.hashtags.all()], ['два'])
		self.assertFalse(self.mentioned(self.bob).exists())
		self.assertEqual(self.mentioned(self.cat).count(), 1)
		edit_post(post, '@cat #два и ещё текст')
		self.assertEqual(self.mentioned(self.cat).count(), 1)
