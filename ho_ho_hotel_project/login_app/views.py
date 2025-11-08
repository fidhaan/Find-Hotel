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
from .forms import CustomUserCreationForm, VerificationForm
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

class LoginPageView(View):

    def get(self, request, *args, **kwargs):

        return render(request, 'login_app/login-page.html')

class RegistrationView(View):
    """
    Handles the two-step user registration process:
    Step 1: User details submission and OTP generation/sending.
    Step 2: OTP verification to activate the account.
    """
    
    # Assigning the actual imported classes
    user_form_class = CustomUserCreationForm 
    otp_form_class = VerificationForm
    
    template_name = 'login_app/register.html'
    success_url = reverse_lazy('login')

    def get(self, request):
        """Handles initial page load and cleaning up abandoned sessions."""
        temp_user_id = request.session.get('temp_user_id')
        
        # Cleanup logic for abandoned registrations (UNCOMMENTED ACTUAL DB LOGIC)
        if temp_user_id:
            try:
                # Use the actual CustomUser model
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False) 
                user.delete() # Delete the temporary, unverified user
                messages.warning(request, "Abandoned registration cleaned up. Please start fresh.")
            except CustomUser.DoesNotExist:
                pass # If user doesn't exist, just pass
            
            # Clear session data related to temporary registration
            if 'reg_data' in request.session:
                del request.session['reg_data']
            if 'temp_user_id' in request.session:
                del request.session['temp_user_id']
                
        return render(request, self.template_name, {
            'form': self.user_form_class(),
            'otp_form': None,
            'current_step': 1,
            'title': 'Register New User (Step 1 of 2)'
        })

    def post(self, request):
        """Handles submission of both Step 1 (Registration) and Step 2 (Verification)."""
        current_step = request.POST.get('current_step', '1')

        # --- Step 1: User Registration Form Submission ---
        if current_step == '1':
            form = self.user_form_class(request.POST)

            if form.is_valid():
                try:
                    # Save user temporarily (is_active=False) and generate OTPs
                    user = form.save(commit=False)
                    user.is_active = False 
                    
                    email_otp = generate_otp()
                    # phone_otp = generate_otp() # REMOVED: Phone OTP generation
                    
                    email_input = user.email
                    # REMOVED: phone_number_input is no longer needed
                    
                    user.email_otp = email_otp
                    
                    # 1. REMOVED: Attempt Phone OTP Sending block
                    user.phone_otp = None # Ensure phone_otp is explicitly null/None
                    user.phone_number = None # REMOVED: The form won't save it, but explicitly set to None if necessary
                    
                    user.save() 
                    
                    # 2. Attempt Email OTP Sending
                    send_otp_to_email(email_input, email_otp)
                    
                    request.session['temp_user_id'] = str(user.pk)
                    
                    # User feedback message (Simplified)
                    messages.info(request, f"Verification code sent to your email ({email_input})! Enter the OTP to finalize registration.")
                    
                    # Transition to Step 2 (OTP form)
                    return render(request, self.template_name, {
                        'form': form,
                        'otp_form': self.otp_form_class(),
                        'current_step': 2,
                        'phone_required': False, # Changed to False since phone verification is skipped
                        'title': 'Verify Your Details (Step 2 of 2)'
                    })
                
                except IntegrityError:
                    messages.error(request, "A user with that username or email already exists.")
                    return render(request, self.template_name, {'form': form, 'current_step': 1})
                except Exception as e:
                    # ENHANCED LOGGING: This block catches failures in send_otp_to_email
                    print("\n\n" + "="*80)
                    print(f"*** ACTUAL ERROR: An external service failed during registration.")
                    print(f"*** The underlying error is: {e}")
                    print("="*80 + "\n\n")
                    messages.error(request, "An unexpected error occurred during OTP sending. Please ensure your email is correct.")
                    return render(request, self.template_name, {'form': form, 'current_step': 1})

            else:
                # Re-render Step 1 with errors
                return render(request, self.template_name, {'form': form, 'current_step': 1})

        # --- Step 2: OTP Verification Submission ---
        elif current_step == '2':
            temp_user_id = request.session.get('temp_user_id')
            if not temp_user_id:
                messages.error(request, "Session expired. Please restart registration.")
                return redirect('register')
            
            try:
                # Use the actual database lookup
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False)
                
            except CustomUser.DoesNotExist:
                messages.error(request, "Invalid registration state.")
                return redirect('register')

            # Instantiate a generic user form to display user data in the template if verification fails
            user_form_instance = self.user_form_class(initial=user.__dict__)
            
            otp_form = self.otp_form_class(request.POST)
            
            if otp_form.is_valid():
                # Email verification
                email_otp_entered = otp_form.cleaned_data.get('email_otp')
                if email_otp_entered and email_otp_entered == user.email_otp:
                    user.is_email_verified = True
                else:
                    messages.error(request, "Invalid Email Verification Code.")
                    user.is_email_verified = False
                
                # Phone verification
                # This logic is simplified/cleaned up as user.phone_number should be None
                user.is_phone_verified = True # Always skip verification since no phone number was provided
                # REMOVED: The logic block that checks and validates phone_otp_entered 

                # Finalize registration if both are verified
                if user.is_email_verified and user.is_phone_verified: # Since is_phone_verified is True, only email matters
                    user.is_active = True
                    user.email_otp = None
                    user.phone_otp = None
                    user.save()
                    
                    del request.session['temp_user_id']
                    messages.success(request, f'Account successfully created and verified for {user.username}! Please log in.')
                    return redirect(self.success_url)
                
                else:
                    # Verification failed (only email could fail), re-render Step 2
                    user.save() 
                    return render(request, self.template_name, {
                        'form': user_form_instance, 
                        'otp_form': otp_form,
                        'current_step': 2,
                        'phone_required': False, # Changed to False
                        'title': 'Verify Your Details (Step 2 of 2)'
                    })
            
            else:
                # OTP form is invalid, re-render Step 2 with errors
                return render(request, self.template_name, {
                    'form': user_form_instance,
                    'otp_form': otp_form,
                    'current_step': 2,
                    'phone_required': False, # Changed to False
                    'title': 'Verify Your Details (Step 2 of 2)'
                })
        
        # Fallback for unexpected POST requests
        return redirect('register')
class CustomLoginView(LoginView):
    
    form_class = AuthenticationForm 
    template_name = 'login_app/login-page.html' 
    
    def get_success_url(self):
        return reverse_lazy('home') 
        
    def form_valid(self, form):
        messages.success(self.request, f'Welcome back, {self.request.user.username}!')
        return super().form_valid(form)



class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('home')



class HotelOwnerRegistrationView(View):
    """
    Handles the three-step hotel owner registration:
    1. Owner details. 
    2. Hotel details (creates inactive user and hotel).
    3. OTP verification (activates user).
    """
    owner_form_class = HotelOwnerCreationForm
    hotel_form_class = HotelRegistrationForm
    otp_form_class = VerificationForm
    template_name = 'login_app/register_owner.html'
    success_url = reverse_lazy('login')
    
    # NOTE: Hardcoded contacts removed as per request.
    # REGISTERED_EMAIL = "fidhaancaketales2025@gmail.com"
    # REGISTERED_PHONE = "+917559942623" 

    def get(self, request):
        """Handles initial page load and cleaning up abandoned sessions."""
        temp_user_id = request.session.get('temp_owner_user_id')
        
        # Cleanup logic for abandoned registrations
        if temp_user_id:
            try:
                # Find and delete the temporary, unverified hotel owner user
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False, is_hotel_owner=True)
                user.delete()
                messages.warning(request, "Abandoned hotel owner registration cleaned up. Please start fresh.")
            except CustomUser.DoesNotExist:
                pass

        # Ensure all session data is cleared on fresh GET request
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
        """Handles submission of Step 1, Step 2, and Step 3."""
        current_step = int(request.POST.get('current_step', 1))
        
        # --- Step 1: Owner Details Submission (Session Storage) ---
        if current_step == 1:
            owner_form = self.owner_form_class(request.POST)
            if owner_form.is_valid():
                data = owner_form.cleaned_data
                # Store cleaned data (including plain password) in session
                request.session['owner_registration_data'] = {
                    'username': data['username'],
                    'email': data['email'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'phone_number': data['phone_number'],
                    'password': data['password2'], # Using password2 from form
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
                    'owner_form': owner_form, 
                    'current_step': 1,
                    'title': 'Register Hotel Owner (Step 1 of 3)'
                })

        # --- Step 2: Hotel Details Submission (User Creation, Hotel Save, OTP Send) ---
        elif current_step == 2:
            
            owner_data = request.session.get('owner_registration_data')
            if not owner_data:
                messages.error(request, "Session expired. Please restart registration.")
                return redirect('owner_register')

            hotel_form = self.hotel_form_class(request.POST, request.FILES)
            
            if hotel_form.is_valid():
                # Attempt to create user and send OTPs
                try:
                    # 1. Create Inactive CustomUser (Owner)
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
                
                    # 2. Save Hotel linked to the new user
                    hotel = hotel_form.save(commit=False)
                    hotel.owner = user
                    hotel.save()

                    # 3. Generate and Save OTPs
                    email_otp = generate_otp()
                    phone_otp = generate_otp()
                    
                    user.email_otp = email_otp 
                    user.phone_otp = phone_otp 
                    user.save() 
                    
                    # 4. Send OTPs to the actual user's contacts
                    send_otp_to_email(user.email, email_otp)
                    send_otp_to_phone(user.phone_number, phone_otp)
                    
                    # 5. Store temporary user ID and clear owner data
                    request.session['temp_owner_user_id'] = str(user.pk) 
                    del request.session['owner_registration_data']

                    # Update message to reflect user's contacts
                    phone_display = user.phone_number[-4:] if user.phone_number else 'N/A'
                    messages.info(request, f"Verification codes sent! Check your email ({user.email}) and phone number (ending in {phone_display}) for the OTPs to finalize registration.")
                    
                    # Rerender Step 3 (Verification Form)
                    return render(request, self.template_name, {
                        'owner_form': self.owner_form_class(initial=owner_data), # Optional: prefill owner data for display
                        'hotel_form': hotel_form, # Keep hotel form context
                        'otp_form': self.otp_form_class(),
                        'current_step': 3,
                        'title': 'Verify Owner Details (Step 3 of 3)'
                    })
                
                except IntegrityError:
                    messages.error(request, "A user with that username or email already exists. Please restart registration.")
                    return redirect('owner_register')
                except Exception as e:
                    print(f"Hotel Owner Registration Error: {e}")
                    # Attempt cleanup if user was created but OTP sending failed
                    if 'user' in locals() and not user.is_active:
                         user.delete() 
                    messages.error(request, "An unexpected error occurred during creation or OTP sending. Please try again.")
                    return redirect('owner_register')

            else:
                # Hotel form validation failed, re-render step 2
                owner_form = self.owner_form_class(initial=owner_data)
                return render(request, self.template_name, {
                    'owner_form': owner_form,
                    'hotel_form': hotel_form,
                    'current_step': 2,
                    'title': 'Register Hotel Details (Step 2 of 3)'
                })

        # --- Step 3: OTP Verification and Activation ---
        elif current_step == 3:
            
            temp_user_id = request.session.get('temp_owner_user_id')
            if not temp_user_id:
                messages.error(request, "Session expired. Please restart registration.")
                return redirect('owner_register')
            
            try:
                # Retrieve the temporary user
                user = CustomUser.objects.get(pk=temp_user_id, is_active=False, is_hotel_owner=True)
            except CustomUser.DoesNotExist:
                messages.error(request, "Invalid registration state.")
                return redirect('owner_register')

            otp_form = self.otp_form_class(request.POST)
            
            if otp_form.is_valid():
                
                email_match = otp_form.cleaned_data['email_otp'] == user.email_otp
                phone_match = otp_form.cleaned_data['phone_otp'] == user.phone_otp
                
                user.is_email_verified = email_match
                user.is_phone_verified = phone_match

                if not email_match:
                    messages.error(request, "Invalid Email Verification Code.")
                if not phone_match:
                    messages.error(request, "Invalid Phone Verification Code.")

                
                if user.is_email_verified and user.is_phone_verified:
                    # Success: Activate account
                    user.is_active = True
                    user.email_otp = None
                    user.phone_otp = None
                    user.save()
                    
                    del request.session['temp_owner_user_id']
                    messages.success(request, f'Hotel Owner account successfully created and verified! Please log in.')
                    return redirect(self.success_url)
                
                else:
                    # Failure: Re-render step 3 with error messages
                    user.save() 
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
        
        return redirect('owner_register') 
class UserProfileView(LoginRequiredMixin, DetailView):
    
    model = CustomUser
    template_name = 'login_app/user_profile.html'
    context_object_name = 'user_profile'

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['title'] = f"{user.username}'s Profile"
        
        if user.is_hotel_owner:
            try:
                context['hotel'] = Hotel.objects.get(owner=user)
            except Hotel.DoesNotExist:
                context['hotel'] = None
                messages.warning(self.request, "Hotel Owner, but no associated Hotel record found.")

        return context

class UserDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    
    model = CustomUser
    template_name = 'login_app/user_confirm_delete.html'
    success_url = reverse_lazy('login') 
    context_object_name = 'user_to_delete'

    def get_object(self, queryset=None):
        return self.request.user

    def test_func(self):
        return self.request.user.is_authenticated
    
    def form_valid(self, form):
        messages.success(self.request, f"Account '{self.request.user.username}' and all associated data have been permanently deleted.")
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Confirm Account Deletion'
        if self.request.user.is_hotel_owner:
            try:
                context['hotel'] = Hotel.objects.get(owner=self.request.user)
            except Hotel.DoesNotExist:
                context['hotel'] = None
        return context
    
class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Django's default password change view (requires current password)."""
    
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
            email_otp = generate_otp()
            
            user.email_otp = email_otp 
            user.phone_otp = None # Ensure phone_otp is clear if not needed
            user.save() 

            # Send OTP to the logged-in user's email
            send_otp_to_email(user.email, email_otp)
            
            messages.success(request, f"Verification code sent to your registered email ({user.email}) to proceed with password change.")
            
            request.session['password_change_initiated'] = True
            
            return redirect('otp_protected_password_change') 
            
        except Exception as e:
            print(f"Error initiating password change or sending OTP: {e}") 
            messages.error(request, "An error occurred while initiating password change. Please contact support.")
            return redirect('profile')

class OTPProtectedPasswordChangeView(LoginRequiredMixin, View):
    
    form_class = SetPasswordWithOTPForm 
    template_name = 'login_app/password_change_otp.html'
    
    def get(self, request, *args, **kwargs):
        if not request.session.get('password_change_initiated'):
            messages.warning(request, "Please initiate the secure password change process first.")
            return redirect('secure_password_request') 
        
        context = {
            'form': self.form_class(user=request.user),
            'title': 'Secure Password Change',
            # Pass the user's email for display in the template
            'user_email': request.user.email, 
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        if not request.session.get('password_change_initiated'):
            messages.error(request, "Invalid request flow.")
            return redirect('profile') 
            
        user = request.user
        form = self.form_class(user=user, data=request.POST)

        if form.is_valid():
            email_otp_entered = form.cleaned_data['email_otp']
            
            if email_otp_entered == user.email_otp:
                new_password = form.cleaned_data['new_password1']
                user.set_password(new_password)
                
                user.email_otp = None
                user.save()
                del request.session['password_change_initiated']
                
                # Keep the user logged in after password change
                update_password_session_auth(request, user)
                
                messages.success(request, "Your password was successfully updated via OTP verification.")
                return redirect('profile') 
            
            else:
                form.add_error('email_otp', "Invalid Verification Code.")
                messages.error(request, "The verification code is incorrect.")
                
        return render(request, self.template_name, {
            'form': form,
            'title': 'Secure Password Change',
            # Pass the user's email for display in the template
            'user_email': user.email, 
        })

def generate_otp():
    """Generates a simple 6-digit numeric OTP."""
    return str(random.randint(100000, 999999))

# !!! REVISED FUNCTION: Accepts the user's email as the recipient
def send_otp_to_email(user_email, otp):
    """Sends OTP via Django's send_mail function."""
    recipient = user_email 
    subject = 'OTP for Registration Verification'
    message = f'Your verification code for registration is: {otp}.'
    email_from = settings.EMAIL_HOST_USER or 'noreply@yourdomain.com'
    
    try:
        send_mail(
            subject, 
            message, 
            email_from, 
            [recipient], 
            fail_silently=False 
        )
        print(f"--- EMAIL SENT SUCCESS --- OTP: {otp} to recipient: {recipient}")
        return True
    except Exception as e:
        print(f"--- EMAIL SENDING FAILED --- Error: {e}")
        raise e 

# !!! REVISED FUNCTION: Accepts the user's phone number as the recipient
def send_otp_to_phone(user_phone_number, otp):
    """Sends OTP via Twilio SMS."""
    recipient = user_phone_number 
    print(f"--- SMS ATTEMPTED --- OTP: {otp} to recipient: {recipient}")
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f'Your verification code for registration is: {otp}',
            from_=settings.TWILIO_PHONE_NUMBER,
            to=recipient 
        )
        print(f"--- SMS SENT SUCCESS ---")
        return True
    except Exception as e:
        print(f"Twilio SMS Error: {e}")
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
        context['email_otp_sent'] = self.request.session.get('email_otp_sent', False)
        context['phone_otp_sent'] = self.request.session.get('phone_otp_sent', False)
        # Determine if the user is currently on the verification step
        context['is_verification_step'] = context['email_otp_sent'] or context['phone_otp_sent']
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        user = self.object
        form = self.get_form()
        
        email_otp_sent = self.request.session.get('email_otp_sent', False)
        # phone_otp_sent = self.request.session.get('phone_otp_sent', False) # REMOVED

        # --- Verification Step (OTP submitted) ---
        if email_otp_sent: # Check only for email_otp_sent
            
            # Retrieve OTPs entered by user
            email_otp_entered = request.POST.get('email_otp')
            # phone_otp_entered = request.POST.get('phone_otp') # REMOVED
            
            is_email_match = True
            is_phone_match = True # Always True since phone verification is skipped
            success = True
            
            # 1. Verify Email OTP
            if email_otp_sent:
                if not email_otp_entered:
                    is_email_match = False
                    messages.error(request, "Email verification code is required.")
                elif str(email_otp_entered) == str(user.email_otp):
                    # Success: Move new email to official field
                    user.email = user.new_email
                    user.new_email = None
                    user.email_otp = None
                else:
                    is_email_match = False
                    messages.error(request, "Invalid Email Verification Code.")
                    
            # 2. REMOVED: Verify Phone OTP Block
            
            success = is_email_match and is_phone_match # is_phone_match is always True here
            
            if success:
                # Clear session flags and save final changes
                if 'email_otp_sent' in request.session: del request.session['email_otp_sent']
                # if 'phone_otp_sent' in request.session: del request.session['phone_otp_sent'] # REMOVED
                
                # Save the user with updated email/phone and cleared OTPs/new_fields
                user.save() 
                
                messages.success(request, "Profile updated and verified successfully! 🎉")
                return redirect(self.success_url) 

            else:
                # Failed verification: Re-render the form with error messages
                return self.render_to_response(self.get_context_data(form=form))

        # --- Initial Submission Step (Form submitted with changes) ---
        else:
            if form.is_valid():
                # Call form_valid to handle validation and OTP sending
                return self.form_valid(form) 
            else:
                return self.form_invalid(form)

    def form_valid(self, form):
        user = self.get_object() 
        original_email = user.email or '' 
        # original_phone is no longer strictly needed for comparison but can remain

        # Get the new potential values from the submitted form
        new_email = form.cleaned_data.get('email')
        # new_phone is no longer needed for separate verification logic

        needs_email_verification = False
        # needs_phone_verification is now False by default and not checked
        # is_phone_otp_sent_successfully is no longer needed

        # 1. Check Email Change (EMAIL VERIFICATION LOGIC REMAINS)
        email_changed = (
            new_email and new_email.strip().lower() != original_email.strip().lower()
        )
        
        if email_changed:
            user.new_email = new_email
            
            # Keep the existing official email until verification is complete
            user.email = original_email 
            
            email_otp = generate_otp()
            user.email_otp = email_otp
            send_otp_to_email(new_email, email_otp) 
            needs_email_verification = True
        else:
            # If email wasn't changed, ensure temporary fields are clear/don't carry over
            user.new_email = None
            user.email_otp = None
            
        # --- REMOVED: Phone Number Change/OTP Logic Block ---
        # The phone number will now be updated directly by form.save() if no email verification is needed.
        user.new_phone_number = None
        user.phone_otp = None
        # ---------------------------------------------------

        # 3. Handle Saving
        needs_verification = needs_email_verification # Only check email now

        if needs_verification:
            
            # Update ALL fields from the form, including the new phone number, but keeping the old email
            self.object = form.save(commit=False) 
            
            # The form.save(commit=False) overwrote user.email, so restore the original email temporarily
            self.object.email = original_email 
            
            # Save the user with updated non-sensitive fields, new_fields, and OTPs
            self.object.save() # Use self.object to save the changes from the form
            
            # Set session flags based on successful OTP sending
            self.request.session['email_otp_sent'] = needs_email_verification
            self.request.session['phone_otp_sent'] = False # Always set to False now
            
            # Redirect to the same URL to show the verification fields
            messages.info(self.request, "Verification initiated. Please enter the code sent to your new email to finalize the update.")
            return redirect(self.request.path) 
        
        else:
            # No email change (phone change is now handled immediately)
            
            # Save all fields via the parent class method, which updates phone_number directly
            response = super().form_valid(form)
            
            # Clear any temporary fields just in case
            user.new_email = None
            user.new_phone_number = None
            user.email_otp = None
            user.phone_otp = None
            user.save() 
            
            messages.success(self.request, "Profile updated successfully.")
            return response
        
class CustomUserCreationForm:
    """Mock class mimicking your actual form for demonstration purposes."""
    def __init__(self, *args, **kwargs): 
        self.is_bound = True
        self.cleaned_data = kwargs.get('data') or {}
        self.errors = {}
    def is_valid(self): return True
    def save(self, commit=True): 
        class MockUser:
            pk = 'mock-id-123'
            is_active = False
            email = 'mock@example.com'
            phone_otp = None
            email_otp = '123456'
            phone_number = self.cleaned_data.get('phone_number')
            def save(self): pass
            def __dict__(self): return {'username': 'mock_user', 'email': self.email}
        return MockUser()
    @property
    def cleaned_data(self): return {'phone_number': None}
    
class VerificationForm:
    """Mock class mimicking your actual form for demonstration purposes."""
    def __init__(self, *args, **kwargs): 
        self.is_bound = True
        self.errors = {}
    def is_valid(self): return True
    @property
    def cleaned_data(self): 
        # Returns a mock set of OTPs for validation logic to pass
        return {'email_otp': '123456', 'phone_otp': '789012'}