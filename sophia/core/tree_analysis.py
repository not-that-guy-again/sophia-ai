"""Pure analysis functions for consequence trees. No LLM calls."""

from sophia.core.consequence import ConsequenceNode, ConsequenceTree


def get_worst_path(tree: ConsequenceTree) -> list[ConsequenceNode]:
    """Return the path from root to the highest-harm terminal node.

    Traverses all branches depth-first and returns the path (list of nodes
    from root to terminal) ending at the terminal with the lowest harm_benefit.
    """
    worst_path: list[ConsequenceNode] = []
    worst_score = float("inf")

    def _dfs(node: ConsequenceNode, current_path: list[ConsequenceNode]) -> None:
        nonlocal worst_path, worst_score
        current_path = current_path + [node]

        if node.is_terminal:
            if node.harm_benefit < worst_score:
                worst_score = node.harm_benefit
                worst_path = current_path
        else:
            for child in node.children:
                _dfs(child, current_path)

    for root in tree.root_nodes:
        _dfs(root, [])

    return worst_path


def get_expected_harm(tree: ConsequenceTree) -> float:
    """Compute probability-weighted expected harm across all terminal nodes.

    Each terminal contributes: harm_benefit * product(probability along path).
    """
    total = 0.0

    def _dfs(node: ConsequenceNode, cumulative_prob: float) -> None:
        nonlocal total
        prob = cumulative_prob * node.probability

        if node.is_terminal:
            total += node.harm_benefit * prob
        else:
            for child in node.children:
                _dfs(child, prob)

    for root in tree.root_nodes:
        _dfs(root, 1.0)

    return total


def has_catastrophic_branch(
    tree: ConsequenceTree,
    threshold: float = -0.8,
) -> bool:
    """Check if any plausible node has harm_benefit at or below threshold.

    A node is considered plausible if its probability exceeds 0.1.
    Scans ALL nodes (not just terminals) because catastrophic intermediate
    consequences matter even if downstream nodes partially recover.
    """

    def _check(nodes: list[ConsequenceNode]) -> bool:
        for node in nodes:
            if node.probability > 0.1 and node.harm_benefit <= threshold:
                return True
            if _check(node.children):
                return True
        return False

    return _check(tree.root_nodes)


def get_stakeholder_impact(
    tree: ConsequenceTree,
    stakeholder_id: str,
) -> float:
    """Aggregate probability-weighted impact for a specific stakeholder.

    Sums harm_benefit * probability for all nodes where stakeholder_id
    appears in stakeholders_affected.
    """
    total = 0.0

    def _sum(nodes: list[ConsequenceNode]) -> None:
        nonlocal total
        for node in nodes:
            if stakeholder_id in node.stakeholders_affected:
                total += node.harm_benefit * node.probability
            _sum(node.children)

    _sum(tree.root_nodes)
    return total


def classify_risk(
    tree: ConsequenceTree,
    catastrophic_threshold: float = -0.8,
) -> str:
    """Phase 2 temporary heuristic for risk classification.

    Returns:
        "RED" if any plausible node has catastrophic harm
        "YELLOW" if expected harm is below -0.3
        "GREEN" otherwise
    """
    if has_catastrophic_branch(tree, threshold=catastrophic_threshold):
        return "RED"

    if get_expected_harm(tree) < -0.3:
        return "YELLOW"

    return "GREEN"
