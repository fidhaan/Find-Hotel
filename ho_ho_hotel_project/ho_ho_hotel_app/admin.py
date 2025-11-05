from django.contrib import admin
from . import models
from login_app.models import Hotel
# Register your models here.
admin.site.register(models.Hotel)
admin.site.register(models.Room)
admin.site.register(models.Favourite)
admin.site.register(models.Review)