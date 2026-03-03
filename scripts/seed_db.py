#!/usr/bin/env python3
"""Sophia — Database Seeding Script

Loads seed data from the active hat's seed/ directory into the database.
Used for development and testing — populates the database with realistic
sample records so you can test the pipeline without live data.

Usage:
    uv run python scripts/seed_db.py
    uv run python scripts/seed_db.py --hat customer-service
    uv run python scripts/seed_db.py --hat customer-service --clear
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sophia.config import settings
from sophia.hats.loader import discover_hats, load_hat

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def find_seed_files(hat_path: Path) -> list[Path]:
    """Find all JSON files in a hat's seed/ directory."""
    seed_dir = hat_path / "seed"
    if not seed_dir.exists():
        return []
    return sorted(seed_dir.glob("*.json"))


def load_seed_data(seed_files: list[Path]) -> dict[str, list]:
    """Load all seed files into a dict keyed by filename stem."""
    data = {}
    for path in seed_files:
        try:
            with open(path) as f:
                content = json.load(f)
            data[path.stem] = content if isinstance(content, list) else [content]
            logger.info("  Loaded %s (%d records)", path.name, len(data[path.stem]))
        except json.JSONDecodeError as e:
            logger.error("  Failed to parse %s: %s", path.name, e)
        except Exception as e:
            logger.error("  Failed to load %s: %s", path.name, e)
    return data


def seed_hat(hat_name: str, clear: bool = False) -> None:
    """Load seed data for a specific hat."""
    hats_dir = Path(settings.hats_dir).resolve()

    # Verify the hat exists
    available = discover_hats(hats_dir)
    hat_names = {m.name for m in available}
    if hat_name not in hat_names:
        logger.error("Hat '%s' not found. Available: %s", hat_name, ", ".join(sorted(hat_names)))
        sys.exit(1)

    hat_path = hats_dir / hat_name
    hat_config = load_hat(hat_path)

    logger.info("Seeding hat: %s (%s)", hat_config.display_name, hat_name)

    # Find seed files
    seed_files = find_seed_files(hat_path)
    if not seed_files:
        logger.info("  No seed data found in %s/seed/", hat_name)
        return

    # Load data
    data = load_seed_data(seed_files)

    if clear:
        logger.info("  --clear flag set: would clear existing records before seeding")
        # Phase 5: implement actual database clearing here

    # Phase 5: insert data into database tables
    # For now, just validate and report what would be seeded
    total_records = sum(len(records) for records in data.values())
    logger.info(
        "  Ready to seed %d records across %d tables",
        total_records,
        len(data),
    )

    for table_name, records in data.items():
        logger.info("    %s: %d records", table_name, len(records))

    # Print sample data for verification
    for table_name, records in data.items():
        if records:
            logger.info("  Sample from %s: %s", table_name, json.dumps(records[0], indent=2)[:200])

    logger.info("Seeding complete (dry run — database writes available in Phase 5)")


def main():
    parser = argparse.ArgumentParser(description="Seed the Sophia database with hat data")
    parser.add_argument(
        "--hat",
        default=settings.default_hat,
        help=f"Hat to seed data from (default: {settings.default_hat})",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing records before seeding",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_hats",
        help="List available hats and their seed data",
    )
    args = parser.parse_args()

    if args.list_hats:
        hats_dir = Path(settings.hats_dir).resolve()
        available = discover_hats(hats_dir)
        if not available:
            logger.info("No hats found in %s", hats_dir)
            return
        for manifest in available:
            hat_path = hats_dir / manifest.name
            seed_files = find_seed_files(hat_path)
            seed_info = f"{len(seed_files)} seed file(s)" if seed_files else "no seed data"
            logger.info("  %s — %s", manifest.name, seed_info)
        return

    seed_hat(args.hat, clear=args.clear)


if __name__ == "__main__":
    main()
