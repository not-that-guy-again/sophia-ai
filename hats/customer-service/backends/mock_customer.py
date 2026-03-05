from sophia.services.customer import CustomerService
from sophia.services.models import Customer, CustomerHistory

from .mock_data import MockDataStore


class MockCustomerService(CustomerService):
    async def get_customer(self, customer_id: str) -> Customer | None:
        return MockDataStore.customers.get(customer_id)

    async def search_customers(self, query: str) -> list[Customer]:
        q = query.lower()
        return [
            c
            for c in MockDataStore.customers.values()
            if q in c.name.lower() or q in c.email.lower() or (c.phone and q in c.phone)
        ]

    async def get_customer_history(self, customer_id: str) -> CustomerHistory:
        customer = MockDataStore.customers.get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        orders = [o for o in MockDataStore.orders.values() if o.customer_id == customer_id]
        orders.sort(key=lambda o: o.created_at, reverse=True)

        returns = [
            r
            for r in MockDataStore.returns.values()
            if any(
                o.customer_id == customer_id
                for o in MockDataStore.orders.values()
                if o.order_id == r.order_id
            )
        ]

        total_refunded = sum(r.refund_amount or 0.0 for r in returns)

        return CustomerHistory(
            customer=customer,
            orders=orders,
            returns=returns,
            total_refunded=total_refunded,
        )
