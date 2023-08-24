from django.contrib import admin
from django.contrib.auth.models import Group, User

from .models import Post, Profile

class PostAdmin(admin.ModelAdmin):
    model = Post
    
class ProfileInline(admin.StackedInline):
    model = Profile

class UserAdmin(admin.ModelAdmin):
    model = User
    fields = ["username","first_name", "last_name", "last_login", "date_joined"]
    inlines = [ProfileInline]

admin.site.unregister(Group)
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(Post)
