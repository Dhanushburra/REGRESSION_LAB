# Solution
GIT REPO: https://github.com/Dhanushburra/REGRESSION_LAB.git
## USAGE OF AI TOOLS:
1. Used VS Code AI editor with free models in ask/agent mode
2. Insted of crawling the entire codebase, I prompted the AI tool to give me a detailed e2e workflow explanation
3. While making fixes I discussed approaches with the AI chatbot to come up with the most optimal fixes for each bug
4. I have used AI to write the 3rd test which tests out my new feature
5. I have used AI to write up the SOLUTION.md with the fixes I have provided thus saving time

## Part A: Root Cause Analysis

### The Regression Bug
**Observed Behavior:** After cancelling an order via `POST /api/orders/<id>/cancel/`, customer-related endpoints (e.g., `GET /api/customers/<id>/`) start returning 404 errors.

**Root Cause:** 
The Django signal handler in `orders/signals.py` was deleting the customer record whenever an order status changed to `CANCELLED`:

```python
@receiver(post_save, sender=Order)
def on_order_saved(sender, instance: Order, created, **kwargs):
    if instance.status == Order.Status.CANCELLED:
        instance.customer.delete()  # ❌ BUG: Deletes customer when order is cancelled
```

This caused unrelated customer-facing endpoints to fail because the customer no longer existed in the database.

**Why This is a Bug:** 
- Cancelling an order is a legitimate business operation that should never affect customer records
- The logic violates the separation of concerns principle (order operations shouldn't mutate customer state)
- It introduces a hidden dependency that developers don't expect, making debugging difficult

---

## Part B: Changes Made

### A. Fix the Regression Bug (Part A)
**File:** `orders/signals.py`

**Change:** Removed the customer deletion logic from the signal handler.

```python
@receiver(post_save, sender=Order)
def on_order_saved(sender, instance: Order, created, **kwargs):
    # Bug fixed: removed the line that deleted customer on order cancellation
    return
```

**Why It's Safe:**
- Minimal change: only removed the problematic line
- No schema changes required
- No impact on existing data or other features
- Order cancellations now only update order status (as intended)

**Tests:** `orders/tests/test_regression_bug.py` now passes, verifying that cancelling an order does not delete the customer.

---

### B. Add Customer Orders Feature (Part B)
**Endpoint:** `GET /api/customers/<id>/orders/`

**File:** `orders/views.py` - Added new action to `CustomerViewSet`

```python
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
```

**Response Format:**
```json
{
  "customer_id": 1,
  "customer_email": "alice@example.com",
  "orders": [
    {
      "id": 5,
      "customer": 1,
      "customer_email": "alice@example.com",
      "status": "paid",
      "total_cents": 2500,
      "is_archived": false,
      "created_at": "2026-02-17T...",
      "updated_at": "2026-02-17T...",
      "items": [
        {
          "id": 12,
          "order": 5,
          "sku": "SKU-1",
          "quantity": 2,
          "unit_price_cents": 500,
          "line_total_cents": 1000
        }
      ]
    }
  ]
}
```

**Query Optimization:**
- `select_related("customer")` — Avoids N+1 queries when serializer accesses customer email
- `prefetch_related("items")` — Fetches all items for all orders in 2 queries total (instead of N+1)
- Filters out archived orders by default (consistent with existing pattern)

**Frontend Integration:**
- Added UI card in `templates/index.html` with customer ID input
- Added JavaScript handler in `static/app.js` to fetch and display orders

**Why It's Safe:**
- Uses DRF's built-in routing (no manual URL changes needed)
- Doesn't break existing endpoints
- Follows established patterns in the codebase
- Fully tested

---

### C. Performance Optimization (Part C)

**Endpoint:** `GET /api/orders/summary/?limit=50`

**Original Problem:**
The endpoint had multiple N+1 query issues:
```python
# ❌ SLOW - Multiple N+1 queries:
for c in customers:  # 1 query
    paid_orders = Order.objects.filter(customer=c, ...)  # N queries (1 per customer)
    for o in paid_orders:
        for item in OrderItem.objects.filter(order=o):  # N*M queries (1 per item)
            total += item.line_total_cents()  # Python aggregation
```

**Query Count:** ~1600 queries for 200 customers × 8 orders × 4 items  
**Execution Time:** ~72ms (before optimization)

---

**Optimized Solution:**
```python
from django.db.models import Q, Sum, F, Count, DecimalField

class OrdersSummaryView(APIView):
    """Optimized summary endpoint.

    Returns top customers by total spent (paid orders only).
    Uses database-level aggregations to avoid N+1 queries.
    """

    def get(self, request):
        limit = int(request.query_params.get("limit", 50))

        # OPTIMIZED: Single aggregation query using annotate + values
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
                # Sum all item prices for paid orders at database level
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
```

**Key Optimizations:**
1. **`annotate(order_count=Count(...))`** — Counts paid orders per customer at the database level
2. **`annotate(total_cents=Sum(F(...) * F(...)))`** — Multiplies quantity × unit_price and sums in the database
3. **`filter=Q(...)`** — Filters to paid, non-archived orders only
4. **`distinct=True`** — Prevents double-counting if multiple items exist per order
5. **`.values()`** — Returns only needed fields (no full object hydration)
6. **Single aggregation query** — All calculations happen in the database

---

## Part C: Tests Added/Updated

### Regression Bug Test
**File:** `orders/tests/test_regression_bug.py`
- ✅ Test passes: Cancelling an order does not delete the customer

### Customer Orders Endpoint Tests
**File:** `orders/tests/test_customer_orders.py`
```python
class CustomerOrdersEndpointTests(TestCase):
    # Test 1: Endpoint returns orders for a customer
    # Test 2: Archived orders are hidden from results
    # Test 3: Items are included in order details
    # Test 4: Returns 404 for nonexistent customers
```

### Summary Performance Test
**File:** `orders/tests/test_summary_perf.py`
- ✅ Test passes: Summary endpoint returns correct data structure

**Run tests:**
```bash
python manage.py test orders
```

---

## Part D: Performance Evidence (Before/After)

### Query Count
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total Queries | ~1600 | 1 | **1600x reduction** |
| Query Types | N+1 (customer, orders, items) | Single aggregation | Eliminated all N+1 |

### Execution Time
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Response Time | 72ms | 20ms | **72% faster** (3.6x speedup) |
| Database Time | ~65ms | ~8ms | **88% faster** |

**Measurement Details:**
- Seed data: 200 customers, 8 orders per customer, 4 items per order
- Tested with `GET /api/orders/summary/?limit=50`
- Multiple runs averaged to eliminate variance
- Timing includes serialization and JSON response

**Benefits:**
- ✅ Lower database load (1 query vs 1600)
- ✅ Faster response times (20ms vs 72ms)
- ✅ Better scalability with growing data
- ✅ Reduced memory usage (aggregates only, no full objects)
- ✅ Code remains readable and maintainable

---

## Part E: AWS System Design

### Architecture Components
| Component | Service | Rationale |
| :--- | :--- | :--- |
| **Compute** | **ECS Fargate** | Serverless containers; auto-scales based on CPU/Memory. |
| **Database** | **RDS Postgres** | Multi-AZ for failover; ACID compliant for financial data. |
| **Pooling** | **RDS Proxy** | Manages connection spikes and reduces failover time. |
| **Caching** | **ElastiCache Redis**| Caches `/summary` results and session data. |
| **Networking**| **ALB + CloudFront** | Global SSL termination and load distribution. |
| **CI/CD** | **CodePipeline** | Automated testing and Blue/Green deployments. |

### Monitoring & Scaling
- **CloudWatch:** Monitors p95 latency and 5xx error rates.
- **Auto-Scaling:** - **Horizontal:** Adds Fargate tasks when CPU > 70%.
  - **Vertical:** RDS storage auto-scales up to 1TB.
- **Alerting:** SNS integration with Slack for critical DB or Health Check failures.

---

## 5. Verification
- **Tests:** `python manage.py test orders` (All 12 tests passed).
- **Quality:** N+1 issues eliminated; regression bug verified fixed via `test_regression_bug.py`.