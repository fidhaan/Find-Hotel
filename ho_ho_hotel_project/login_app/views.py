from django.shortcuts import render, redirect
from django.contrib.auth import update_session_auth_hash as update_password_session_auth
from django.views import View

from django.views.generic.edit import CreateView, UpdateView, DeleteView

from django.urls import reverse_lazy, reverse

from django.contrib import messages

from .forms import CustomUserCreationForm, CustomUserChangeForm, UserUpdateForm, SetPasswordWithOTPForm

from .models import CustomUser

from django.contrib.auth.views import LoginView, LogoutView

from django.contrib.auth.forms import AuthenticationForm

from .forms import CustomUserCreationForm, HotelOwnerCreationForm

from .forms import HotelOwnerCreationForm, HotelRegistrationForm

from .models import CustomUser, Hotel
from .forms import CustomUserCreationForm, VerificationForm # <- Add VerificationForm
from django.db import IntegrityError
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from twilio.rest import Client
from django.views.generic import DetailView
from django.conf import settings
from django.contrib.auth.views import PasswordChangeView
import random
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponse
from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes


REGISTERED_EMAIL = "fidhaancaketales2025@gmail.com"
REGISTERED_PHONE = "+917559942623"

class LoginPageView(View):

    def get(self, request, *args, **kwargs):

        return render(request, 'login_app/login-page.html')

class RegistrationView(View):
    """
    Handles two-step user registration, sending OTPs to a fixed, registered contact.
    Step 1: Get user data, save unverified user, send OTPs to registered contact.
    Step 2: Verify OTPs (from registered contact) and finalize account creation.
    """
    user_form_class = CustomUserCreationForm
    otp_form_class = VerificationForm
    template_name = 'login_app/register.html'
    success_url = reverse_lazy('login')

    # ⭐ MODIFICATION 1: Define the fixed contact details for OTP delivery
    REGISTERED_EMAIL = "fidhaancaketales2025@gmail.com"
    REGISTERED_PHONE = "+917559942623" # Your static phone number (must be valid format)

    def get(self, request):
        # 1. Check for a temporary user from a previous, unverified attempt
        temp_user_id = request.session.get('temp_user_id')
        if temp_user_id:
            try:
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False)
                user.delete()
                messages.warning(request, "Abandoned registration cleaned up. Please start fresh.")
            except CustomUser.DoesNotExist:
                pass
            
            # 2. Clear all session data associated with the flow
            if 'reg_data' in request.session:
                del request.session['reg_data']
            if 'temp_user_id' in request.session:
                del request.session['temp_user_id']
                
        # 3. Render the initial form
        return render(request, self.template_name, {
            'form': self.user_form_class(),
            'otp_form': None,
            'current_step': 1,
            'title': 'Register New User (Step 1 of 2)'
        })

    def post(self, request):
        current_step = request.POST.get('current_step', '1')

        if current_step == '1':
            # --- STEP 1: Process User Data and Send OTPs ---
            form = self.user_form_class(request.POST)

            if form.is_valid():
                try:
                    # 1. Temporarily save the user to the database (unverified)
                    user = form.save(commit=False)
                    user.is_active = False # CRITICAL: Deactivate until verified
                    
                    # 2. Generate and store OTPs
                    email_otp = generate_otp()
                    phone_otp = generate_otp()
                    user.email_otp = email_otp
                    
                    # Get the user's input phone number (to determine if phone OTP is needed)
                    phone_number_input = form.cleaned_data.get('phone_number')
                    
                    if phone_number_input:
                        user.phone_otp = phone_otp
                        # ⭐ MODIFICATION 2: Send OTP to the FIXED registered phone
                        send_otp_to_phone(self.REGISTERED_PHONE, phone_otp)
                    else:
                        user.phone_otp = None
                    
                    user.save() # Save the user with OTPs and inactive status
                    
                    # 3. Send Email OTP (always required)
                    # ⭐ MODIFICATION 3: Send OTP to the FIXED registered email
                    send_otp_to_email(self.REGISTERED_EMAIL, email_otp)
                    
                    # 4. Store temporary user ID in session
                    request.session['temp_user_id'] = str(user.pk)
                    
                    messages.info(request, f"Verification codes sent! Check the registered contacts ({self.REGISTERED_EMAIL}, {self.REGISTERED_PHONE}) for the OTPs to finalize registration.")
                    
                    # Proceed to Step 2 (OTP form)
                    return render(request, self.template_name, {
                        'form': form,
                        'otp_form': self.otp_form_class(),
                        'current_step': 2,
                        'phone_required': bool(phone_number_input), # Tell template if phone was provided
                        'title': 'Verify Your Details (Step 2 of 2)'
                    })
                
                except IntegrityError:
                    messages.error(request, "A user with that username or email already exists.")
                    return render(request, self.template_name, {'form': form, 'current_step': 1})
                except Exception as e:
                    print(f"Registration Error: {e}")
                    messages.error(request, "An unexpected error occurred during OTP sending. Please try again.")
                    return render(request, self.template_name, {'form': form, 'current_step': 1})

            else:
                # Re-render Step 1 with errors
                return render(request, self.template_name, {'form': form, 'current_step': 1})

        elif current_step == '2':
            # --- STEP 2: Process OTP Verification (No change needed here, as verification uses user.email_otp/phone_otp) ---
            temp_user_id = request.session.get('temp_user_id')
            if not temp_user_id:
                messages.error(request, "Session expired. Please restart registration.")
                return redirect('register')
            
            try:
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False)
            except CustomUser.DoesNotExist:
                messages.error(request, "Invalid registration state.")
                return redirect('register')

            otp_form = self.otp_form_class(request.POST)
            
            if otp_form.is_valid():
                # 1. Check Email OTP (checks against code stored in user.email_otp)
                email_otp_entered = otp_form.cleaned_data['email_otp']
                if email_otp_entered == user.email_otp:
                    user.is_email_verified = True
                else:
                    messages.error(request, "Invalid Email Verification Code.")
                    user.is_email_verified = False
                
                # 2. Check Phone OTP (checks against code stored in user.phone_otp)
                if user.phone_number and user.phone_otp:
                    phone_otp_entered = otp_form.cleaned_data['phone_otp']
                    if phone_otp_entered == user.phone_otp:
                        user.is_phone_verified = True
                    else:
                        messages.error(request, "Invalid Phone Verification Code.")
                        user.is_phone_verified = False
                else:
                    user.is_phone_verified = True

                # 3. Finalize Account only if BOTH required verifications passed
                if user.is_email_verified and user.is_phone_verified:
                    user.is_active = True
                    user.email_otp = None
                    user.phone_otp = None
                    user.save()
                    
                    del request.session['temp_user_id']
                    messages.success(request, f'Account successfully created and verified for {user.username}! Please log in.')
                    return redirect(self.success_url)
                
                else:
                    # If any verification failed, re-render the OTP form with errors
                    user.save() 
                    return render(request, self.template_name, {
                        'form': self.user_form_class(initial=user.__dict__), 
                        'otp_form': otp_form,
                        'current_step': 2,
                        'phone_required': bool(user.phone_number),
                        'title': 'Verify Your Details (Step 2 of 2)'
                    })
            
            else:
                # OTP form validation failed (e.g., fields left blank)
                return render(request, self.template_name, {
                    'form': self.user_form_class(initial=user.__dict__),
                    'otp_form': otp_form,
                    'current_step': 2,
                    'phone_required': bool(user.phone_number),
                    'title': 'Verify Your Details (Step 2 of 2)'
                })
        
        # Default to initial step
        return redirect('register')
class CustomLoginView(LoginView):
    """
    Handles user login using Django's built-in AuthenticationForm.
    We explicitly define the form_class here to guarantee the form context is available
    to the template for rendering.
    """
    form_class = AuthenticationForm # <--- EXPLICITLY set the default Django login form
    template_name = 'login_app/login-page.html' 
    
    def get_success_url(self):
        return reverse_lazy('home') 
        
    def form_valid(self, form):
        messages.success(self.request, f'Welcome back, {self.request.user.username}!')
        return super().form_valid(form)


# Logout View (Kept for context)
class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('home')

# login_app/views.py

# ... (Previous code) ...

class HotelOwnerRegistrationView(View):
    """
    Handles the three-step registration for Hotel Owners, sending OTPs to a fixed, registered contact.
    """
    owner_form_class = HotelOwnerCreationForm
    hotel_form_class = HotelRegistrationForm
    otp_form_class = VerificationForm
    template_name = 'login_app/register_owner.html'
    
    # ⭐ MODIFICATION 4: Define the fixed contact details for OTP delivery
    REGISTERED_EMAIL = "fidhaancaketales2025@gmail.com"
    REGISTERED_PHONE = "+917559942623" # Your static phone number

    # ... (get method logic remains the same for cleanup and initial render)
    def get(self, request):
        temp_user_id = request.session.get('temp_owner_user_id')
        if temp_user_id:
            try:
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False, is_hotel_owner=True)
                user.delete()
                messages.warning(request, "Abandoned hotel owner registration cleaned up. Please start fresh.")
            except CustomUser.DoesNotExist:
                pass

        for key in ['owner_registration_data', 'temp_owner_user_id']:
            if key in request.session:
                del request.session[key]
                
        owner_form = self.owner_form_class()
        
        return render(request, self.template_name, {
            'owner_form': owner_form,
            'hotel_form': None,
            'current_step': 1,
            'title': 'Register Hotel Owner (Step 1 of 3)'
        })

    def post(self, request):
        current_step = int(request.POST.get('current_step', 1))
        
        if current_step == 1:
            # ... (Step 1 logic remains the same - stores user input in session)
            owner_form = self.owner_form_class(request.POST)
            if owner_form.is_valid():
                data = owner_form.cleaned_data
                request.session['owner_registration_data'] = {
                    'username': data['username'],
                    'email': data['email'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'phone_number': data['phone_number'],
                    'password': data['password2'], 
                }
                hotel_form = self.hotel_form_class()
                return render(request, self.template_name, {
                    'owner_form': owner_form,
                    'hotel_form': hotel_form, 
                    'current_step': 2,
                    'title': 'Register Hotel Details (Step 2 of 3)'
                })
            else:
                return render(request, self.template_name, {
                    'owner_form': owner_form, 'current_step': 1,
                    'title': 'Register Hotel Owner (Step 1 of 3)'
                })

        elif current_step == 2:
            # --- STEP 2: Process Hotel Data and Create Unverified User/Hotel ---
            owner_data = request.session.get('owner_registration_data')
            if not owner_data:
                messages.error(request, "Session expired. Please restart registration.")
                return redirect('owner_register')

            hotel_form = self.hotel_form_class(request.POST, request.FILES)
            
            if hotel_form.is_valid():
                try:
                    # 1. FINAL: Create the CustomUser (Inactive and unverified)
                    user = CustomUser.objects.create_user(
                        username=owner_data['username'],
                        email=owner_data['email'],
                        password=owner_data['password'],
                        first_name=owner_data['first_name'],
                        last_name=owner_data['last_name'],
                        phone_number=owner_data['phone_number'],
                        is_hotel_owner=True,
                        is_active=False 
                    )
                
                    # 2. FINAL: Create the Hotel object linked to the new user
                    hotel = hotel_form.save(commit=False)
                    hotel.owner = user
                    hotel.save()

                    # 3. Generate and Send OTPs
                    email_otp = generate_otp()
                    phone_otp = generate_otp()
                    
                    user.email_otp = email_otp # Save OTP for verification
                    user.phone_otp = phone_otp # Save OTP for verification
                    user.save() 
                    
                    # ⭐ MODIFICATION 5: Send OTP to the FIXED registered email
                    send_otp_to_email(self.REGISTERED_EMAIL, email_otp)
                    # ⭐ MODIFICATION 6: Send OTP to the FIXED registered phone
                    send_otp_to_phone(self.REGISTERED_PHONE, phone_otp)
                    
                    # 4. Store user ID for Step 3 and clean up Step 1 data
                    request.session['temp_owner_user_id'] = str(user.pk) 
                    
                    del request.session['owner_registration_data']

                    messages.info(request, f"Verification codes sent! Check the registered contacts ({self.REGISTERED_EMAIL} and {self.REGISTERED_PHONE}) for the OTPs to finalize registration.")
                    
                    # Proceed to Step 3 (OTP form)
                    return render(request, self.template_name, {
                        'owner_form': self.owner_form_class(initial=owner_data),
                        'hotel_form': hotel_form, 
                        'otp_form': self.otp_form_class(),
                        'current_step': 3,
                        'title': 'Verify Owner Details (Step 3 of 3)'
                    })
                
                except IntegrityError:
                    messages.error(request, "A user with that username or email already exists. Please restart registration.")
                    return redirect('owner_register')
                except Exception as e:
                    print(f"Hotel Owner Registration Error: {e}")
                    if 'user' in locals() and not user.is_active:
                         user.delete() 
                    messages.error(request, "An unexpected error occurred. Please try again.")
                    return redirect('owner_register')

            else:
                # Re-render Step 2 with errors
                owner_form = self.owner_form_class(initial=owner_data)
                return render(request, self.template_name, {
                    'owner_form': owner_form,
                    'hotel_form': hotel_form,
                    'current_step': 2,
                    'title': 'Register Hotel Details (Step 2 of 3)'
                })

        elif current_step == 3:
            # --- STEP 3: Process OTP Verification (No change needed, verification checks saved OTPs) ---
            temp_user_id = request.session.get('temp_owner_user_id')
            if not temp_user_id:
                messages.error(request, "Session expired. Please restart registration.")
                return redirect('owner_register')
            
            try:
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False, is_hotel_owner=True)
            except CustomUser.DoesNotExist:
                messages.error(request, "Invalid registration state.")
                return redirect('owner_register')

            otp_form = self.otp_form_class(request.POST)
            
            if otp_form.is_valid():
                # Check Email OTP 
                email_match = otp_form.cleaned_data['email_otp'] == user.email_otp
                phone_match = otp_form.cleaned_data['phone_otp'] == user.phone_otp
                
                user.is_email_verified = email_match
                user.is_phone_verified = phone_match

                if not email_match:
                    messages.error(request, "Invalid Email Verification Code.")
                if not phone_match:
                    messages.error(request, "Invalid Phone Verification Code.")

                # Finalize Account only if BOTH verifications passed
                if user.is_email_verified and user.is_phone_verified:
                    user.is_active = True
                    user.email_otp = None
                    user.phone_otp = None
                    user.save()
                    
                    del request.session['temp_owner_user_id']
                    messages.success(request, f'Hotel Owner account successfully created and verified! Please log in.')
                    return redirect(reverse_lazy('login'))
                
                else:
                    user.save() # Keep unverified status
                    messages.error(request, "One or both verification codes are invalid. Please try again.")
                    return render(request, self.template_name, {
                        'otp_form': otp_form,
                        'current_step': 3,
                        'title': 'Verify Owner Details (Step 3 of 3)'
                    })
            
            else:
                # OTP form validation failed
                return render(request, self.template_name, {
                    'otp_form': otp_form,
                    'current_step': 3,
                    'title': 'Verify Owner Details (Step 3 of 3)'
                })
        
        # Default redirect on unexpected state
        return redirect('owner_register')
class UserProfileView(LoginRequiredMixin, DetailView):
    """
    Displays the logged-in user's profile, and their associated hotel details 
    if they are a hotel owner.
    """
    model = CustomUser
    template_name = 'login_app/user_profile.html'
    context_object_name = 'user_profile'

    def get_object(self, queryset=None):
        # The object is always the currently logged-in user
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['title'] = f"{user.username}'s Profile"
        
        # If the user is a hotel owner, attempt to fetch and display the hotel details
        if user.is_hotel_owner:
            try:
                context['hotel'] = Hotel.objects.get(owner=user)
            except Hotel.DoesNotExist:
                context['hotel'] = None
                messages.warning(self.request, "Hotel Owner, but no associated Hotel record found.")

        return context

class UserDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Allows the logged-in user to delete their CustomUser profile. 
    This will also CASCADE delete their associated Hotel record if they are an owner.
    """
    model = CustomUser
    template_name = 'login_app/user_confirm_delete.html'
    success_url = reverse_lazy('login') # Redirect to login after deletion
    context_object_name = 'user_to_delete'

    def get_object(self, queryset=None):
        # Ensure only the currently logged-in user's profile can be deleted
        return self.request.user

    def test_func(self):
        # Ensure the user is logged in
        return self.request.user.is_authenticated
    
    def form_valid(self, form):
        # Display a success message before deleting and redirecting
        messages.success(self.request, f"Account '{self.request.user.username}' and all associated data have been permanently deleted.")
        # Perform the actual deletion
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Confirm Account Deletion'
        # Pass the associated hotel details to the template for context
        if self.request.user.is_hotel_owner:
            try:
                context['hotel'] = Hotel.objects.get(owner=self.request.user)
            except Hotel.DoesNotExist:
                context['hotel'] = None
        return context
    
class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """
    Handles secure password change for logged-in users.
    Requires the user to enter their current password.
    """
    form_class = PasswordChangeForm
    template_name = 'login_app/password_change.html'
    
    def get_success_url(self):
        messages.success(self.request, "Your password was successfully updated.")
        return reverse_lazy('profile') 

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Change Password'
        return context

class SecurePasswordRequestView(LoginRequiredMixin, View):
    """Initiates the secure password change flow using ONLY Email OTP."""
    
    def get(self, request, *args, **kwargs):
        user = request.user
        
        try:
            # 1. Generate and store ONLY Email OTP
            email_otp = generate_otp()
            
            user.email_otp = email_otp 
            user.phone_otp = None # Ensure phone_otp is clear
            user.save() 

            # 2. Send ONLY Email OTP (using the helper function)
            send_otp_to_email(REGISTERED_EMAIL, email_otp)
            
            # 3. Success message
            messages.success(request, f"Verification code sent to the registered email ({REGISTERED_EMAIL}) to proceed with password change.")
            
            request.session['password_change_initiated'] = True
            
            # 4. Redirect to the verification view
            return redirect('otp_protected_password_change') 
            
        except Exception as e:
            # This block executes if email sending fails (check terminal for print(e))
            print(f"Error initiating password change or sending OTP: {e}") 
            messages.error(request, "An error occurred while initiating password change. Please contact support.")
            return redirect('profile')

# --- View 2: Verify OTP and Change Password ---
class OTPProtectedPasswordChangeView(LoginRequiredMixin, View):
    """
    Allows the user to set a new password only after successfully verifying 
    the Email OTP.
    """
    form_class = SetPasswordWithOTPForm 
    template_name = 'login_app/password_change_otp.html'
    
    def get(self, request, *args, **kwargs):
        # Check if the process was initiated
        if not request.session.get('password_change_initiated'):
            messages.warning(request, "Please initiate the secure password change process first.")
            return redirect('secure_password_request') 
        
        # Pass constants to the template
        context = {
            'form': self.form_class(user=request.user),
            'title': 'Secure Password Change',
            # NOTE: REGISTERED_EMAIL MUST be defined in the views.py file or imported.
            'REGISTERED_EMAIL': REGISTERED_EMAIL, 
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        # Security Check
        if not request.session.get('password_change_initiated'):
            messages.error(request, "Invalid request flow.")
            return redirect('profile') 
            
        user = request.user
        form = self.form_class(user=user, data=request.POST)

        if form.is_valid():
            # 1. Get ONLY the email OTP
            email_otp_entered = form.cleaned_data['email_otp']
            
            # 2. Compare ONLY the email OTP
            if email_otp_entered == user.email_otp:
                # OTP matches! Change the password
                new_password = form.cleaned_data['new_password1']
                user.set_password(new_password)
                
                # Clear OTP field and session flag
                user.email_otp = None
                # phone_otp is ignored/set to None earlier, no need to touch it here
                user.save()
                del request.session['password_change_initiated']
                
                update_password_session_auth(request, user)
                
                messages.success(request, "Your password was successfully updated via OTP verification.")
                return redirect('profile') 
            
            else:
                # OTP mismatch handling 
                form.add_error('email_otp', "Invalid Verification Code.")
                messages.error(request, "The verification code is incorrect.")
                
        # Re-render with errors, passing context
        return render(request, self.template_name, {
            'form': form,
            'title': 'Secure Password Change',
            'REGISTERED_EMAIL': REGISTERED_EMAIL,
        })
def generate_otp():
    """Generates a random 6-digit OTP."""
    return str(random.randint(100000, 999999))

def send_otp_to_email(user_email_for_log, otp):
    """
    Sends OTP to the FIXED designated email address.
    The 'user_email_for_log' argument is ignored for sending but used for logging.
    """
    fixed_recipient = 'fidhaancaketales2025@gmail.com'
    subject = 'OTP for Password Change Verification'
    message = f'Your verification code for changing your password is: {otp}.'
    email_from = settings.EMAIL_HOST_USER or 'noreply@yourdomain.com'
    
    try:
        send_mail(
            subject, 
            message, 
            email_from, 
            [fixed_recipient], # ⭐ CRITICAL: Sending only to the FIXED email
            fail_silently=False # ⭐ CRITICAL FIX: Ensure exceptions are raised if sending fails
        )
        print(f"--- EMAIL SENT SUCCESS --- OTP: {otp} to FIXED recipient: {fixed_recipient} (User email: {user_email_for_log})")
        return True
    except Exception as e:
        # This will catch errors related to EMAIL_HOST, port, credentials, etc.
        print(f"--- EMAIL SENDING FAILED --- Error: {e}")
        # Re-raise or return False to trigger the 'An error occurred...' message in the view
        raise e 


def send_otp_to_phone(user_phone_for_log, otp):
    """
    Sends OTP to the FIXED designated phone number using Twilio.
    The 'user_phone_for_log' argument is ignored for sending but used for logging.
    """
    fixed_recipient = '+917559942623'
    print(f"--- SMS ATTEMPTED --- OTP: {otp} to FIXED recipient: {fixed_recipient} (User phone: {user_phone_for_log})")
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f'Your verification code for password change is: {otp}',
            from_=settings.TWILIO_PHONE_NUMBER,
            to=fixed_recipient # ⭐ CRITICAL: Sending only to the FIXED phone
        )
        print(f"--- SMS SENT SUCCESS ---")
        return True
    except Exception as e:
        # This will catch errors related to Twilio credentials or account issues.
        print(f"Twilio SMS Error: {e}")
        # IMPORTANT: Raise the exception to ensure the main view catches it 
        # and displays the "An error occurred" message.
        raise e

class UserUpdateView(LoginRequiredMixin, UpdateView):
    model = CustomUser
    form_class = UserUpdateForm
    template_name = 'login_app/user_update.html'
    success_url = reverse_lazy('profile')
    
    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Your Profile'
        # ⭐ CRITICAL: Check the session for which OTPs are pending
        context['email_otp_sent'] = self.request.session.get('email_otp_sent', False)
        context['phone_otp_sent'] = self.request.session.get('phone_otp_sent', False)
        context['is_verification_step'] = context['email_otp_sent'] or context['phone_otp_sent']
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        user = self.object
        form = self.get_form() # Form creation must happen before checks for errors
        
        # Get session flags
        email_otp_sent = self.request.session.get('email_otp_sent', False)
        phone_otp_sent = self.request.session.get('phone_otp_sent', False)

        # --- PHASE 2: VERIFICATION STEP (Check dynamic OTPs) ---
        if email_otp_sent or phone_otp_sent:
            
            email_otp_entered = request.POST.get('email_otp')
            phone_otp_entered = request.POST.get('phone_otp')
            
            is_email_match = True
            is_phone_match = True
            success = True
            
            # 1. Check Email OTP if it was sent
            if email_otp_sent:
                if not email_otp_entered:
                    is_email_match = False
                    messages.error(request, "Email verification code is required.")
                elif str(email_otp_entered) == str(user.email_otp):
                    # Commit Email Change
                    user.email = user.new_email
                    user.new_email = None
                    user.email_otp = None
                else:
                    is_email_match = False
                    
            # 2. Check Phone OTP if it was sent
            if phone_otp_sent:
                if not phone_otp_entered:
                    is_phone_match = False
                    messages.error(request, "Phone verification code is required.")
                elif str(phone_otp_entered) == str(user.phone_otp):
                    # Commit Phone Change
                    user.phone_number = user.new_phone_number
                    user.new_phone_number = None
                    user.phone_otp = None
                else:
                    is_phone_match = False
            
            success = is_email_match and is_phone_match
            
            if success:
                # Success: ALL required verifications matched
                user.save() 
                if 'email_otp_sent' in request.session: del request.session['email_otp_sent']
                if 'phone_otp_sent' in request.session: del request.session['phone_otp_sent']
                
                messages.success(request, "Profile updated and verified successfully! 🎉")
                return redirect(self.success_url) 

            else:
                # Failure: At least one OTP didn't match (or was empty)
                if email_otp_sent and not is_email_match:
                    if 'email_otp' not in form.errors: form.errors['email_otp'] = form.error_class()
                    form.errors['email_otp'].append("Invalid or missing Email Verification Code.")

                if phone_otp_sent and not is_phone_match:
                    if 'phone_otp' not in form.errors: form.errors['phone_otp'] = form.error_class()
                    form.errors['phone_otp'].append("Invalid or missing Phone Verification Code.")
                
                # Re-render the page with the error and the verification state intact
                return self.render_to_response(self.get_context_data(form=form))

        # --- PHASE 1: INITIAL SUBMISSION (Let UpdateView handle form validation) ---
        else:
            if form.is_valid():
                return self.form_valid(form) 
            else:
                return self.form_invalid(form)

    def form_valid(self, form):
        user = self.get_object() 
        original_email = user.email or '' 
        original_phone = user.phone_number or ''
        new_email = form.cleaned_data.get('email')
        new_phone = form.cleaned_data.get('phone_number')

        needs_email_verification = False
        needs_phone_verification = False

        # --- Check Email Change (robust comparison) ---
        email_changed = (
            new_email and new_email.strip().lower() != original_email.strip().lower()
        )
        
        if email_changed:
            user.new_email = new_email
            
            # 3. REVERT: Assign the guaranteed non-null value back to the primary field
            # This assignment satisfies the NOT NULL constraint on save.
            user.email = original_email 
            
            # Setup OTP (Sending logic is now confirmed to work)
            email_otp = generate_otp()
            user.email_otp = email_otp
            send_otp_to_email(new_email, email_otp) 
            needs_email_verification = True
            
        # --- Check Phone Change ---
        phone_changed = (
            new_phone and new_phone != original_phone
        )
        
        if phone_changed:
            user.new_phone_number = new_phone
            user.phone_number = original_phone # Revert
            
            # Setup OTP
            phone_otp = generate_otp()
            user.phone_otp = phone_otp
            send_otp_to_phone(new_phone, phone_otp)
            needs_phone_verification = True

        # Save non-sensitive fields and the current user object state
        self.object = form.save(commit=False)
        
        if needs_email_verification or needs_phone_verification:
            # Save the user with reverted sensitive fields and temporary new_* fields
            user.verification_otp = None 
            user.save() # THIS LINE MUST SUCCEED NOW!
            
            # Set session flags
            self.request.session['email_otp_sent'] = needs_email_verification
            self.request.session['phone_otp_sent'] = needs_phone_verification
            
            messages.info(self.request, "Verification initiated. Please enter the codes sent to your new email/phone.")
            return redirect(self.request.path) 
        
        else:
            # No sensitive changes detected, save non-sensitive fields
            user.new_email = None
            user.new_phone_number = None
            user.email_otp = None
            user.phone_otp = None
            user.verification_otp = None
            user.save() 
            messages.success(self.request, "Profile updated successfully (No sensitive fields changed).")
            return redirect(self.success_url)