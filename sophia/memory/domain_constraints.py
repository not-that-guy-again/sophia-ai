from sophia.memory.store import MemoryStore


def get_domain_constraints(store: MemoryStore) -> dict:
    """Return the domain constraints from the memory store."""
    return store.domain_constraints
