from django.contrib.auth import login
from django.db import transaction
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Complaint, Coupon, CouponMeal, CouponTransferRequest, Feedback, Mess, MessMenu, Student
from .serializers import (
    AuthUserSerializer,
    ComplaintSerializer,
    CouponSerializer,
    CouponExchangeCreateSerializer,
    CouponExchangeRequestSerializer,
    FeedbackSerializer,
    LoginSerializer,
    MessSerializer,
    MessMenuCreateSerializer,
    MessMenuSerializer,
    SignupSerializer,
    StudentSerializer,
)


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


def health_check(request):
    return JsonResponse({'status': 'ok'})


class SignupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': 'Signup successful.',
                'user': AuthUserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.context['request'] = request
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        login(request, user)

        daily_coupons_created = 0
        if hasattr(user, 'student'):
            daily_coupons_created = Coupon.create_daily_coupons_for_student(user.student)

        return Response(
            {
                'message': 'Login successful.',
                'user': AuthUserSerializer(user).data,
                'daily_coupons_created': daily_coupons_created,
            },
            status=status.HTTP_200_OK,
        )


class StudentListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        students = Student.objects.all().order_by('user_id')
        return Response(StudentSerializer(students, many=True).data, status=status.HTTP_200_OK)


class StudentDetailView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, student_id):
        student = get_object_or_404(Student, student_id=student_id)
        return Response(StudentSerializer(student).data, status=status.HTTP_200_OK)




class CouponQrView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, coupon_id):

        coupon = get_object_or_404(Coupon, coupon_id=coupon_id)
        coupon.ensure_qr_image()
        return Response(
            CouponSerializer(coupon, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class CouponListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'student'):
            return Response({'detail': 'Only students have coupons.'}, status=status.HTTP_403_FORBIDDEN)

        coupons = list(
            Coupon.objects.select_related('student', 'student__mess')
            .filter(student=request.user.student)
            .order_by('-coupon_date', 'coupon_meal')
        )

        for coupon in coupons:
            if not coupon.qr_image:
                coupon.ensure_qr_image()

        return Response(CouponSerializer(coupons, many=True, context={'request': request}).data, status=status.HTTP_200_OK)


class CouponVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        qr_payload = request.data.get('qr_payload')
        if not qr_payload:
            return Response({'detail': 'qr_payload is required.'}, status=status.HTTP_400_BAD_REQUEST)

        coupon = get_object_or_404(Coupon.objects.select_related('student', 'student__mess'), qr_payload=qr_payload)
        return Response(
            {
                'valid': True,
                'coupon': CouponSerializer(coupon, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


class CouponExchangeRequestCreateView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'student'):
            return Response({'detail': 'Only students can view coupon exchange requests.'}, status=status.HTTP_403_FORBIDDEN)

        exchange_requests = (
            CouponTransferRequest.objects.select_related('coupon', 'requested_by', 'requested_to')
            .filter(requested_to=request.user.student)
            .order_by('-requested_at')
        )
        return Response(
            CouponExchangeRequestSerializer(exchange_requests, many=True, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = CouponExchangeCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        exchange_request = serializer.save()
        return Response(CouponExchangeRequestSerializer(exchange_request).data, status=status.HTTP_201_CREATED)


class CouponExchangeAcceptView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, exchange_id):
        exchange_request = get_object_or_404(
            CouponTransferRequest.objects.select_related('coupon', 'requested_by', 'requested_to'),
            pk=exchange_id,
        )

        if not request.user.is_authenticated or not hasattr(request.user, 'student'):
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        if exchange_request.requested_to_id != request.user.student.user_id:
            return Response({'detail': 'Only the requested recipient can accept this exchange.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            exchange_request.accept()

        exchange_request.refresh_from_db()
        return Response(CouponExchangeRequestSerializer(exchange_request).data, status=status.HTTP_200_OK)


class CouponExchangeRejectView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, exchange_id):
        exchange_request = get_object_or_404(
            CouponTransferRequest.objects.select_related('coupon', 'requested_by', 'requested_to'),
            pk=exchange_id,
        )

        if not request.user.is_authenticated or not hasattr(request.user, 'student'):
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        if exchange_request.requested_to_id != request.user.student.user_id:
            return Response({'detail': 'Only the requested recipient can reject this exchange.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            exchange_request.reject()

        exchange_request.refresh_from_db()
        return Response(CouponExchangeRequestSerializer(exchange_request).data, status=status.HTTP_200_OK)


class MessMenuListCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        menus = MessMenu.objects.select_related('mess').prefetch_related('items').order_by(
            'mess__hostel_id', 'mess__name', 'day_of_week', 'meal'
        )

        hostel_id = request.query_params.get('hostel_id')
        day_of_week = request.query_params.get('day_of_week')
        meal = request.query_params.get('meal')

        if hostel_id:
            menus = menus.filter(mess__hostel_id=hostel_id)
        if day_of_week:
            menus = menus.filter(day_of_week=day_of_week)
        if meal:
            menus = menus.filter(meal=meal)

        return Response(MessMenuSerializer(menus, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = MessMenuCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        menu = serializer.save()
        return Response(MessMenuSerializer(menu).data, status=status.HTTP_201_CREATED)


class MessMenuDetailView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, menu_id):
        menu = get_object_or_404(MessMenu.objects.select_related('mess').prefetch_related('items'), pk=menu_id)
        return Response(MessMenuSerializer(menu).data, status=status.HTTP_200_OK)


class MessListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        messes = Mess.objects.order_by('hostel_id', 'name')
        return Response(MessSerializer(messes, many=True).data, status=status.HTTP_200_OK)


class FeedbackListCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        feedbacks = Feedback.objects.select_related('raised_by').order_by('-id')

        raised_by_id = request.query_params.get('raised_by_id')
        coupon_meal = request.query_params.get('coupon_meal')
        hostel_id = request.query_params.get('hostel_id')

        if raised_by_id:
            feedbacks = feedbacks.filter(raised_by_id=raised_by_id)
        if coupon_meal:
            feedbacks = feedbacks.filter(coupon_meal=coupon_meal)
        if hostel_id:
            feedbacks = feedbacks.filter(hostel_id=hostel_id)

        return Response(FeedbackSerializer(feedbacks, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = FeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = serializer.save()
        return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


class DailyMealRatingSummaryView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        date_str = request.query_params.get('date')

        if date_str:
            try:
                target_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'detail': 'date must be in YYYY-MM-DD format.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = timezone.localdate()

        rating_rows = {
            (row['hostel_id'], row['coupon_meal']): row
            for row in (
                Feedback.objects.filter(created_at__date=target_date)
                .values('hostel_id', 'coupon_meal')
                .annotate(
                    average_rating=Avg('rating'),
                    rated_count=Count('id'),
                )
            )
        }

        data = []
        for mess in Mess.objects.order_by('hostel_id', 'name'):
            meals = []
            for meal_code, meal_label in CouponMeal.choices:
                rating_row = rating_rows.get((mess.hostel_id, meal_code))
                average_rating = rating_row['average_rating'] if rating_row else None
                meals.append(
                    {
                        'meal': meal_code,
                        'meal_name': meal_label,
                        'average_rating': round(float(average_rating), 2) if average_rating is not None else None,
                        'rated_count': rating_row['rated_count'] if rating_row else 0,
                    }
                )

            data.append(
                {
                    'hostel_id': mess.hostel_id,
                    'mess_id': mess.id,
                    'mess_name': mess.name,
                    'date': target_date.isoformat(),
                    'meals': meals,
                }
            )

        return Response(data, status=status.HTTP_200_OK)


class ComplaintListCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        complaints = Complaint.objects.select_related('raised_by', 'mess').order_by('-id')

        raised_by_id = request.query_params.get('raised_by_id')
        hostel_id = request.query_params.get('hostel_id')
        coupon_meal = request.query_params.get('coupon_meal')

        if raised_by_id:
            complaints = complaints.filter(raised_by_id=raised_by_id)
        if hostel_id:
            complaints = complaints.filter(mess__hostel_id=hostel_id)
        if coupon_meal:
            complaints = complaints.filter(coupon_meal=coupon_meal)

        return Response(ComplaintSerializer(complaints, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ComplaintSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        complaint = serializer.save()
        return Response(ComplaintSerializer(complaint).data, status=status.HTTP_201_CREATED)


class MessNameListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        mess_names = list(Mess.objects.order_by('name').values_list('name', flat=True))
        return Response({'mess_names': mess_names}, status=status.HTTP_200_OK)
