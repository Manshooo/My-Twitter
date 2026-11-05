from django.contrib import admin
from django.contrib.auth.models import Group

from customUser.models import CustomUser, FollowThrough
from .settings import AUTH_USER_MODEL
from .models import Profile

class FollowThroughInlineAdmin(admin.TabularInline):
	model = FollowThrough
	extra = 1
	fk_name = "follower"
class UserProfileAdmin(admin.ModelAdmin):
	model = Profile
	inlines = [FollowThroughInlineAdmin]
	list_display = ["username", "user", "is_verified", "likes_public"]
	list_editable = ["is_verified"]
	list_filter = ["is_verified"]
	search_fields = ["username", "user__username"]

class UserAdmin(admin.ModelAdmin):
	model = CustomUser
	list_display = ["username", "email", "first_name", "last_name", "last_visit", "last_login", "date_joined"]
	fields = ["username", "password", "first_name", "last_name", "email", "last_login", "date_joined", ]


admin.site.unregister(Group)
admin.site.register(CustomUser, UserAdmin)
admin.site.register(Profile, UserProfileAdmin)
