from pathlib import Path

import pytest

from sophia.hats.loader import discover_hats, load_hat, load_hat_tools
from sophia.hats.schema import HatConfig, HatManifest
from tests.conftest import CS_HAT_DIR, HATS_DIR


def test_discover_hats():
    manifests = discover_hats(HATS_DIR)
    assert len(manifests) >= 1
    names = {m.name for m in manifests}
    assert "customer-service" in names


def test_discover_hats_empty_dir(tmp_path):
    manifests = discover_hats(tmp_path)
    assert manifests == []


def test_discover_hats_nonexistent_dir():
    manifests = discover_hats(Path("/nonexistent"))
    assert manifests == []


def test_load_hat():
    hat = load_hat(CS_HAT_DIR)

    assert hat.manifest.name == "customer-service"
    assert hat.manifest.display_name == "Customer Service"
    assert len(hat.manifest.tools) == 21
    assert "look_up_order" in hat.manifest.tools
    assert "escalate_to_human" in hat.manifest.tools

    # Constraints loaded
    assert hat.constraints["business_name"] == "TechMart Electronics"
    assert hat.constraints["policies"]["max_agent_refund"] == 100.00

    # Stakeholders loaded
    assert len(hat.stakeholders.stakeholders) == 4
    ids = {s.id for s in hat.stakeholders.stakeholders}
    assert ids == {"customer", "business", "other_customers", "employees"}

    # Evaluator config loaded
    assert hat.evaluator_config.weight_overrides["tribal"] == 0.40

    # Prompts loaded
    assert "system" in hat.prompts
    assert "proposer" in hat.prompts
    assert "TechMart" in hat.prompts["system"]


def test_load_hat_tools():
    hat = load_hat(CS_HAT_DIR)
    tools = load_hat_tools(hat)

    assert len(tools) == 19
    names = {t.name for t in tools}
    assert "look_up_order" in names
    assert "offer_full_refund" in names
    assert "escalate_to_human" in names


def test_load_hat_nonexistent():
    with pytest.raises(FileNotFoundError):
        load_hat(Path("/nonexistent/hat"))
