import importlib.util
import json
import logging
import sys
from pathlib import Path

from sophia.hats.schema import (
    EvaluatorConfig,
    HatConfig,
    HatManifest,
    StakeholderRegistry,
)
from sophia.tools.base import Tool

logger = logging.getLogger(__name__)

PROMPT_FILES = [
    "system",
    "proposer",
    "consequence",
    "eval_self",
    "eval_tribal",
    "eval_domain",
    "eval_authority",
]


def discover_hats(hats_dir: Path) -> list[HatManifest]:
    """Scan a directory for valid hats and return their manifests."""
    manifests = []
    if not hats_dir.exists():
        logger.warning("Hats directory does not exist: %s", hats_dir)
        return manifests

    for entry in sorted(hats_dir.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "hat.json"
        if not manifest_path.exists():
            logger.debug("Skipping %s — no hat.json", entry.name)
            continue
        try:
            with open(manifest_path) as f:
                data = json.load(f)
            manifest = HatManifest(**data)
            manifests.append(manifest)
            logger.info("Discovered hat: %s (%s)", manifest.name, entry)
        except Exception as e:
            logger.error("Failed to load hat manifest at %s: %s", manifest_path, e)

    return manifests


def load_hat(hat_path: Path) -> HatConfig:
    """Load all components of a hat from disk."""
    manifest_path = hat_path / "hat.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No hat.json found at {hat_path}")

    with open(manifest_path) as f:
        raw_manifest = json.load(f)
    manifest = HatManifest(**raw_manifest)

    # Load constraints
    constraints = _load_json(hat_path / "constraints.json")

    # Load stakeholders
    stakeholders_data = _load_json(hat_path / "stakeholders.json")
    stakeholders = StakeholderRegistry(**stakeholders_data) if stakeholders_data else StakeholderRegistry()

    # Load evaluator config
    eval_data = _load_json(hat_path / "evaluator_config.json")
    evaluator_config = EvaluatorConfig(**eval_data) if eval_data else EvaluatorConfig()

    # Load prompts
    prompts = {}
    prompts_dir = hat_path / "prompts"
    if prompts_dir.exists():
        for prompt_name in PROMPT_FILES:
            prompt_path = prompts_dir / f"{prompt_name}.txt"
            if prompt_path.exists():
                prompts[prompt_name] = prompt_path.read_text().strip()

    logger.info(
        "Loaded hat '%s': %d tools, %d stakeholders, %d prompts",
        manifest.name,
        len(manifest.tools),
        len(stakeholders.stakeholders),
        len(prompts),
    )

    return HatConfig(
        manifest=manifest,
        hat_path=str(hat_path),
        constraints=constraints,
        stakeholders=stakeholders,
        evaluator_config=evaluator_config,
        prompts=prompts,
        raw_manifest=raw_manifest,
    )


def load_hat_tools(hat_config: HatConfig) -> list[Tool]:
    """Dynamically import and instantiate tools from a hat's tools/ directory."""
    tools_dir = hat_config.tools_module_path
    if not tools_dir.exists():
        logger.warning("No tools directory for hat '%s'", hat_config.name)
        return []

    tools: list[Tool] = []
    hat_name = hat_config.name

    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"hat_{hat_name}_{py_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            logger.warning("Could not load module spec for %s", py_file)
            continue

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find all Tool subclasses defined in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Tool)
                and attr is not Tool
                and hasattr(attr, "name")
            ):
                try:
                    instance = attr()
                    if instance.name in hat_config.manifest.tools:
                        tools.append(instance)
                        logger.debug("Loaded tool: %s from %s", instance.name, py_file.name)
                except Exception as e:
                    logger.error("Failed to instantiate tool %s: %s", attr_name, e)

    logger.info("Loaded %d tools for hat '%s'", len(tools), hat_config.name)
    return tools


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict if not found."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)
