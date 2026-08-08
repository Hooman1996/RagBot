# setup_dbs.py

"""
Database Initialization Script - Minimal Safe Tables
=====================================================

This script:
1. Connects to default PostgreSQL 'postgres' database
2. Creates 'hihelp_db' database if it doesn't exist
3. Creates ONLY minimal safe tables:
   - users
   - collections
   - documents
   - chunks
   - embeddings
   - queries
   - chat_sessions
   - tickets
   - chunk_versions

Usage:
    python setup_dbs.py

Run this ONCE before running your main application.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

import os
from dotenv import load_dotenv
from new_architecture.knowledge_reset import (
    PRODUCTION_RESET_CONFIRMATION,
    RESET_CONFIRMATION,
    KnowledgeResetService,
    ResetPhaseError,
    reset_postgres_schema,
)

# Load variables from .env into os.environ
load_dotenv()

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

# DEFAULT_DB_PORT = 5432


DEFAULT_DB_HOST = os.getenv("DEFAULT_DB_HOST")
DEFAULT_DB_PORT = os.getenv("DEFAULT_DB_PORT")
DEFAULT_DB_USER = os.getenv("DEFAULT_DB_USER")
DEFAULT_DB_PASSWORD = os.getenv("DEFAULT_DB_PASSWORD")
DEFAULT_DB_NAME = os.getenv("DEFAULT_DB_NAME")

# DEFAULT_DB_NAME = 'chatbot'


# TARGET_DB_NAME = "chatbot"
# TARGET_DB_PORT = 5432

TARGET_DB_NAME = os.getenv("POSTGRES_DB")
TARGET_DB_HOST = os.getenv("POSTGRES_HOST")
TARGET_DB_PORT = os.getenv("POSTGRES_PORT")



TARGET_DB_USER = os.getenv("POSTGRES_USER")
TARGET_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")


# Connection URLs
DEFAULT_DB_URL = (
    f"postgresql+asyncpg://{DEFAULT_DB_USER}:{DEFAULT_DB_PASSWORD}"
    f"@{DEFAULT_DB_HOST}:{DEFAULT_DB_PORT}/{DEFAULT_DB_NAME}"
)

TARGET_DB_URL = (
    f"postgresql+asyncpg://{TARGET_DB_USER}:{TARGET_DB_PASSWORD}"
    f"@{TARGET_DB_HOST}:{TARGET_DB_PORT}/{TARGET_DB_NAME}"
)


def schema_reset_requested(response: str) -> bool:
    """Interpret the explicit PostgreSQL reset prompt deterministically."""
    return response.strip().lower() in {"yes", "y"}


# ═══════════════════════════════════════════════════════════
# STEP 1: CREATE DATABASE
# ═══════════════════════════════════════════════════════════

async def create_database():
    """
    Connect to default 'postgres' database and create target DB
    """
    print("=" * 80)
    print("STEP 1: Creating Database")
    print("=" * 80)
    print()

    print(f"→ Connecting to PostgreSQL server...")
    print(f"   Host: {DEFAULT_DB_HOST}")
    print(f"   Port: {DEFAULT_DB_PORT}")
    print(f"   User: {DEFAULT_DB_USER}")
    print()

    try:
        # Connect to default 'postgres' database
        conn = await asyncpg.connect(
            host=DEFAULT_DB_HOST,
            port=DEFAULT_DB_PORT,
            user=DEFAULT_DB_USER,
            password=DEFAULT_DB_PASSWORD,
            database=DEFAULT_DB_NAME
        )

        print(f"✅ Connected to PostgreSQL server")
        print()

        # Check if target database exists
        print(f"→ Checking if database '{TARGET_DB_NAME}' exists...")

        target_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            TARGET_DB_NAME
        )

        if target_exists:
            print(f"✓ Database '{TARGET_DB_NAME}' already exists")
            print()
            await conn.close()
            return True

        else:
            print(f"→ Database '{TARGET_DB_NAME}' does not exist")
            print(f"→ Creating database '{TARGET_DB_NAME}'...")

            # Create database
            await conn.execute(f'CREATE DATABASE "{TARGET_DB_NAME}"')

            print(f"✅ Database '{TARGET_DB_NAME}' created successfully!")
            print()

            await conn.close()
            return True

    except asyncpg.PostgresError as e:
        print(f"❌ PostgreSQL Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# STEP 2: CREATE TABLES (MINIMAL SAFE MODELS ONLY)
# ═══════════════════════════════════════════════════════════

async def create_tables(*, allow_production_reset: bool = False):
    """
    Connect to target DB and create ONLY minimal safe tables
    """
    print("=" * 80)
    print("STEP 2: Creating Tables (Minimal Safe Models Only)")
    print("=" * 80)
    print()

    try:
        # Import Base class
        from app.core.database import Base

        # ═══════════════════════════════════════════════════════════
        # IMPORT ONLY MINIMAL SAFE MODELS
        # ═══════════════════════════════════════════════════════════

        print("→ Importing minimal safe models...")

        from app.models.user import User
        from app.models.collection import Collection
        from app.models.document import Document
        from app.models.chunk import Chunk
        from app.models.embedding import Embedding
        from app.models.query import Query
        from app.models.chat_session import ChatSession
        from app.models.feedback import Feedback
        from app.models.ticket import Ticket

        print(f"✓ Imported {len(Base.metadata.tables)} models")
        print()

        # List all tables that will be created
        print("→ Tables to create:")
        expected_tables = [
            "users",
            "collections",
            "documents",
            "chunks",
            "embeddings",
            "queries",
            "chat_sessions",
            "feedbacks",
            "tickets",
            "chunk_versions",  # Added for KB version control
            "mass_answer_jobs",
        ]

        # Note: chunk_versions won't be in Base.metadata.tables initially if not modelled in SQLAlchemy
        for table_name in sorted(Base.metadata.tables.keys()):
            if table_name in expected_tables:
                print(f"   ✓ {table_name}")
            else:
                print(f"   ⚠ {table_name} (unexpected)")
        print(f"   ✓ chunk_versions (raw SQL initialization)")
        print()

        # Verify we have exactly the expected tables (excluding the raw SQL one for the set check)
        actual_tables = set(Base.metadata.tables.keys())
        expected_orm_tables = set(expected_tables) - {
            "chunk_versions",
            "mass_answer_jobs",
        }

        if actual_tables != expected_orm_tables:
            print("⚠️  WARNING: Table mismatch detected in ORM!")
            missing = expected_orm_tables - actual_tables
            if missing:
                print(f"   Missing tables: {missing}")

            extra = actual_tables - expected_orm_tables
            if extra:
                print(f"   Extra tables: {extra}")
            print()

        # ═══════════════════════════════════════════════════════════
        # CHECK IF TABLES EXIST
        # ═══════════════════════════════════════════════════════════

        print(f"→ Connecting to database '{TARGET_DB_NAME}'...")

        conn = await asyncpg.connect(
            host=TARGET_DB_HOST,
            port=TARGET_DB_PORT,
            user=TARGET_DB_USER,
            password=TARGET_DB_PASSWORD,
            database=TARGET_DB_NAME
        )

        print(f"✅ Connected to database '{TARGET_DB_NAME}'")
        print()

        # Check existing tables
        print("→ Checking if tables exist...")

        result = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )

        existing_tables = [row['table_name'] for row in result]

        await conn.close()

        # ═══════════════════════════════════════════════════════════
        # ASK USER IF THEY WANT TO DROP AND RECREATE
        # ═══════════════════════════════════════════════════════════

        if existing_tables:
            print(f"⚠️  Found {len(existing_tables)} existing tables:")
            for table in existing_tables:
                print(f"   - {table}")
            print()

            response = input(
                "Drop and recreate PostgreSQL application tables? [y/N]: "
            )

            if not schema_reset_requested(response):
                print()
                print("⚠️  PostgreSQL schema reset skipped")
                print("   Existing tables and data will be kept")
                return True

            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                if not allow_production_reset:
                    print(
                        "❌ Production schema reset refused. Use "
                        "--allow-production-reset only under an approved procedure."
                    )
                    return False
                confirmation = input(
                    "Type RESET PRODUCTION SCHEMA to confirm PostgreSQL reset: "
                )
                if confirmation != "RESET PRODUCTION SCHEMA":
                    print("Production PostgreSQL reset cancelled.")
                    return False

            print()

        # ═══════════════════════════════════════════════════════════
        # CREATE TABLES
        # ═══════════════════════════════════════════════════════════

        print(f"→ Creating SQLAlchemy engine...")

        engine = create_async_engine(
            TARGET_DB_URL,
            echo=False,
            pool_pre_ping=True
        )

        print("→ Recreating PostgreSQL application schema...")
        await reset_postgres_schema(engine, Base.metadata)

        print("✅ PostgreSQL schema recreated successfully")
        print()

        if existing_tables:
            await prompt_for_knowledge_reset(
                allow_production_reset=allow_production_reset
            )

        # ═══════════════════════════════════════════════════════════
        # VERIFY TABLES WERE CREATED
        # ═══════════════════════════════════════════════════════════

        print("→ Verifying tables...")

        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT table_name,
                           (SELECT COUNT(*)
                            FROM information_schema.columns
                            WHERE table_name = t.table_name) as column_count
                    FROM information_schema.tables t
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                    """
                )
            )

            tables = [(row[0], row[1]) for row in result.fetchall()]

        print(f"✓ Found {len(tables)} tables in database:")
        print()

        for table_name, column_count in tables:
            status = "✓" if table_name in expected_tables else "⚠"
            print(f"   {status} {table_name:<30} ({column_count} columns)")

        print()

        # Verify relationships
        print("→ Verifying relationships...")

        async with engine.connect() as conn:
            # Check foreign keys
            result = await conn.execute(
                text(
                    """
                    SELECT tc.table_name,
                           kcu.column_name,
                           ccu.table_name  AS foreign_table_name,
                           ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                             JOIN information_schema.key_column_usage AS kcu
                                  ON tc.constraint_name = kcu.constraint_name
                             JOIN information_schema.constraint_column_usage AS ccu
                                  ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                    ORDER BY tc.table_name
                    """
                )
            )

            fks = result.fetchall()

            if fks:
                print(f"✓ Found {len(fks)} foreign key relationships:")
                for fk in fks:
                    table, column, ref_table, ref_column = fk
                    print(f"   {table}.{column} → {ref_table}.{ref_column}")
            else:
                print("⚠️  No foreign keys found (this might be an issue)")

        print()

        # Close engine
        await engine.dispose()

        return True

    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════════
# OPTIONAL CROSS-STORE KNOWLEDGE RESET
# ═══════════════════════════════════════════════════════════

async def prompt_for_knowledge_reset(*, allow_production_reset: bool) -> None:
    print(
        "Knowledge-base state may also exist in Qdrant, MinIO, "
        "and datasource selections."
    )
    response = input(
        "Clear ALL application knowledge-base data from PostgreSQL metadata, "
        "Qdrant, MinIO, and stale datasource selections? [y/N]: "
    )
    if response.lower() not in {"yes", "y"}:
        print("Knowledge-base data outside the PostgreSQL schema was preserved.")
        return

    service = KnowledgeResetService.from_environment()
    try:
        postgres = await asyncio.to_thread(service.inspect_postgres)
        qdrant = await asyncio.to_thread(service.inspect_qdrant)
        minio = await asyncio.to_thread(service.inspect_minio)
        print()
        print(f"PostgreSQL datasource records to clear: {postgres['documents']}")
        print(f"Qdrant points to clear: {qdrant['points']}")
        print(f"MinIO knowledge objects to clear: {minio['objects']}")
        print(
            "Stale datasource selections to clear: "
            f"{postgres['datasource_selections_to_clear']}"
        )
        print(f"MinIO reset scope: {minio['scope']}")
        print()

        production = service.config.environment == "production"
        if production and not allow_production_reset:
            raise RuntimeError(
                "Production knowledge reset refused without "
                "--allow-production-reset"
            )
        expected = (
            PRODUCTION_RESET_CONFIRMATION if production else RESET_CONFIRMATION
        )
        confirmation = input(f"Type {expected} to confirm: ")
        if confirmation != expected:
            print("Knowledge-base reset cancelled; confirmation did not match.")
            return

        result = await asyncio.to_thread(service.full_knowledge_reset)
        print(json.dumps(result.public_dict(), indent=2, ensure_ascii=False))

        if not production:
            clear_local = input(
                "Also clear generated files under DATA_INSERTION_DIRECTORY "
                "(FULL_DEV_RESET)? [y/N]: "
            )
            if clear_local.lower() in {"yes", "y"}:
                local_result = await asyncio.to_thread(
                    service.clear_generated_knowledge
                )
                print(json.dumps(local_result, indent=2, ensure_ascii=False))
    except ResetPhaseError as exc:
        print(json.dumps(exc.result.public_dict(), indent=2, ensure_ascii=False))
        raise
    finally:
        service.close()


# ═══════════════════════════════════════════════════════════
# STEP 3: VERIFY INSTALLATION
# ═══════════════════════════════════════════════════════════

async def verify_installation():
    """
    Verify that database and tables are ready
    """
    print("=" * 80)
    print("STEP 3: Verification")
    print("=" * 80)
    print()

    try:
        engine = create_async_engine(
            TARGET_DB_URL,
            echo=False,
            pool_pre_ping=True
        )

        # Test connection and get PostgreSQL version
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()

            print("✅ Database Connection Test:")
            print(f"   PostgreSQL Version: {version[:80]}...")
            print()

            # Count tables
            result = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
            )

            table_count = result.scalar()

            print(f"✅ Tables: {table_count} tables found")

            # Expected: 9 ORM tables + 2 raw SQL tables = 11
            if table_count >= 11:
                print(f"   ✓ Correct number of tables")
            else:
                print(f"   ⚠️  Expected at least 11 tables, found {table_count}")
            print()

            # Test each table
            tables_to_test = [
                "users",
                "collections",
                "documents",
                "chunks",
                "embeddings",
                "queries",
                "chat_sessions",
                "tickets",
                "chunk_versions",  # Testing new KB ledger
                "mass_answer_jobs",
            ]

            print("✅ Testing table access:")
            for table in tables_to_test:
                try:
                    result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    print(f"   ✓ {table:<20} (accessible, {count} rows)")
                except Exception as e:
                    print(f"   ✗ {table:<20} (error: {e})")

            print()

        await engine.dispose()

        return True

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════════
# STEP 4: CREATE SAMPLE DATA (OPTIONAL)
# ═══════════════════════════════════════════════════════════

async def create_sample_data():
    """
    Create sample data for testing (optional)
    """
    print("=" * 80)
    print("STEP 4: Create Sample Data (Optional)")
    print("=" * 80)
    print()

    response = input("Do you want to create sample test data? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("⚠️  Skipping sample data creation")
        print()
        return True

    print()
    print("→ Creating sample data...")

    try:
        import bcrypt
        from datetime import datetime

        engine = create_async_engine(TARGET_DB_URL, echo=False)

        async with engine.begin() as conn:
            # Create test user
            password_hash = bcrypt.hashpw("User@123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            result = await conn.execute(
                text("""
                     INSERT INTO users (uuid, email, username, password_hash, full_name,
                                        role, is_active, is_verified, created_at, updated_at)
                     VALUES (gen_random_uuid()::text, :email, :username, :password_hash, :full_name,
                             :role, :is_active, :is_verified, :created_at, :updated_at) RETURNING id
                     """),
                {
                    'email': 'test@example.com',
                    'username': 'testuser',
                    'password_hash': password_hash,
                    'full_name': 'Test User',
                    'role': 'user',
                    'is_active': True,
                    'is_verified': True,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
            )

            user_id = result.scalar()

            print(f"✓ Created test user (ID: {user_id})")
            print(f"   Username: testuser")
            print(f"   Password: User@123")
            print()

            # Create test collection
            result = await conn.execute(
                text("""
                     INSERT INTO collections (uuid, user_id, name, description,
                                              document_count, total_size, is_public,
                                              created_at, updated_at)
                     VALUES (gen_random_uuid()::text, :user_id, :name, :description,
                             :document_count, :total_size, :is_public,
                             :created_at, :updated_at) RETURNING id
                     """),
                {
                    'user_id': user_id,
                    'name': 'Test Collection',
                    'description': 'Sample collection for testing',
                    'document_count': 0,
                    'total_size': 0,
                    'is_public': False,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
            )

            collection_id = result.scalar()

            print(f"✓ Created test collection (ID: {collection_id})")
            print()

        await engine.dispose()

        print("✅ Sample data created successfully")
        print()

        return True

    except Exception as e:
        print(f"❌ Error creating sample data: {e}")
        import traceback
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════

async def main(*, allow_production_reset: bool = False):
    """
    Main initialization function
    """
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "NEGAH YAR DB INITIALIZATION - MINIMAL SAFE MODELS".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("║" + f"Target Database: {TARGET_DB_NAME}".ljust(78) + "║")
    print("║" + f"PostgreSQL Host: {TARGET_DB_HOST}:{TARGET_DB_PORT}".ljust(78) + "║")
    print("║" + " " * 78 + "║")
    print("║" + "Tables to create:".ljust(78) + "║")
    print("║" + "  • users".ljust(78) + "║")
    print("║" + "  • collections".ljust(78) + "║")
    print("║" + "  • documents".ljust(78) + "║")
    print("║" + "  • chunks".ljust(78) + "║")
    print("║" + "  • embeddings".ljust(78) + "║")
    print("║" + "  • queries".ljust(78) + "║")
    print("║" + "  • chat_sessions".ljust(78) + "║")
    print("║" + "  • tickets".ljust(78) + "║")
    print("║" + "  • chunk_versions (KB Ledger)".ljust(78) + "║")
    print("║" + "  • mass_answer_jobs".ljust(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    # Step 1: Create Database
    success = await create_database()
    if not success:
        print()
        print("❌ Failed to create database")
        print("   Please check your PostgreSQL connection settings")
        sys.exit(1)

    # Step 2: Create Tables
    success = await create_tables(
        allow_production_reset=allow_production_reset
    )
    if not success:
        print()
        print("❌ Failed to create tables")
        sys.exit(1)

    # Step 3: Verify Installation
    success = await verify_installation()
    if not success:
        print()
        print("❌ Verification failed")
        sys.exit(1)

    # Step 4: Create Sample Data (Optional)
    await create_sample_data()

    # Success!
    print()
    print("=" * 80)
    print()
    print("    ✅ DATABASE INITIALIZATION COMPLETE!")
    print()
    print("    Your database is ready with minimal safe models:")
    print()
    print("    Tables created:")
    print("      • users           - User accounts")
    print("      • collections     - Document collections")
    print("      • documents       - Uploaded documents")
    print("      • chunks          - Text chunks from documents")
    print("      • embeddings      - Vector embeddings")
    print("      • queries         - User queries and responses")
    print("      • chat_sessions   - Chat conversation sessions")
    print("      • chunk_versions  - Version tracking for KB modifications")
    print("      • mass_answer_jobs - Durable batch job metadata")
    print()
    print("    Next steps:")
    print("      1. Run your application")
    print("      2. Upload documents using upload_document_standalone.py")
    print("      3. Test the system")
    print()
    print("=" * 80)
    print()


# ═══════════════════════════════════════════════════════════
# RUN SCRIPT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-production-reset",
        action="store_true",
        help="Allow reset prompts in production; stronger confirmation still applies",
    )
    arguments = parser.parse_args()
    try:
        asyncio.run(
            main(
                allow_production_reset=arguments.allow_production_reset
            )
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
