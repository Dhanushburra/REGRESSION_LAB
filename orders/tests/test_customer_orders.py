from django.test import TestCase
from rest_framework.test import APIClient
from orders.models import Customer, Order, OrderItem

class CustomerOrdersEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = Customer.objects.create(
            name="Test Customer",
            email="test@example.com",
            is_active=True
        )

    def test_customer_orders_endpoint_returns_orders(self):
        """Test that GET /api/customers/<id>/orders/ returns customer's orders."""
        # Create some orders
        order1 = Order.objects.create(
            customer=self.customer,
            status=Order.Status.PAID,
            total_cents=1000
        )
        order2 = Order.objects.create(
            customer=self.customer,
            status=Order.Status.DRAFT,
            total_cents=2000
        )
        
        # Add items to first order
        OrderItem.objects.create(
            order=order1,
            sku="SKU-1",
            quantity=2,
            unit_price_cents=500
        )
        
        # Fetch customer orders
        res = self.client.get(f"/api/customers/{self.customer.id}/orders/")
        
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        
        # Verify response structure
        self.assertIn("customer_id", payload)
        self.assertIn("customer_email", payload)
        self.assertIn("orders", payload)
        
        # Verify correct customer
        self.assertEqual(payload["customer_id"], self.customer.id)
        self.assertEqual(payload["customer_email"], "test@example.com")
        
        # Verify orders are returned
        self.assertEqual(len(payload["orders"]), 2)

    def test_customer_orders_hides_archived(self):
        """Test that archived orders are hidden from the endpoint."""
        order1 = Order.objects.create(
            customer=self.customer,
            status=Order.Status.PAID
        )
        order2 = Order.objects.create(
            customer=self.customer,
            status=Order.Status.PAID,
            is_archived=True  # Archived
        )
        
        res = self.client.get(f"/api/customers/{self.customer.id}/orders/")
        
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        
        # Only non-archived order should be returned
        self.assertEqual(len(payload["orders"]), 1)
        self.assertEqual(payload["orders"][0]["id"], order1.id)

    def test_customer_orders_includes_items(self):
        """Test that orders include their items."""
        order = Order.objects.create(
            customer=self.customer,
            status=Order.Status.PAID
        )
        OrderItem.objects.create(
            order=order,
            sku="SKU-ABC",
            quantity=3,
            unit_price_cents=999
        )
        OrderItem.objects.create(
            order=order,
            sku="SKU-XYZ",
            quantity=1,
            unit_price_cents=1500
        )
        
        res = self.client.get(f"/api/customers/{self.customer.id}/orders/")
        
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        
        # Verify items are included
        order_data = payload["orders"][0]
        self.assertEqual(len(order_data["items"]), 2)
        self.assertEqual(order_data["items"][0]["sku"], "SKU-ABC")
        self.assertEqual(order_data["items"][1]["sku"], "SKU-XYZ")

    def test_customer_orders_with_nonexistent_customer(self):
        """Test that accessing orders for nonexistent customer returns 404."""
        res = self.client.get("/api/customers/99999/orders/")
        self.assertEqual(res.status_code, 404)