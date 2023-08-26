from django.contrib import admin
from django.contrib.auth.models import Group, User

from customUser.models import CustomUser
from .settings import AUTH_USER_MODEL
from .models import Post, Tag

class PostAdmin(admin.ModelAdmin):
	model = Post
	
class TagAdmin(admin.ModelAdmin):
	model = Tag
	
class UserAdmin(admin.ModelAdmin):
	model = AUTH_USER_MODEL
	fields = ["username","first_name", "last_name", "last_login", "date_joined"]

admin.site.unregister(Group)
"""
admin.site.unregister(User)
admin.site.register(User, UserAdmin) """
admin.site.register(Post, PostAdmin)
admin.site.register(CustomUser, UserAdmin)
admin.site.register(Tag, TagAdmin)
