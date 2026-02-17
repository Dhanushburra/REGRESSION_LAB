from django.db.models import Q, Sum, F, Count, DecimalField
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer, Order, OrderItem
from .serializers import CustomerSerializer, OrderSerializer, OrderItemSerializer

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by("-id")
    serializer_class = CustomerSerializer

    @action(detail=True, methods=["get"])
    def orders(self, request, pk=None):
        """GET /api/customers/<id>/orders/ — customer's non-archived orders with items."""
        customer = self.get_object()

        orders_qs = (
            Order.objects
            .filter(customer=customer, is_archived=False)
            .select_related("customer")    # avoids per-order customer fetches
            .prefetch_related("items")     # fetch items for all orders in one go
            .order_by("-id")
        )

        serializer = OrderSerializer(orders_qs, many=True, context={"request": request})
        return Response({
            "customer_id": customer.id,
            "customer_email": customer.email,
            "orders": serializer.data,
        })
    
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().order_by("-id")
    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Default behavior: hide archived orders in list views.
        # (Note: detail views should still retrieve by id.)
        if self.action == "list":
            qs = qs.filter(is_archived=False)
        return qs

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        return Response({"id": order.id, "status": order.status})

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        order = self.get_object()
        order.is_archived = True
        order.save(update_fields=["is_archived", "updated_at"])
        return Response({"id": order.id, "is_archived": order.is_archived})

class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all().order_by("-id")
    serializer_class = OrderItemSerializer

class OrdersSummaryView(APIView):
    """Optimized summary endpoint.

    Returns top customers by total spent (paid orders only).
    Uses database-level aggregations to avoid N+1 queries.
    """

    def get(self, request):
        limit = int(request.query_params.get("limit", 50))

        # OPTIMIZED: Single aggregation query using annotate + values
        # This computes order counts and totals at the database level
        customer_summaries = (
            Customer.objects
            .filter(is_active=True)
            .annotate(
                # Count paid orders (non-archived)
                order_count=Count(
                    "orders",
                    filter=Q(orders__status=Order.Status.PAID, orders__is_archived=False),
                    distinct=True
                ),
                # Sum all item prices for paid orders (quantity * unit_price)
                # F() allows field arithmetic in the database
                total_cents=Sum(
                    F("orders__items__quantity") * F("orders__items__unit_price_cents"),
                    filter=Q(orders__status=Order.Status.PAID, orders__is_archived=False),
                    output_field=DecimalField(),
                )
            )
            .values("id", "email", "order_count", "total_cents")
            .order_by("-total_cents")[:limit]
        )

        rows = []
        for summary in customer_summaries:
            rows.append({
                "customer_id": summary["id"],
                "email": summary["email"],
                "order_count": summary["order_count"] or 0,
                "total_cents": int(summary["total_cents"] or 0),
            })

        return Response({"limit": limit, "rows": rows})