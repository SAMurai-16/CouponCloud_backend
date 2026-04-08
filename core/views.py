from django.contrib.auth import login
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Complaint, Coupon, CouponTransferRequest, Feedback, MessMenu, Student
from .serializers import (
    AuthUserSerializer,
    ComplaintSerializer,
    CouponSerializer,
    CouponTransferCreateSerializer,
    CouponTransferRequestSerializer,
    FeedbackSerializer,
    LoginSerializer,
    MessMenuCreateSerializer,
    MessMenuSerializer,
    SignupSerializer,
    StudentSerializer,
)


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
        return Response(
            {
                'message': 'Login successful.',
                'user': AuthUserSerializer(user).data,
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


class CouponTransferRequestCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CouponTransferCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        transfer_request = serializer.save()
        return Response(CouponTransferRequestSerializer(transfer_request).data, status=status.HTTP_201_CREATED)


class CouponTransferAcceptView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, transfer_id):
        transfer_request = get_object_or_404(
            CouponTransferRequest.objects.select_related('coupon', 'requested_by', 'requested_to'),
            pk=transfer_id,
        )

        if not request.user.is_authenticated or not hasattr(request.user, 'student'):
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        if transfer_request.requested_to_id != request.user.student.user_id:
            return Response({'detail': 'Only the requested recipient can accept this transfer.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            transfer_request.accept()

        transfer_request.refresh_from_db()
        return Response(CouponTransferRequestSerializer(transfer_request).data, status=status.HTTP_200_OK)


class CouponTransferRejectView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, transfer_id):
        transfer_request = get_object_or_404(
            CouponTransferRequest.objects.select_related('coupon', 'requested_by', 'requested_to'),
            pk=transfer_id,
        )

        if not request.user.is_authenticated or not hasattr(request.user, 'student'):
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        if transfer_request.requested_to_id != request.user.student.user_id:
            return Response({'detail': 'Only the requested recipient can reject this transfer.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            transfer_request.reject()

        transfer_request.refresh_from_db()
        return Response(CouponTransferRequestSerializer(transfer_request).data, status=status.HTTP_200_OK)


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


class FeedbackListCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        feedbacks = Feedback.objects.select_related('raised_by').order_by('-id')

        raised_by_id = request.query_params.get('raised_by_id')
        coupon_meal = request.query_params.get('coupon_meal')

        if raised_by_id:
            feedbacks = feedbacks.filter(raised_by_id=raised_by_id)
        if coupon_meal:
            feedbacks = feedbacks.filter(coupon_meal=coupon_meal)

        return Response(FeedbackSerializer(feedbacks, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = FeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = serializer.save()
        return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


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
