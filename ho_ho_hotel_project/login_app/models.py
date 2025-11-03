from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid

# 1. CustomUser Model (for the person)
class CustomUser(AbstractUser):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    # This flag identifies the type of user
    is_hotel_owner = models.BooleanField(
        default=False,
        help_text=_('Designates whether this user is a hotel owner.'),
        verbose_name=_('hotel owner status')
    )
    
    # --- Standard Profile Fields ---
    age = models.IntegerField(
        null=True, 
        blank=True, 
        help_text="Optional: Enter your age."
    )
    
    phone_number = models.CharField(
        max_length=15, 
        null=True, 
        blank=True, 
        help_text="Optional: Enter your phone number."
    )
    
    # --- OTP Verification Fields (CRITICAL for two-step change) ---
    new_email = models.EmailField(max_length=254, null=True, blank=True) 
    new_phone_number = models.CharField(max_length=15, null=True, blank=True)
    verification_otp = models.CharField(max_length=6, null=True, blank=True)
    
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    
    email_otp = models.CharField(max_length=6, null=True, blank=True)
    phone_otp = models.CharField(max_length=6, null=True, blank=True)

    # --- Django Internal Fields (for related_name conflicts) ---
    # These are necessary because you inherited AbstractUser
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=_('groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name="custom_user_groups_set",
        related_query_name="custom_user",
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name="custom_user_permissions_set",
        related_query_name="custom_user",
    )

    def __str__(self):
        return self.username

# -------------------------------------------------------------

# 2. Hotel Model (for the business/data)
class Hotel(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    # Link to the owner's account (One-to-One ensures one owner per hotel for now)
    owner = models.OneToOneField(
        CustomUser, 
        on_delete=models.CASCADE, 
        limit_choices_to={'is_hotel_owner': True} 
    )
    
    # Business-specific fields
    hotel_name = models.CharField(max_length=255, unique=True)
    place = models.CharField(max_length=100)
    address = models.TextField()

    # Document upload fields
    ownership_proof = models.FileField(
        upload_to='hotel_documents/proofs/',
        help_text="Upload scanned copy of ownership proof."
    )
    license_number = models.CharField(max_length=50, unique=True)
    owner_id_proof = models.FileField(
        upload_to='hotel_documents/id_proofs/',
        help_text="Upload scanned copy of the owner's ID proof (e.g., Aadhar, Passport)."
    )

    def __str__(self):
        return self.hotel_name