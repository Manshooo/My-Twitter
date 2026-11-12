"""sitemap.xml: только то, что видно гостю и что автор разрешил индексировать (Profile.search_indexing)."""
from django.contrib.sitemaps import Sitemap
from django.db.models import Exists, OuterRef
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from post.models import Hashtag, Post


def _indexable_posts():
	# visible_to(None) уже убирает закрытые аккаунты, забаненных, удалённое и скрытое.
	return Post.objects.visible_to(None).filter(is_repost=False, author__search_indexing=True)


class PagesSitemap(Sitemap):
	def items(self):
		return ['index', 'rules', 'privacy', 'cookies']

	def location(self, item):
		return reverse(item)


class PostsSitemap(Sitemap):
	limit = 10000

	def items(self):
		return _indexable_posts().order_by('-created_at', '-id').only('id', 'created_at', 'edited_at')

	def location(self, item):
		return reverse('post', args=[item.pk])

	def lastmod(self, item):
		return item.edited_at or item.created_at


class ProfilesSitemap(Sitemap):
	limit = 10000

	def items(self):
		return (
			Profile.objects.public().filter(search_indexing=True, is_private=False)
			.exclude(user__banned_until__gt=timezone.now())
			.select_related('user').only('user__username').order_by('pk')
		)

	def location(self, item):
		return reverse('profile', kwargs={'slug': item.user.username})


class TagsSitemap(Sitemap):
	limit = 10000

	def items(self):
		used = _indexable_posts().filter(hashtags=OuterRef('pk'))
		return Hashtag.objects.filter(Exists(used)).only('name').order_by('name')

	def location(self, item):
		return reverse('hashtag', args=[item.name])


SITEMAPS = {'pages': PagesSitemap, 'posts': PostsSitemap, 'people': ProfilesSitemap, 'tags': TagsSitemap}
