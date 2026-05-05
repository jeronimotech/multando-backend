"""Create Twitter (X) scraping tables for the Apify integration.

Adds:
- ``twitter_hashtags``      — admin-managed list of hashtags to monitor.
- ``twitter_scraped_tweets`` — every tweet returned by Apify, with
  Claude-extracted infraction data and an optional link to a Report.
- ``twitter_scrape_runs``   — audit log per scheduled scrape.

Revision ID: 019_twitter_scraping
Revises: 018_sdm_submissions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "019_twitter_scraping"
down_revision = "018_sdm_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # twitter_hashtags
    # ------------------------------------------------------------------
    op.create_table(
        "twitter_hashtags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("hashtag", sa.String(length=140), nullable=False),
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "last_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_tweet_id", sa.String(length=64), nullable=True),
        sa.Column(
            "total_tweets_fetched",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_reports_created",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hashtag", name="uq_twitter_hashtags_hashtag"),
    )
    op.create_index(
        "ix_twitter_hashtags_hashtag",
        "twitter_hashtags",
        ["hashtag"],
    )
    op.create_index(
        "ix_twitter_hashtags_jurisdiction_id",
        "twitter_hashtags",
        ["jurisdiction_id"],
    )
    op.create_index(
        "ix_twitter_hashtags_enabled",
        "twitter_hashtags",
        ["enabled"],
    )

    # ------------------------------------------------------------------
    # twitter_scraped_tweets
    # ------------------------------------------------------------------
    op.create_table(
        "twitter_scraped_tweets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tweet_id", sa.String(length=64), nullable=False),
        sa.Column(
            "hashtag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("twitter_hashtags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_handle", sa.String(length=100), nullable=False),
        sa.Column("tweet_text", sa.Text(), nullable=False),
        sa.Column("tweet_url", sa.String(length=500), nullable=False),
        sa.Column("media_urls", postgresql.JSONB(), nullable=True),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=True),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tweet_id", name="uq_twitter_scraped_tweets_tweet_id"
        ),
    )
    op.create_index(
        "ix_twitter_scraped_tweets_tweet_id",
        "twitter_scraped_tweets",
        ["tweet_id"],
    )
    op.create_index(
        "ix_twitter_scraped_tweets_hashtag_id",
        "twitter_scraped_tweets",
        ["hashtag_id"],
    )
    op.create_index(
        "ix_twitter_scraped_tweets_report_id",
        "twitter_scraped_tweets",
        ["report_id"],
    )
    op.create_index(
        "ix_twitter_scraped_tweets_status",
        "twitter_scraped_tweets",
        ["status"],
    )
    op.create_index(
        "ix_twitter_scraped_tweets_posted_at",
        "twitter_scraped_tweets",
        ["posted_at"],
    )
    op.create_index(
        "ix_twitter_scraped_tweets_created_at",
        "twitter_scraped_tweets",
        ["created_at"],
    )

    # ------------------------------------------------------------------
    # twitter_scrape_runs
    # ------------------------------------------------------------------
    op.create_table(
        "twitter_scrape_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "hashtag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("twitter_hashtags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "ended_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "tweets_fetched",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reports_created",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("apify_run_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_twitter_scrape_runs_hashtag_id",
        "twitter_scrape_runs",
        ["hashtag_id"],
    )
    op.create_index(
        "ix_twitter_scrape_runs_created_at",
        "twitter_scrape_runs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_twitter_scrape_runs_created_at",
        table_name="twitter_scrape_runs",
    )
    op.drop_index(
        "ix_twitter_scrape_runs_hashtag_id",
        table_name="twitter_scrape_runs",
    )
    op.drop_table("twitter_scrape_runs")

    op.drop_index(
        "ix_twitter_scraped_tweets_created_at",
        table_name="twitter_scraped_tweets",
    )
    op.drop_index(
        "ix_twitter_scraped_tweets_posted_at",
        table_name="twitter_scraped_tweets",
    )
    op.drop_index(
        "ix_twitter_scraped_tweets_status",
        table_name="twitter_scraped_tweets",
    )
    op.drop_index(
        "ix_twitter_scraped_tweets_report_id",
        table_name="twitter_scraped_tweets",
    )
    op.drop_index(
        "ix_twitter_scraped_tweets_hashtag_id",
        table_name="twitter_scraped_tweets",
    )
    op.drop_index(
        "ix_twitter_scraped_tweets_tweet_id",
        table_name="twitter_scraped_tweets",
    )
    op.drop_table("twitter_scraped_tweets")

    op.drop_index(
        "ix_twitter_hashtags_enabled", table_name="twitter_hashtags"
    )
    op.drop_index(
        "ix_twitter_hashtags_jurisdiction_id",
        table_name="twitter_hashtags",
    )
    op.drop_index(
        "ix_twitter_hashtags_hashtag", table_name="twitter_hashtags"
    )
    op.drop_table("twitter_hashtags")
