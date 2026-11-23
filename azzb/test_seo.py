import json
import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from azzb.testing import ACTIVE
from post.models import Image, Post
from post.services import publish_post

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

	def test_guest_sees_header_and_latest_posts(self):
		response = self.client.get('/users/alice/')
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'accounts/profile_guest.html')
		self.assertContains(response, '<meta property="og:title" content="alice (@alice)">', html=True)
		self.assertContains(response, '<meta property="og:type" content="profile">', html=True)
		self.assertContains(response, '<meta property="og:description" content="Пишу про погоду">', html=True)
		# Индексируемый профиль показывает гостю три последних поста (ревизия R2).
		self.assertContains(response, 'Секретов нет')
		self.assertContains(response, 'Присоединяйтесь к обсуждению')
		self.assertNotContains(response, 'class="tabbar"')
		self.assertNotContains(response, 'noindex')
		data = jsonld(response)
		self.assertEqual(data['@type'], 'ProfilePage')
		self.assertEqual(data['mainEntity']['alternateName'], '@alice')

	def test_bio_links_for_guest_and_signed_in_viewer(self):
		owner = make('links', bio='Мой сайт example.ru')
		bio = (
			'<p class="post-text profile-bio">Мой сайт '
			'<a class="url-link" href="https://example.ru" rel="ugc nofollow">example.ru</a></p>'
		)
		self.assertContains(self.client.get('/users/links/'), bio, html=True)
		self.client.force_login(owner)
		self.assertContains(self.client.get('/users/links/'), bio, html=True)

	def test_private_profile_hides_bio_and_is_not_indexed(self):
		make('locked', is_private=True, bio='Только для своих')
		response = self.client.get('/users/locked/')
		self.assertContains(response, 'Закрытый аккаунт в AzzB')
		self.assertNotContains(response, 'Только для своих')
		self.assertContains(response, '<meta name="robots" content="noindex">', html=True)
		self.assertIsNone(jsonld(response))

	def test_opted_out_profile_is_not_indexed(self):
		quiet = make('quiet', search_indexing=False)
		publish_post(quiet.profile, 'тихий пост')
		response = self.client.get('/users/quiet/')
		self.assertNotContains(response, 'тихий пост')
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
		self.assertEqual(data['commentCount'], 0)
		self.assertNotIn('comment', data)
		self.assertNotContains(response, 'noindex')

	def test_post_marks_up_indexable_replies_from_the_guest_page_in_order(self):
		post = publish_post(self.alice.profile, 'Начало обсуждения')
		bob = make('bob')
		first = publish_post(bob.profile, 'Первый ответ </script>', reply_to=post)
		publish_post(make('private', is_private=True).profile, 'Закрытый ответ', reply_to=post)
		publish_post(make('quiet', search_indexing=False).profile, 'Ответ без индексации', reply_to=post)
		hidden = publish_post(bob.profile, 'Скрытый ответ', reply_to=post)
		Post.objects.filter(pk=hidden.pk).update(hidden_at=timezone.now())
		image_reply = Post.objects.create(author=bob.profile, reply_to=post, is_reply=True)
		image = Image.objects.create(post=image_reply, file='posts/reply.webp')
		publish_post(bob.profile, 'Ответ за пределами первой страницы', reply_to=post)

		with patch('post.views.GUEST_REPLIES', 5):
			response = self.client.get(reverse('post', args=[post.pk]))
		self.assertContains(response, 'Ответ без индексации')
		comments = jsonld(response)['comment']
		self.assertEqual([comment['@type'] for comment in comments], ['Comment', 'Comment'])
		self.assertEqual([comment['url'] for comment in comments], [
			'http://testserver' + reverse('post', args=[reply.pk]) for reply in (first, image_reply)
		])
		self.assertEqual(comments[0]['text'], first.text)
		self.assertEqual(comments[0]['author']['url'], 'http://testserver/users/bob/')
		self.assertEqual(comments[0]['datePublished'], first.created_at.isoformat())
		self.assertEqual(comments[1]['image'], ['http://testserver' + image.file.url])

	def test_moderation_hidden_reply_is_omitted_even_for_its_author(self):
		post = publish_post(self.alice.profile, 'Открытый пост')
		bob = make('bob')
		reply = publish_post(bob.profile, 'Виден только автору', reply_to=post)
		Post.objects.filter(pk=reply.pk).update(hidden_at=timezone.now())
		self.client.force_login(bob)

		response = self.client.get(reverse('post', args=[post.pk]))
		self.assertContains(response, reply.text)
		self.assertNotIn('comment', jsonld(response))

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
		robots = self.client.get('/robots.txt').content.decode()
		for name in ('account_login', 'account_signup'):
			with self.subTest(name=name):
				path = reverse(name)
				page = self.client.get(path, {'next': '/users/alice/'})
				self.assertContains(page, f'<link rel="canonical" href="http://testserver{path}">', html=True)
				self.assertContains(page, '<input type="hidden" name="next" value="/users/alice/">', html=True)
				self.assertIn(f'Allow: {path}\n', robots)


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
