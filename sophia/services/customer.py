from abc import ABC, abstractmethod

from sophia.services.models import Customer, CustomerHistory


class CustomerService(ABC):
    @abstractmethod
    async def get_customer(self, customer_id: str) -> Customer | None: ...

    @abstractmethod
    async def search_customers(self, query: str) -> list[Customer]: ...

    @abstractmethod
    async def get_customer_history(self, customer_id: str) -> CustomerHistory: ...
