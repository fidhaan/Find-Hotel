from django.contrib.auth.forms import UserCreationForm, UserChangeForm, SetPasswordForm
from django import forms
from django.core.exceptions import ValidationError
from .models import CustomUser, Hotel 

# --- 1. Form for Standard User Registration ---

class CustomUserCreationForm(UserCreationForm):
    # ... (existing form fields) ...
    age = forms.IntegerField(
        required=False, 
        label='Age (optional)',
        help_text="Optional: Enter your age."
    )
    
    phone_number = forms.CharField(
        max_length=15, 
        required=False, 
        label='Phone Number (optional)',
        help_text="Optional: Enter your phone number."
    )

    class Meta(UserCreationForm.Meta):
        # ... (existing meta fields) ...
        model = CustomUser
        fields = UserCreationForm.Meta.fields + (
            'email', 
            'first_name', 
            'last_name', 
            'age',
            'phone_number'
        )
        labels = {
            # ... (existing labels) ...
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True

    # 🚨 CRITICAL FIX 1: Enforce Unique Email 
    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # Check if any user already exists with this email
        # The 'username' uniqueness is handled by the parent UserCreationForm.
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email address is already registered.")
            
        return email

    # 🚨 CRITICAL FIX 2: Enforce Unique Phone Number
    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        
        if phone:
            # 1. Strip all non-digit characters (except initial +)
            phone_digits = ''.join(filter(str.isdigit, phone))
            
            # Simple assumption: If a number is 10 digits and lacks a country code, add +91 (India)
            if len(phone_digits) == 10 and not phone.startswith('+'):
                phone = '+91' + phone_digits
                
            # If still not E.164 compliant, raise an error
            if not phone.startswith('+') or len(phone_digits) < 10:
                raise forms.ValidationError(
                    "Please enter the full international phone number starting with the '+' sign and country code (e.g., +91xxxxxxxxxx)."
                )
                
            # Check if any user already exists with this phone number
            if CustomUser.objects.filter(phone_number=phone).exists():
                 raise ValidationError("This phone number is already registered.")

        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_email_verified = False
        user.is_phone_verified = False
        if commit:
            user.save()
        return user

# --- 2. Form for Hotel Owner User Registration (Step 1 of Multi-step) ---

class HotelOwnerCreationForm(CustomUserCreationForm):
    # ... (content remains the same) ...
    class Meta(CustomUserCreationForm.Meta):
        model = CustomUser
        fields = (
            'username', 
            'email', 
            'first_name', 
            'last_name', 
            'phone_number'
        ) + UserCreationForm.Meta.fields[-2:]
        
        labels = {
            'username': 'Username (required)',
            'email': 'Email Address (required)',
            'first_name': 'Owner First Name',
            'last_name': 'Owner Last Name',
            'phone_number': 'Phone Number (required for contact)',
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_hotel_owner = True
        # is_email_verified/is_phone_verified are set to False by the parent form's save()
        if commit:
            user.save()
        return user


# --- 3. Form for Hotel Details Registration (Step 2 of Multi-step) ---

class HotelRegistrationForm(forms.ModelForm):
    # ... (content remains the same) ...
    class Meta:
        model = Hotel
        fields = (
            'hotel_name', 
            'place', 
            'address', 
            'license_number',
            'ownership_proof', 
            'owner_id_proof',
        )
        labels = {
            'hotel_name': 'Hotel Name',
            'place': 'City/Place',
            'address': 'Full Hotel Address',
            'license_number': 'Official Business License Number',
            'ownership_proof': 'Upload Hotel Ownership Proof Document (PDF/Image)',
            'owner_id_proof': 'Upload Owner National ID Proof (PDF/Image)',
        }

# --- 4. Standard User Change Form (Optional, but kept for consistency) ---

class CustomUserChangeForm(UserChangeForm):
    # ... (content remains the same) ...
    age = forms.IntegerField(
        required=False, 
        label='Age (optional)',
        help_text="Optional: Enter your age."
    )
    
    phone_number = forms.CharField(
        max_length=15, 
        required=False, 
        label='Phone Number (optional)',
        help_text="Optional: Enter your phone number."
    )

    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = (
            'username',
            'email',
            'first_name',
            'last_name',
            'age', 
            'phone_number'
        )
        labels = {
            'username': 'Username',
            'email': 'Email Address',
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'age': 'Age',
            'phone_number': 'Phone Number',
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True

# In forms.py

class UserUpdateForm(forms.ModelForm): 
    
    email = forms.EmailField(
        required=True, 
        label='Email Address',
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    
    phone_number = forms.CharField(
        max_length=15, 
        required=False, 
        label='Phone Number (optional)',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # ⭐ FIX: Define the dynamic OTP fields as CLASS ATTRIBUTES
    email_otp = forms.CharField(  # Renamed attribute to directly match the desired field name
        max_length=6,
        required=False, 
        label='Email Verification Code',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Email OTP'})
    )
    
    phone_otp = forms.CharField(  # Renamed attribute to directly match the desired field name
        max_length=6,
        required=False, 
        label='Phone Verification Code',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Phone OTP'})
    )
    
    class Meta:
        model = CustomUser
        fields = (
            'username',
            'first_name',
            'last_name',
            'age',
        )
        
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure initial data is set correctly
        if self.instance and self.instance.pk:
            self.fields['email'].initial = self.instance.email
            self.fields['phone_number'].initial = self.instance.phone_number

    # --- (clean_phone_number remains the same) ---
    def clean_phone_number(self):
        # ... (implementation remains the same) ...
        phone = self.cleaned_data.get('phone_number')
        
        if phone:
            phone_digits = ''.join(filter(str.isdigit, phone))
            
            if not phone.startswith('+'):
                if len(phone_digits) == 10:
                    phone = '+91' + phone_digits
                else:
                    self.add_error('phone_number', "Please enter the full international phone number starting with the '+' sign and country code (e.g., +91xxxxxxxxxx).")
                    
            elif len(phone) < 10:
                self.add_error('phone_number', "Phone number is too short.")
        
        return phone

    def clean(self):
        cleaned_data = super().clean()
        
        # Check if we are in the OTP submission phase by looking for any OTP data
        is_otp_submission = cleaned_data.get('email_otp') or cleaned_data.get('phone_otp')

        if is_otp_submission:
            # 1. Clear validation errors for ModelForm fields (username, age, etc.)
            for field_name in self.Meta.fields:
                if field_name in self.errors:
                    del self.errors[field_name]
            
            # 2. Prevent errors on the sensitive fields (email/phone_number) 
            #    which are required but not present in the OTP POST data.
            #    We remove them from errors AND from cleaned_data to ensure form.is_valid() passes
            #    and subsequent methods (like form.save) don't try to use a default None.
            for field_name in ['email', 'phone_number']:
                if field_name in self.errors:
                    del self.errors[field_name]
                if field_name in cleaned_data:
                    del cleaned_data[field_name] # Remove it from cleaned_data to skip it on save.
                    
        return cleaned_data
    
class VerificationForm(forms.Form):
    # This form is used for the final submission in both user and owner registration
    email_otp = forms.CharField(
        max_length=6,
        required=True,
        label='Email Verification Code',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter 6-digit Email Code'})
    )
    phone_otp = forms.CharField(
        max_length=6,
        required=False,
        label='Phone Verification Code (if entered)',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter 6-digit Phone Code'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        phone_otp = cleaned_data.get('phone_otp')
        
        # A simple check: if phone_otp is provided, it must have 6 digits.
        if phone_otp and len(phone_otp) != 6:
            self.add_error('phone_otp', 'Phone code must be 6 digits.')
        
        return cleaned_data
    
class SetPasswordWithOTPForm(SetPasswordForm):
    """
    Extends SetPasswordForm to include ONLY the Email OTP field for verification.
    This version uses the __init__ method to guarantee the custom field is attached.
    """
    # 1. Define the custom field as a class attribute
    email_otp = forms.CharField(
        max_length=6,
        required=True,
        label='Email Verification Code',
        widget=forms.TextInput(attrs={'placeholder': 'Enter 6-digit Email OTP', 'class': 'form-control'})
    )
    
    # 2. CRITICAL FIX: Ensure the field is present in the form instance
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Explicitly move the custom field from the class to the instance's fields dictionary.
        # This is what resolves the "AttributeError".
        if 'email_otp' not in self.fields:
            self.fields['email_otp'] = self.email_otp
            
        # Optional: Reorder fields to put the OTP at the end
        field_order = list(self.fields.keys())
        if 'email_otp' in field_order:
            field_order.remove('email_otp')
            field_order.append('email_otp')
        self.order_fields(field_order)