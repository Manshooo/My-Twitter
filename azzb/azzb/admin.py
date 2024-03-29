from django.contrib import admin
from django.contrib.auth.models import Group

from customUser.models import CustomUser, FollowThrough
from .settings import AUTH_USER_MODEL
from post.models import Post
from .models import Profile

class PostAdmin(admin.ModelAdmin):
	model = Post
	list_display = ["author", "created_at", "likes_count"]

class FollowThroughInlineAdmin(admin.TabularInline):
	model = FollowThrough
	extra = 1
	fk_name = "follower"
class UserProfileAdmin(admin.ModelAdmin):
	model = Profile
	inlines = [FollowThroughInlineAdmin]

class UserAdmin(admin.ModelAdmin):
	model = CustomUser
	list_display = ["username", "email", "first_name", "last_name", "last_visit", "last_login", "date_joined"]
	fields = ["username", "password", "first_name", "last_name", "email", "last_login", "date_joined", ]


admin.site.unregister(Group)
admin.site.register(Post, PostAdmin)
admin.site.register(CustomUser, UserAdmin)
admin.site.register(Profile, UserProfileAdmin)
