from rest_framework import serializers
from .models import Post

class PostSerializer(serializers.ModelSerializer):
    
	class Meta:
		model = Post
		fields = ('pk', 'post_text', 'post_author', 'post_date', 'post_images')