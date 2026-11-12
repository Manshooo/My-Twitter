import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from post.models import Post
from post.services import publish_post
from azzb.testing import ACTIVE

User = get_user_model()


def make(name, **profile):
	user = User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **ACTIVE)
	if profile:
		for field, value in profile.items():
			setattr(user.profile, field, value)
		user.profile.save()
	return user


def jsonld(response):
	match = re.search(r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.S)
	return json.loads(match.group(1)) if match else None


class RobotsTests(TestCase):
	def test_robots_closes_private_sections_and_points_to_sitemap(self):
		response = self.client.get('/robots.txt')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
		body = response.content.decode()
		for section in ('/messages/', '/notifications/', '/search/', '/settings/', '/api/', '/auth/'):
			self.assertIn(f'Disallow: {section}\n', body)
		self.assertIn('Sitemap: http://testserver/sitemap.xml', body)


class SitemapTests(TestCase):
	def setUp(self):
		self.alice = make('alice')
		self.hidden = make('hidden', search_indexing=False)
		self.locked = make('locked', is_private=True)
		self.banned = make('banned')
		self.banned.banned_until = timezone.now() + timedelta(days=1)
		self.banned.save()
		self.visible = publish_post(self.alice.profile, 'Открытый #погода')
		self.opted_out = publish_post(self.hidden.profile, 'Без поисковиков #тайна')
		self.private = publish_post(self.locked.profile, 'Только подписчикам #секрет')

	def section(self, name):
		response = self.client.get(reverse('sitemap-section', kwargs={'section': name}))
		self.assertEqual(response.status_code, 200)
		return response.content.decode()

	def test_index_lists_sections(self):
		body = self.client.get('/sitemap.xml').content.decode()
		for name in ('pages', 'posts', 'people', 'tags'):
			self.assertIn(f'http://testserver/sitemap-{name}.xml', body)

	def test_only_indexable_posts_people_and_tags(self):
		posts = self.section('posts')
		self.assertIn(reverse('post', args=[self.visible.pk]), posts)
		self.assertNotIn(reverse('post', args=[self.opted_out.pk]), posts)
		self.assertNotIn(reverse('post', args=[self.private.pk]), posts)

		people = self.section('people')
		self.assertIn('/users/alice/', people)
		for name in ('hidden', 'locked', 'banned'):
			self.assertNotIn(f'/users/{name}/', people)

		tags = self.section('tags')
		self.assertIn(reverse('hashtag', args=['погода']), tags)
		self.assertNotIn(reverse('hashtag', args=['тайна']), tags)
		self.assertNotIn(reverse('hashtag', args=['секрет']), tags)


class GuestProfileTests(TestCase):
	def setUp(self):
		self.alice = make('alice', bio='Пишу про погоду')
		publish_post(self.alice.profile, 'Секретов нет, но только после входа')

	def test_guest_sees_card_with_preview_but_no_posts(self):
		response = self.client.get('/users/alice/')
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'accounts/profile_guest.html')
		self.assertContains(response, '<meta property="og:title" content="alice (@alice)">', html=True)
		self.assertContains(response, '<meta property="og:type" content="profile">', html=True)
		self.assertContains(response, '<meta property="og:description" content="Пишу про погоду">', html=True)
		self.assertNotContains(response, 'Секретов нет')
		self.assertNotContains(response, 'noindex')
		data = jsonld(response)
		self.assertEqual(data['@type'], 'ProfilePage')
		self.assertEqual(data['mainEntity']['alternateName'], '@alice')

	def test_private_profile_hides_bio_and_is_not_indexed(self):
		make('locked', is_private=True, bio='Только для своих')
		response = self.client.get('/users/locked/')
		self.assertContains(response, 'Закрытый аккаунт в AzzB')
		self.assertNotContains(response, 'Только для своих')
		self.assertContains(response, '<meta name="robots" content="noindex">', html=True)
		self.assertIsNone(jsonld(response))

	def test_opted_out_profile_is_not_indexed(self):
		make('quiet', search_indexing=False)
		response = self.client.get('/users/quiet/')
		self.assertContains(response, '<meta name="robots" content="noindex">', html=True)
		self.assertIsNone(jsonld(response))

	def test_guest_actions_and_pages_need_login(self):
		response = self.client.get('/users/alice/?cursor=x', headers={'HX-Request': 'true'})
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse('account_login'), response['Location'])
		response = self.client.post('/users/alice/', {'subscribe': ''})
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse('account_login'), response['Location'])

	def test_member_still_gets_full_profile(self):
		self.client.force_login(make('bob'))
		response = self.client.get('/users/alice/')
		self.assertTemplateUsed(response, 'accounts/profile.html')
		self.assertContains(response, 'Секретов нет')


class PostMetaTests(TestCase):
	def setUp(self):
		self.alice = make('alice')

	def test_post_has_og_and_social_media_posting(self):
		post = publish_post(self.alice.profile, 'Текст </script><b>поста</b>')
		response = self.client.get(reverse('post', args=[post.pk]))
		self.assertContains(response, '<meta property="og:type" content="article">', html=True)
		self.assertContains(response, '<meta property="og:title" content="alice (@alice)">', html=True)
		url = f'http://testserver/p/{post.pk}/'
		self.assertContains(response, f'<link rel="canonical" href="{url}">', html=True)
		self.assertContains(response, f'<meta property="og:url" content="{url}">', html=True)
		data = jsonld(response)
		self.assertEqual(data['@type'], 'SocialMediaPosting')
		self.assertEqual(data['text'], 'Текст </script><b>поста</b>')
		self.assertEqual(data['author']['url'], 'http://testserver/users/alice/')
		self.assertNotContains(response, 'noindex')

	def test_opted_out_author_posts_are_not_indexed(self):
		quiet = make('quiet', search_indexing=False)
		post = Post.objects.create(author=quiet.profile, text='Не ищите меня')
		response = self.client.get(reverse('post', args=[post.pk]))
		self.assertContains(response, '<meta name="robots" content="noindex">', html=True)
		self.assertIsNone(jsonld(response))
		self.assertContains(response, 'property="og:title"')

	def test_home_describes_site(self):
		response = self.client.get('/')
		self.assertEqual(jsonld(response)['@type'], 'WebSite')
		self.assertContains(response, '<meta name="twitter:card" content="summary_large_image">', html=True)
		self.assertContains(response, '<meta property="og:locale" content="ru_RU">', html=True)
		self.assertContains(response, '<title>AzzB</title>', html=True)
		self.assertNotContains(response, 'разработке')

	def test_auth_pages_have_canonical_and_are_allowed(self):
		page = self.client.get(reverse('account_login') + '?next=/hot/')
		self.assertContains(page, '<link rel="canonical" href="http://testserver/auth/login/">', html=True)
		self.assertIn('Allow: /auth/signup/', self.client.get('/robots.txt').content.decode())


class SeoTagsTests(SimpleTestCase):
	def render(self, source, **context):
		request = RequestFactory().get('/p/x/?cursor=abc')
		return Template('{% load seo %}' + source).render(Context({'request': request, **context}))

	def test_absolute_keeps_full_urls_from_storage(self):
		self.assertEqual(self.render('{% absolute url %}', url='/media/a.webp'), 'http://testserver/media/a.webp')
		self.assertEqual(self.render('{% absolute url %}', url='https://azzb.ru/media/a.webp'), 'https://azzb.ru/media/a.webp')

	def test_canonical_drops_query(self):
		self.assertEqual(self.render('{% canonical %}'), 'http://testserver/p/x/')

	def test_capture_is_not_escaped_twice(self):
		self.assertEqual(self.render('{% capture as t %} {{ v }} {% endcapture %}[{{ t }}]', v='a & b'), '[a &amp; b]')


class SearchIndexingSettingTests(TestCase):
	def test_profile_edit_saves_setting(self):
		bob = make('bob')
		self.client.force_login(bob)
		self.client.post(reverse('edit-profile'), {'username': 'bob', 'theme': ''})
		bob.profile.refresh_from_db()
		self.assertFalse(bob.profile.search_indexing)
		self.client.post(reverse('edit-profile'), {'username': 'bob', 'theme': '', 'search_indexing': 'on'})
		bob.profile.refresh_from_db()
		self.assertTrue(bob.profile.search_indexing)
