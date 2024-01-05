from rest_framework import serializers
from .models import Profile

class ProfileSerializer(serializers.ModelSerializer):
	class Meta:
		model = Profile
		fields = "__all__"
class ProfileListSerializer(serializers.ListSerializer):
	class Meta:
		model = Profile
		fields = ['user', 'username', 'avatar']