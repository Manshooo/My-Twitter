from datetime import date
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from django.contrib.auth.decorators import login_required

from . import search as finder
from .discover import who_to_follow
from .ratelimit import rate_limit
from django.views.generic import TemplateView

from post.models import Post
from post.pagination import PAGE_TEMPLATE, cursor_page, is_load_more, number_page, page_url

FEED_TEMPLATE = "azzb/feed.html"


def render_posts(request, template, context, posts, next_params):
	context.update({
		"posts": posts,
		"next_url": page_url(request, **next_params) if next_params else None,
	})
	return render(request, PAGE_TEMPLATE if is_load_more(request) else template, context)


def index(request):
	queryset = Post.objects.for_feed(request.user).top_level().without_muted(request.user)
	posts, cursor = cursor_page(queryset, request.GET.get("cursor"))
	# Свой новый пост из composer логично показать сверху именно «Свежего».
	context = {"feed": "latest", "prepend": True}
	return render_posts(request, FEED_TEMPLATE, context, posts, cursor and {"cursor": cursor})


def follows_updates(request):
	follows = request.user.profile.follows.all()
	queryset = Post.objects.for_feed(request.user).top_level().without_muted(request.user).filter(author__in=follows)
	posts, cursor = cursor_page(queryset, request.GET.get("cursor"))
	return render_posts(request, FEED_TEMPLATE, {"feed": "following"}, posts, cursor and {"cursor": cursor})


def hot_news(request):
	queryset = (
		# Без репостов (hot() их отбрасывает): иначе пост стоял бы здесь столько раз, сколько его репостили.
		Post.objects.for_feed(request.user).top_level().without_muted(request.user).hot()
	)
	posts, next_page = number_page(queryset, request.GET.get("page"))
	return render_posts(request, FEED_TEMPLATE, {"feed": "hot"}, posts, next_page and {"page": next_page})


SUGGESTIONS_PAGE = 30


@login_required
def suggested_people(request):
	"""Полный список «Кого почитать» (D6): на телефоне правой колонки нет, сюда ведут ссылки."""
	return render(request, 'azzb/who_to_follow.html', {'people': who_to_follow(request.user, SUGGESTIONS_PAGE)})


SEARCH_TABS = ('posts', 'people', 'tags')


@rate_limit('search', '30/m', '600/h', message='Слишком много поисковых запросов. Подождите минуту.')
def search(request):
	"""Поиск с вкладками «Посты / Люди / Теги». Запрос с @ сразу открывает людей, с # — теги."""
	query = finder.clean_query(request.GET.get('q'))
	tab = request.GET.get('tab')
	if tab not in SEARCH_TABS:
		tab = 'people' if query.startswith('@') else 'tags' if query.startswith('#') else 'posts'
	context = {'query': query, 'tab': tab, 'feed': 'search'}
	if not query:
		return render(request, 'azzb/search.html', context)
	if tab == 'posts':
		found, next_page = number_page(finder.posts(request.user, query), request.GET.get('page'))
		return render_posts(request, 'azzb/search.html', context, found, next_page and {'page': next_page})
	context['people'] = finder.people(request.user, query) if tab == 'people' else None
	context['tags'] = finder.tags(query) if tab == 'tags' else None
	return render(request, 'azzb/search.html', context)


def healthz(request):
	"""Жив ли сайт и его база: для проверки после выкладки и healthcheck контейнера."""
	with connection.cursor() as cursor:
		cursor.execute('SELECT 1')
	return HttpResponse('ok', content_type='text/plain')


# Дата текущей редакции правил, политики и согласия (C5, E6). Меняете текст — меняйте и дату.
LEGAL_UPDATED = date(2026, 11, 11)


def legal_page(template):
	return TemplateView.as_view(template_name=template, extra_context={'legal_updated': LEGAL_UPDATED})


def devtools_workspace(request):
	"""Chrome DevTools, открытые на localhost, запрашивают /.well-known/appspecific/com.chrome.devtools.json,
	чтобы связать сайт с папкой проекта (Automatic Workspace Folders): тогда правки CSS и JS прямо
	в DevTools можно сохранять в файлы. Подключается только при DEBUG (azzb/urls.py)."""
	root = settings.BASE_DIR.as_posix()
	# uuid должен быть постоянным для папки, иначе DevTools каждый раз заводит новое рабочее пространство.
	return JsonResponse({'workspace': {'root': root, 'uuid': str(uuid5(NAMESPACE_URL, root))}})
