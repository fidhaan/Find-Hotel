from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.generic import ListView
import razorpay
import uuid
import json
from ho_ho_hotel_app.models import Room 
from .models import Payment

# Initialize Razorpay Client
# Assuming settings.RZP_KEY_ID and settings.RZP_KEY_SECRET are set
try:
    client = razorpay.Client(auth=(settings.RZP_KEY_ID, settings.RZP_KEY_SECRET))
except AttributeError:
    client = None
    print("WARNING: Razorpay client failed to initialize. Check RZP_KEY_ID/SECRET in settings.")


class CreateOrderView(LoginRequiredMixin, View):
    """
    1. Fetches room details.
    2. Creates a Razorpay Order ID.
    3. Creates a local Payment object with PENDING status.
    4. Renders the checkout page with necessary Razorpay keys and order details.
    """
    def get(self, request, room_id):
        if not client:
            messages.error(request, "Payment service is currently unavailable.")
            return redirect('home')

        # Use an outer try-except block to catch all errors during order creation
        try:
            # 1. Fetch Room and Calculate Amount
            room = get_object_or_404(Room, id=room_id)
            amount_in_cents = int(room.price_per_night * 100) 

            # 2. Create Order in Razorpay
            razorpay_order = client.order.create({
                'amount': amount_in_cents, 
                'currency': 'INR',
                'payment_capture': '1' 
            })
            
            # 3. Create local PENDING Payment record
            payment = Payment.objects.create(
                user=request.user,
                room=room,
                amount=room.price_per_night,
                razorpay_order_id=razorpay_order['id'],
                status='PENDING'
            )

            context = {
                'room': room,
                'razorpay_key': settings.RZP_KEY_ID,
                'order_id': razorpay_order['id'],
                'amount': room.price_per_night,
                'amount_in_cents': amount_in_cents,
                'currency': 'INR',
                'payment_object_id': payment.id # Pass local ID for verification lookup
            }

            # Render the checkout page which contains the Razorpay JS
            return render(request, 'payment/checkout.html', context)
        
        except ValueError:
            # Catches errors if the room_id is invalid or price calculation fails
            messages.error(request, "Invalid room ID or price provided.")
            return redirect('home')

        except Exception as e:
            # Catches any unexpected error during Razorpay API call or database operation
            print(f"CRITICAL ERROR IN CREATE ORDER: {e}")
            messages.error(request, "Failed to initiate payment. Please try again.")
            
            # Safely redirect back to the room detail page using 'pk'
            # We must use the 'room_id' here since 'room' may not be defined if it failed earlier
            try:
                # Use 'pk' here to match your URL pattern
                return redirect(reverse('room_detail', kwargs={'pk': room_id}))
            except Exception:
                return redirect('home')
            
@method_decorator(csrf_exempt, name='dispatch')
class PaymentVerifyView(View):
    """
    Handles the callback from the Razorpay checkout modal.
    Verifies the signature and updates the payment status.
    """
    def post(self, request):
        if not client:
            messages.error(request, "Payment service is currently unavailable.")
            return redirect('home')
            
        fallback_redirect_url = reverse('home')

        try:
            # 1. Reliable Data Retrieval (from request.POST)
            data = request.POST 
            
            razorpay_payment_id = data.get('razorpay_payment_id')
            razorpay_order_id = data.get('razorpay_order_id')
            razorpay_signature = data.get('razorpay_signature')
            payment_object_id = data.get('payment_object_id')
            
            # --- DEBUGGING STEP: Check server console to see what was received! ---
            # Keeping the print statement for continued monitoring
            print(f"\n--- DEBUG: Payment Verify Received Data ---")
            print(f"Payment ID: {razorpay_payment_id}")
            print(f"Order ID: {razorpay_order_id}")
            print(f"Signature: {razorpay_signature}")
            print(f"Local ID: {payment_object_id}")
            print(f"-----------------------------------------\n")
            
            
            # --- CRITICAL MISSING DATA CHECK ---
            if not payment_object_id or not razorpay_order_id:
                messages.error(request, "Missing internal payment reference identifiers.")
                return redirect(fallback_redirect_url)
            
            # 2. Fetch the local payment object
            try:
                payment = get_object_or_404(Payment, id=payment_object_id, razorpay_order_id=razorpay_order_id)
            except ValueError:
                messages.error(request, "Invalid payment reference ID format.")
                return redirect(fallback_redirect_url)
            except Payment.DoesNotExist:
                messages.error(request, "Payment record not found.")
                return redirect(fallback_redirect_url)
            
            
            # 🌟 FIX: Safely determine the redirect URL
            # We use the reverse lookup directly, since get_absolute_url() is missing
            redirect_url = reverse('room_detail', kwargs={'pk': payment.room.id})


            # --- CANCELLATION/FAILURE CHECK ---
            if not razorpay_payment_id or not razorpay_signature:
                payment.status = 'FAILED'
                payment.save()
                messages.warning(request, "Payment was cancelled or interrupted by the user.")
                return redirect(redirect_url)

            
            # 3. Verify the payment signature
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            
            try:
                client.utility.verify_payment_signature(params_dict)
                
                # 4. Signature is valid -> Mark payment as PAID
                payment.razorpay_payment_id = razorpay_payment_id
                payment.razorpay_signature = razorpay_signature
                payment.status = 'PAID'
                payment.save()
                room = payment.room
                room.is_available = False
                room.save()
                
                # 🌟 IMPORTANT: Integrate your booking/reservation logic here later 🌟
                
                messages.success(request, f"Payment for Room {payment.room.room_number} successful! Your booking is confirmed.")
                return redirect(redirect_url)

            except Exception as e:
                # 5. Signature is invalid or verification failed
                payment.status = 'FAILED'
                payment.save()
                messages.error(request, f"Payment verification failed due to signature mismatch.")
                return redirect(redirect_url)

        except Exception as e:
            # General unexpected error
            print(f"CRITICAL ERROR IN PAYMENT VERIFICATION: {e}")
            messages.error(request, "An internal error occurred during payment processing.")
            return HttpResponseBadRequest("Verification Error")
        
class UserOrderView(LoginRequiredMixin, ListView):
    """
    Displays a list of all successful room bookings (PAID payments) 
    made by the currently logged-in user.
    """
    model = Payment
    template_name = 'payment/user_orders.html' # We will create this template
    context_object_name = 'orders'
    paginate_by = 10 # Optional: for handling many orders

    def get_queryset(self):
        # Filter the Payment objects:
        # 1. payments belonging to the current user
        # 2. payments where the status is 'PAID'
        queryset = Payment.objects.filter(
            user=self.request.user,
            status='PAID'
        ).select_related('room', 'room__hotel') # Optimized for fewer database queries
        
        return queryset