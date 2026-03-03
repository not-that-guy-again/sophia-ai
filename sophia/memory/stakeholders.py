from sophia.memory.store import MemoryStore


def get_stakeholders(store: MemoryStore) -> dict:
    """Return the stakeholder registry from the memory store."""
    return store.stakeholders
