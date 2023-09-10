from django.contrib import admin
from django.contrib.auth.models import Group

from customUser.models import CustomUser
from .settings import AUTH_USER_MODEL
from .models import Tag, Post

class PostAdmin(admin.ModelAdmin):
	model = Post

class TagAdmin(admin.ModelAdmin):
	model = Tag
	
class UserAdmin(admin.ModelAdmin):
	model = AUTH_USER_MODEL
	fields = ["username", "password", "first_name", "last_name", "email", "last_login", "date_joined"]


admin.site.unregister(Group)
admin.site.register(Post, PostAdmin)
admin.site.register(CustomUser, UserAdmin)
admin.site.register(Tag, TagAdmin)
