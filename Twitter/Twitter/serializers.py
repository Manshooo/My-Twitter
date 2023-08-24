from rest_framework import serializers
from .models import Post, Profile

class UserProfileSerialezer(serializers.ModelSerializer):
	class Meta:
		model = Profile
		fields = "__all__"
class PostSerializer(serializers.ModelSerializer):
	class Meta:
		model = Post
		fields = "__all__"