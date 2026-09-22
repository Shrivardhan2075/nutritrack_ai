from django.contrib import admin

from .models import DetectedFoodItem, Meal

admin.site.register(Meal)
admin.site.register(DetectedFoodItem)
