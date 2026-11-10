from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from django.conf.urls.static import static
from django.conf import settings

from .views import index, follows_updates, hot_news, legal_page, search, suggested_people
from customUser.account import account_settings, delete_account, export_data
from customUser.views import (
	ChangeProfileView, UserProfileDetailView, answer_follow_request, blocked_accounts, follow_requests, set_theme,
)
from moderation.views import report_post, report_profile
from post.views import bookmark_post, bookmarks, compose, delete_post, hashtag, like_post, post_detail, repost_post

urlpatterns = [
	path('', index, name='index'),
	path("hot/", hot_news, name="hot-news"),
	path("search/", search, name="search"),
	path("people/suggested/", suggested_people, name="who-to-follow"),
	path('p/<uuid:pk>/', post_detail, name='post'),
	path('p/<uuid:pk>/like/', like_post, name='post-like'),
	path('p/<uuid:pk>/repost/', repost_post, name='post-repost'),
	path('p/<uuid:pk>/bookmark/', bookmark_post, name='post-bookmark'),
	path('bookmarks/', bookmarks, name='bookmarks'),
	path('tags/<str:name>/', hashtag, name='hashtag'),
	path('p/<uuid:pk>/delete/', delete_post, name='post-delete'),
	path('p/<uuid:pk>/report/', report_post, name='post-report'),
	path('compose/', compose, name='compose'),
	path('admin/', admin.site.urls),
	# Вход, регистрация с подтверждением почты, сброс и смена пароля и почты — django-allauth (E1).
	path('auth/', include('allauth.urls')),
	path('users/<str:slug>/', login_required(UserProfileDetailView.as_view()), name='profile'),
	path('users/<str:username>/report/', report_profile, name='profile-report'),
	path('moderation/', include('moderation.urls')),
	path('notifications/', include('notifications.urls')),
	path("edit/", login_required(ChangeProfileView.as_view()), name="edit-profile"),
	path("settings/theme/", set_theme, name="set-theme"),
	path("settings/blocked/", login_required(blocked_accounts), name="blocked-accounts"),
	path("settings/requests/", login_required(follow_requests), name="follow-requests"),
	path("settings/requests/<str:username>/", login_required(answer_follow_request), name="follow-request-answer"),
	path("settings/account/", account_settings, name="account-settings"),
	path("settings/account/export/", export_data, name="account-export"),
	path("settings/account/delete/", delete_account, name="account-delete"),
	# Правила и документы (C5, E6) — открыты всем, в том числе забаненным.
	path("rules/", legal_page("legal/rules.html"), name="rules"),
	path("privacy/", legal_page("legal/privacy.html"), name="privacy"),
	path("privacy/consent/", legal_page("legal/consent.html"), name="pd-consent"),
	path('api/', include('api.urls')),
	path('follows-updates/', login_required(follows_updates), name="follows-updates"),
]
if settings.DEBUG:
	# Статику при DEBUG и так раздаёт runserver (django.contrib.staticfiles); здесь — загрузки и toolbar.
	urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
	urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)