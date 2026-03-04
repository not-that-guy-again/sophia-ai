from sophia.services.customer import CustomerService
from sophia.services.mcp.adapter import MCPServiceAdapter
from sophia.services.mcp.client import MCPClient
from sophia.services.models import Customer, CustomerHistory


class MCPCustomerService(CustomerService):
    def __init__(self, client: MCPClient, tool_mapping: dict):
        self.adapter = MCPServiceAdapter(client, tool_mapping)

    async def get_customer(self, customer_id: str) -> Customer | None:
        return await self.adapter._call("get_customer", customer_id=customer_id)

    async def search_customers(self, query: str) -> list[Customer]:
        return await self.adapter._call("search_customers", query=query)

    async def get_customer_history(self, customer_id: str) -> CustomerHistory:
        return await self.adapter._call(
            "get_customer_history", customer_id=customer_id
        )
