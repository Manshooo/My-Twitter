from django.contrib import admin

from .models import Post, Test

admin.site.register(Post)
admin.site.register(Test)