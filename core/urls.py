from django.urls import path

from .views import (
    ComplaintListCreateView,
    CouponQrView,
    CouponVerifyView,
    FeedbackListCreateView,
    health_check,
    LoginView,
    MessMenuDetailView,
    MessMenuListCreateView,
    CouponTransferAcceptView,
    CouponTransferRejectView,
    CouponTransferRequestCreateView,
    SignupView,
    StudentDetailView,
    StudentListView,
)


urlpatterns = [
    path('', health_check, name='health-check'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('students/', StudentListView.as_view(), name='student-list'),
    path('students/<str:student_id>/', StudentDetailView.as_view(), name='student-detail'),
    path('coupons/<str:coupon_id>/qr/', CouponQrView.as_view(), name='coupon-qr'),
    path('coupons/verify/', CouponVerifyView.as_view(), name='coupon-verify'),
    path('coupon-transfer-requests/', CouponTransferRequestCreateView.as_view(), name='coupon-transfer-request-create'),
    path(
        'coupon-transfer-requests/<int:transfer_id>/accept/',
        CouponTransferAcceptView.as_view(),
        name='coupon-transfer-request-accept',
    ),
    path(
        'coupon-transfer-requests/<int:transfer_id>/reject/',
        CouponTransferRejectView.as_view(),
        name='coupon-transfer-request-reject',
    ),
    path('mess-menus/', MessMenuListCreateView.as_view(), name='mess-menu-list-create'),
    path('mess-menus/<int:menu_id>/', MessMenuDetailView.as_view(), name='mess-menu-detail'),
    path('feedbacks/', FeedbackListCreateView.as_view(), name='feedback-list-create'),
    path('complaints/', ComplaintListCreateView.as_view(), name='complaint-list-create'),
]
