"""Run all seed scripts in sequence: cities, catalogues, then test data.

This is the one-command setup for a fresh sandbox/development database.
It runs each seed in the correct dependency order:

    1. Cities (Bogota must exist for reports and authorities)
    2. Catalogues (infractions, vehicle types, levels, badges)
    3. Test data (users, authority, reports, activities, API keys)

Each step is idempotent -- re-running is safe.

Usage:
    cd services/api
    python -m app.scripts.seed_all

Or via Railway:
    railway run --service multando-backend python -m app.scripts.seed_all
"""

import asyncio
import logging

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run all seeds in order."""
    if settings.APP_ENV == "production":
        logger.error("ABORTED: Cannot run seed_all in production!")
        return

    logger.info("=" * 60)
    logger.info("  Multando -- Full Database Seed")
    logger.info(f"  Environment: {settings.APP_ENV}")
    logger.info("=" * 60)

    # Step 1: Cities
    logger.info("")
    logger.info("[1/3] Seeding cities...")
    logger.info("-" * 40)
    from app.core.database import async_session_maker
    from app.scripts.seed_cities import seed_cities

    async with async_session_maker() as session:
        cities = await seed_cities(session)
        if cities:
            logger.info(f"  Created {len(cities)} cities")
        else:
            logger.info("  Cities already seeded -- skipped")

    # Step 2: Catalogues (levels, badges, infractions, vehicle types)
    logger.info("")
    logger.info("[2/3] Seeding catalogues...")
    logger.info("-" * 40)
    from app.scripts.seed import seed_all as seed_catalogues

    catalogue_results = await seed_catalogues()
    total_catalogue = sum(catalogue_results.values())
    if total_catalogue > 0:
        logger.info(f"  Created {total_catalogue} catalogue records")
    else:
        logger.info("  Catalogues already seeded -- skipped")

    # Step 3: Test data
    logger.info("")
    logger.info("[3/3] Seeding test data...")
    logger.info("-" * 40)
    from app.scripts.seed_test_data import seed_test_data

    await seed_test_data()

    logger.info("")
    logger.info("=" * 60)
    logger.info("  All seeds completed.")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
