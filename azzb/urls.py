from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.sitemaps import views as sitemap_views
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.account import account_settings, delete_account, end_sessions, export_data
from accounts.views import (
	ChangeProfileView, UserProfileDetailView, answer_follow_request, blocked_accounts, consent_update, follow_requests,
	set_theme,
)
from moderation.views import report_post, report_profile
from tracking import views as tracking_views
from post.views import (
	bookmark_post, bookmarks, compose, delete_post, hashtag, like_post, pin_post, post_conversation, post_detail,
	repost_post, vote_poll,
)

from .sitemaps import SITEMAPS
from .views import (
	devtools_workspace, following, healthz, index, legal_page, offline, robots_txt, search, service_worker,
	set_feed_sort, suggested_people,
)

urlpatterns = [
	path('', index, name='index'),
	path('healthz', healthz, name='healthz'),
	path('robots.txt', robots_txt, name='robots'),
	path('sw.js', service_worker, name='service-worker'),
	path('offline/', offline, name='offline'),
	path('sitemap.xml', sitemap_views.index, {'sitemaps': SITEMAPS, 'sitemap_url_name': 'sitemap-section'}, name='sitemap'),
	path('sitemap-<section>.xml', sitemap_views.sitemap, {'sitemaps': SITEMAPS}, name='sitemap-section'),
	# «Горячее» стало сортировкой «Популярное» в «Для вас» (ревизия R2).
	path("hot/", RedirectView.as_view(pattern_name="index", permanent=True)),
	path("search/", search, name="search"),
	path("people/suggested/", suggested_people, name="who-to-follow"),
	path('p/<uuid:pk>/', post_detail, name='post'),
	path('p/<uuid:pk>/conversation/', post_conversation, name='post-conversation'),
	path('p/<uuid:pk>/like/', like_post, name='post-like'),
	path('p/<uuid:pk>/repost/', repost_post, name='post-repost'),
	path('p/<uuid:pk>/bookmark/', bookmark_post, name='post-bookmark'),
	path('p/<uuid:pk>/pin/', pin_post, name='post-pin'),
	path('p/<uuid:pk>/vote/', vote_poll, name='post-vote'),
	path('bookmarks/', bookmarks, name='bookmarks'),
	path('tags/<str:name>/', hashtag, name='hashtag'),
	path('p/<uuid:pk>/delete/', delete_post, name='post-delete'),
	path('p/<uuid:pk>/report/', report_post, name='post-report'),
	path('compose/', compose, name='compose'),
	path('admin/', admin.site.urls),
	# Вход, регистрация с подтверждением почты, сброс и смена пароля и почты — django-allauth (E1).
	# Список сеансов allauth — у нас в «Данные и аккаунт».
	path('auth/sessions/', RedirectView.as_view(pattern_name='account-settings')),
	path('auth/', include('allauth.urls')),
	# Гостю — карточка без постов (accounts/profile_guest.html): для превью ссылок и поисковиков.
	path('users/<str:slug>/', UserProfileDetailView.as_view(), name='profile'),
	path('users/<str:username>/report/', report_profile, name='profile-report'),
	path('moderation/', include('moderation.urls')),
	path('notifications/', include('notifications.urls')),
	path('messages/', include('dm.urls')),
	path("edit/", login_required(ChangeProfileView.as_view()), name="edit-profile"),
	path("settings/theme/", set_theme, name="set-theme"),
	path("settings/blocked/", login_required(blocked_accounts), name="blocked-accounts"),
	path("settings/requests/", login_required(follow_requests), name="follow-requests"),
	path("settings/requests/<str:username>/", login_required(answer_follow_request), name="follow-request-answer"),
	path("settings/account/", account_settings, name="account-settings"),
	path("settings/account/export/", export_data, name="account-export"),
	path("settings/account/sessions/", end_sessions, name="account-sessions-end"),
	path("settings/account/delete/", delete_account, name="account-delete"),
	# Правила и документы (C5, E6) — открыты всем, в том числе забаненным.
	path("rules/", legal_page("legal/rules.html"), name="rules"),
	path("privacy/", legal_page("legal/privacy.html"), name="privacy"),
	path("consent/", consent_update, name="consent-update"),
	path("privacy/consent/", legal_page("legal/consent.html"), name="pd-consent"),
	path("cookies/", legal_page("legal/cookies.html"), name="cookies"),
	path('api/events/', tracking_views.events, name='api-events'),
	path('p/<uuid:pk>/not-interested/', tracking_views.not_interested, name='post-not-interested'),
	path('settings/not-interested/<int:pk>/delete/', tracking_views.forget_not_interested, name='not-interested-forget'),
	path('api/', include('api.urls')),
	path('following/', following, name='following'),
	path('follows-updates/', RedirectView.as_view(pattern_name='following', permanent=True)),
	path('settings/feed-sort/', set_feed_sort, name='feed-sort'),
]
if settings.DEBUG:
	# Статику при DEBUG и так раздаёт runserver (django.contrib.staticfiles); здесь — загрузки и toolbar.
	urlpatterns += [
		path("__debug__/", include("debug_toolbar.urls")),
		path(".well-known/appspecific/com.chrome.devtools.json", devtools_workspace),
	]
	urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)