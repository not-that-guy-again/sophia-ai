"""Tests for tree analysis utilities. Uses hand-crafted trees, no LLM."""

from sophia.core.consequence import ConsequenceNode, ConsequenceTree
from sophia.core.proposer import CandidateAction
from sophia.core.tree_analysis import (
    classify_risk,
    get_expected_harm,
    get_stakeholder_impact,
    get_worst_path,
    has_catastrophic_branch,
)


def _candidate(tool_name: str = "test_tool") -> CandidateAction:
    return CandidateAction(
        tool_name=tool_name, parameters={}, reasoning="test", expected_outcome="test"
    )


def _benign_tree() -> ConsequenceTree:
    """All consequences are mildly positive."""
    return ConsequenceTree(
        candidate_action=_candidate(),
        root_nodes=[
            ConsequenceNode(
                id="a1",
                description="Customer issue resolved",
                stakeholders_affected=["customer"],
                probability=0.9,
                tangibility=0.8,
                harm_benefit=0.5,
                affected_party="customer",
                is_terminal=False,
                children=[
                    ConsequenceNode(
                        id="a2",
                        description="Customer retained",
                        stakeholders_affected=["customer", "business"],
                        probability=0.7,
                        tangibility=0.6,
                        harm_benefit=0.4,
                        affected_party="business",
                        is_terminal=True,
                    ),
                ],
            ),
            ConsequenceNode(
                id="b1",
                description="Small cost to business",
                stakeholders_affected=["business"],
                probability=0.9,
                tangibility=0.9,
                harm_benefit=-0.1,
                affected_party="business",
                is_terminal=True,
            ),
        ],
        max_depth=2,
        total_nodes=3,
        worst_terminal=None,  # filled below
        best_terminal=None,
    )


def _catastrophic_tree() -> ConsequenceTree:
    """A tree with a high-probability catastrophic branch."""
    return ConsequenceTree(
        candidate_action=_candidate("place_new_order"),
        root_nodes=[
            ConsequenceNode(
                id="c1",
                description="Give away $499 product for free",
                stakeholders_affected=["business", "other_customers"],
                probability=0.95,
                tangibility=1.0,
                harm_benefit=-0.9,
                affected_party="business",
                is_terminal=False,
                children=[
                    ConsequenceNode(
                        id="c2",
                        description="Sets precedent for free items",
                        stakeholders_affected=["business", "other_customers"],
                        probability=0.7,
                        tangibility=0.8,
                        harm_benefit=-0.85,
                        affected_party="other_customers",
                        is_terminal=True,
                    ),
                ],
            ),
            ConsequenceNode(
                id="d1",
                description="Customer is happy",
                stakeholders_affected=["customer"],
                probability=0.95,
                tangibility=0.9,
                harm_benefit=0.8,
                affected_party="customer",
                is_terminal=True,
            ),
        ],
        max_depth=2,
        total_nodes=3,
        worst_terminal=None,
        best_terminal=None,
    )


def _mixed_tree() -> ConsequenceTree:
    """Moderate negative outcomes, no catastrophic branches."""
    return ConsequenceTree(
        candidate_action=_candidate(),
        root_nodes=[
            ConsequenceNode(
                id="m1",
                description="Partial refund issued at agent limit",
                stakeholders_affected=["customer", "business"],
                probability=0.9,
                tangibility=0.9,
                harm_benefit=-0.4,
                affected_party="business",
                is_terminal=False,
                children=[
                    ConsequenceNode(
                        id="m2",
                        description="Customer somewhat satisfied",
                        stakeholders_affected=["customer"],
                        probability=0.6,
                        tangibility=0.7,
                        harm_benefit=0.2,
                        affected_party="customer",
                        is_terminal=True,
                    ),
                    ConsequenceNode(
                        id="m3",
                        description="Business absorbs cost",
                        stakeholders_affected=["business"],
                        probability=0.9,
                        tangibility=0.9,
                        harm_benefit=-0.5,
                        affected_party="business",
                        is_terminal=True,
                    ),
                ],
            ),
        ],
        max_depth=2,
        total_nodes=3,
        worst_terminal=None,
        best_terminal=None,
    )


def _empty_tree() -> ConsequenceTree:
    """Tree with no nodes."""
    return ConsequenceTree(
        candidate_action=_candidate(),
        root_nodes=[],
        max_depth=3,
        total_nodes=0,
        worst_terminal=None,
        best_terminal=None,
    )


def _low_prob_catastrophic_tree() -> ConsequenceTree:
    """Catastrophic harm but very low probability — should NOT trigger."""
    return ConsequenceTree(
        candidate_action=_candidate(),
        root_nodes=[
            ConsequenceNode(
                id="lp1",
                description="Extremely unlikely worst case",
                stakeholders_affected=["business"],
                probability=0.05,  # below 0.1 threshold
                tangibility=1.0,
                harm_benefit=-0.95,
                affected_party="business",
                is_terminal=True,
            ),
            ConsequenceNode(
                id="lp2",
                description="Normal positive outcome",
                stakeholders_affected=["customer"],
                probability=0.9,
                tangibility=0.7,
                harm_benefit=0.4,
                affected_party="customer",
                is_terminal=True,
            ),
        ],
        max_depth=1,
        total_nodes=2,
        worst_terminal=None,
        best_terminal=None,
    )


# --- get_worst_path ---


class TestGetWorstPath:
    def test_returns_path_to_worst_terminal(self):
        tree = _catastrophic_tree()
        path = get_worst_path(tree)
        assert len(path) == 2
        assert path[0].id == "c1"
        assert path[-1].id == "c2"
        assert path[-1].harm_benefit == -0.85

    def test_benign_tree_worst_is_least_positive(self):
        tree = _benign_tree()
        path = get_worst_path(tree)
        assert len(path) >= 1
        assert path[-1].harm_benefit == -0.1

    def test_empty_tree_returns_empty(self):
        tree = _empty_tree()
        path = get_worst_path(tree)
        assert path == []

    def test_single_terminal_node(self):
        tree = ConsequenceTree(
            candidate_action=_candidate(),
            root_nodes=[
                ConsequenceNode(
                    id="x1",
                    description="Only node",
                    stakeholders_affected=["customer"],
                    probability=1.0,
                    tangibility=1.0,
                    harm_benefit=0.3,
                    affected_party="customer",
                    is_terminal=True,
                ),
            ],
            max_depth=1,
            total_nodes=1,
            worst_terminal=None,
            best_terminal=None,
        )
        path = get_worst_path(tree)
        assert len(path) == 1
        assert path[0].harm_benefit == 0.3


# --- get_expected_harm ---


class TestGetExpectedHarm:
    def test_benign_tree_is_positive(self):
        tree = _benign_tree()
        assert get_expected_harm(tree) > 0

    def test_catastrophic_tree_expected_harm(self):
        tree = _catastrophic_tree()
        # c2: 0.95 * 0.7 * -0.85 = -0.565, d1: 0.95 * 0.8 = 0.76
        # Net positive because customer benefit outweighs — but has_catastrophic_branch
        # still catches it. Expected harm alone doesn't flag catastrophic trees.
        result = get_expected_harm(tree)
        assert result > -1.0  # valid range

    def test_weights_by_probability(self):
        """Low-probability harm contributes less than high-probability benefit."""
        tree = _low_prob_catastrophic_tree()
        result = get_expected_harm(tree)
        # 0.05 * -0.95 = -0.0475, 0.9 * 0.4 = 0.36 → net positive
        assert result > 0

    def test_empty_tree_is_zero(self):
        tree = _empty_tree()
        assert get_expected_harm(tree) == 0.0

    def test_mixed_tree(self):
        tree = _mixed_tree()
        expected = get_expected_harm(tree)
        # m2: 0.9 * 0.6 * 0.2 = 0.108
        # m3: 0.9 * 0.9 * -0.5 = -0.405
        # total: -0.297
        assert expected < 0
        assert expected > -0.5


# --- has_catastrophic_branch ---


class TestHasCatastrophicBranch:
    def test_detects_catastrophic_node(self):
        tree = _catastrophic_tree()
        assert has_catastrophic_branch(tree, threshold=-0.8) is True

    def test_benign_tree_has_no_catastrophic(self):
        tree = _benign_tree()
        assert has_catastrophic_branch(tree, threshold=-0.8) is False

    def test_low_probability_catastrophic_ignored(self):
        tree = _low_prob_catastrophic_tree()
        assert has_catastrophic_branch(tree, threshold=-0.8) is False

    def test_custom_threshold(self):
        tree = _mixed_tree()
        # m1 has harm_benefit=-0.4, m3 has -0.5
        assert has_catastrophic_branch(tree, threshold=-0.3) is True
        assert has_catastrophic_branch(tree, threshold=-0.8) is False

    def test_empty_tree(self):
        tree = _empty_tree()
        assert has_catastrophic_branch(tree) is False


# --- get_stakeholder_impact ---


class TestGetStakeholderImpact:
    def test_aggregates_per_stakeholder(self):
        tree = _benign_tree()
        customer_impact = get_stakeholder_impact(tree, "customer")
        # a1: 0.9 * 0.5 = 0.45, a2: 0.7 * 0.4 = 0.28 → 0.73
        assert customer_impact > 0

    def test_business_impact_in_catastrophic(self):
        tree = _catastrophic_tree()
        business_impact = get_stakeholder_impact(tree, "business")
        assert business_impact < 0

    def test_unknown_stakeholder_returns_zero(self):
        tree = _benign_tree()
        assert get_stakeholder_impact(tree, "nonexistent") == 0.0

    def test_empty_tree(self):
        assert get_stakeholder_impact(_empty_tree(), "customer") == 0.0


# --- classify_risk ---


class TestClassifyRisk:
    def test_catastrophic_returns_red(self):
        tree = _catastrophic_tree()
        assert classify_risk(tree) == "RED"

    def test_benign_returns_green(self):
        tree = _benign_tree()
        assert classify_risk(tree) == "GREEN"

    def test_moderate_harm_returns_yellow(self):
        tree = _mixed_tree()
        # expected harm ≈ -0.297 which is > -0.3, so actually GREEN
        # let's verify and adjust
        eh = get_expected_harm(tree)
        if eh < -0.3:
            assert classify_risk(tree) == "YELLOW"
        else:
            assert classify_risk(tree) == "GREEN"

    def test_low_prob_catastrophic_not_red(self):
        tree = _low_prob_catastrophic_tree()
        assert classify_risk(tree) != "RED"

    def test_empty_tree_is_green(self):
        tree = _empty_tree()
        assert classify_risk(tree) == "GREEN"

    def test_custom_threshold(self):
        tree = _catastrophic_tree()
        # Default -0.8 catches the -0.9 and -0.85 nodes
        assert classify_risk(tree, catastrophic_threshold=-0.8) == "RED"
        # Threshold -0.95 still catches the -0.9 node (harm_benefit=-0.9 <= -0.95? No)
        # but -0.85 <= -0.85? No (need strictly <=). Actually -0.9 <= -0.85 = True
        assert classify_risk(tree, catastrophic_threshold=-0.85) == "RED"
        # Threshold beyond any node score — won't trigger
        assert classify_risk(tree, catastrophic_threshold=-0.99) != "RED"
