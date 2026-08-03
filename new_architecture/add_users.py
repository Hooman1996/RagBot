# add_users.py

"""
Simple User Addition Script - Updated for New Table Structure
==============================================================

This script adds users to the PostgreSQL database.
Compatible with the new minimal safe models.

Usage:
    python add_users.py                    # Interactive menu
    python add_users.py add                # Add users
    python add_users.py list               # List users
    python add_users.py delete <email>     # Delete user
    python add_users.py delete-all         # Delete all users
"""

import sys
from pathlib import Path
import os
from dotenv import load_dotenv

# Load variables from .env into os.environ
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import psycopg2
from datetime import datetime
import uuid
import bcrypt
import json

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Database connection details
# DB_HOST = "localhost"
# DB_PORT = 5432
# DB_NAME = "rag_db"
# DB_USER = "postgres"
# DB_PASSWORD = "postgres"

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "hihelp_db")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# ═══════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def generate_uuid() -> str:
    """Generate a unique UUID"""
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════
# USER DATA
# ═══════════════════════════════════════════════════════════

# Define users to add
USERS_TO_ADD = [
    {
        'email': 'admin@example.com',
        'username': 'admin',
        'password': 'Admin@123',
        'full_name': 'System Administrator',
        'role': 'admin',
        'is_active': True,
        'is_verified': True,
        'bio': 'System administrator with full access',
        'avatar_url': None,
        'settings': {
            'theme': 'dark',
            'notifications': True,
            'language': 'en'
        }
    },
    {
        'email': 'john.doe@example.com',
        'username': 'johndoe',
        'password': 'John@123',
        'full_name': 'John Doe',
        'role': 'user',
        'is_active': True,
        'is_verified': True,
        'bio': 'Regular user - Software Engineer',
        'avatar_url': None,
        'settings': {
            'theme': 'light',
            'notifications': True,
            'language': 'en'
        }
    },
    {
        'email': 'jane.smith@example.com',
        'username': 'janesmith',
        'password': 'Jane@123',
        'full_name': 'Jane Smith',
        'role': 'user',
        'is_active': True,
        'is_verified': True,
        'bio': 'Regular user - Data Scientist',
        'avatar_url': None,
        'settings': {
            'theme': 'light',
            'notifications': False,
            'language': 'en'
        }
    },
    {
        'email': 'moderator@example.com',
        'username': 'moderator',
        'password': 'Mod@123',
        'full_name': 'Content Moderator',
        'role': 'moderator',
        'is_active': True,
        'is_verified': True,
        'bio': 'Content moderator with review permissions',
        'avatar_url': None,
        'settings': {
            'theme': 'dark',
            'notifications': True,
            'language': 'en'
        }
    },
    {
        'email': 'alice.johnson@example.com',
        'username': 'alicejohnson',
        'password': 'Alice@123',
        'full_name': 'Alice Johnson',
        'role': 'user',
        'is_active': True,
        'is_verified': False,
        'bio': 'New user - awaiting email verification',
        'avatar_url': None,
        'settings': {
            'theme': 'light',
            'notifications': True,
            'language': 'en'
        }
    },
]


# ═══════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════

def add_users():
    """
    Add users to the database
    """
    print()
    print("=" * 80)
    print("ADDING USERS TO DATABASE")
    print("=" * 80)
    print()

    # Connect to database
    print(f"→ Connecting to database...")
    print(f"   Host: {DB_HOST}:{DB_PORT}")
    print(f"   Database: {DB_NAME}")
    print(f"   User: {DB_USER}")
    print()

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        print("✅ Connected to database")
        print()

    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        print()
        print("Please check:")
        print("  1. PostgreSQL is running")
        print("  2. Database exists (run: python setup_dbs.py)")
        print("  3. Connection details are correct")
        print()
        sys.exit(1)

    cursor = conn.cursor()

    # Check if users table exists
    print("→ Checking if users table exists...")

    cursor.execute("""
                   SELECT EXISTS (SELECT
                                  FROM information_schema.tables
                                  WHERE table_schema = 'public'
                                    AND table_name = 'users')
                   """)

    table_exists = cursor.fetchone()[0]

    if not table_exists:
        print("❌ Users table does not exist!")
        print("   Please run: python setup_dbs.py")
        print()
        conn.close()
        sys.exit(1)

    print("✓ Users table exists")
    print()

    # Check table structure
    print("→ Verifying table structure...")

    cursor.execute("""
                   SELECT column_name, data_type
                   FROM information_schema.columns
                   WHERE table_name = 'users'
                   ORDER BY ordinal_position
                   """)

    columns = cursor.fetchall()
    column_names = [col[0] for col in columns]

    # Check for required columns
    required_columns = ['id', 'uuid', 'email', 'username', 'password_hash', 'role', 'is_active']
    missing_columns = [col for col in required_columns if col not in column_names]

    if missing_columns:
        print(f"❌ Missing required columns: {missing_columns}")
        print()
        conn.close()
        sys.exit(1)

    print(f"✓ Table structure verified ({len(columns)} columns)")
    print()

    # Check existing users
    print("→ Checking existing users...")

    cursor.execute("SELECT COUNT(*) FROM users")
    existing_count = cursor.fetchone()[0]

    print(f"✓ Found {existing_count} existing users")
    print()

    # Get existing emails and usernames to avoid duplicates
    cursor.execute("SELECT email FROM users")
    existing_emails = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT username FROM users")
    existing_usernames = [row[0] for row in cursor.fetchall()]

    # Add users
    print("→ Adding users...")
    print()

    added_count = 0
    skipped_count = 0

    for user_data in USERS_TO_ADD:
        email = user_data['email']
        username = user_data['username']

        # Check if user already exists
        if email in existing_emails:
            print(f"⚠️  Skipped: {email} (email already exists)")
            skipped_count += 1
            continue

        if username in existing_usernames:
            print(f"⚠️  Skipped: {username} (username already exists)")
            skipped_count += 1
            continue

        # Hash password
        password_hash = hash_password(user_data['password'])

        # Generate UUID
        user_uuid = generate_uuid()

        # Prepare settings as JSON
        settings_json = json.dumps(user_data.get('settings', {}))

        # Insert user - UPDATED COLUMN NAMES
        try:
            cursor.execute("""
                           INSERT INTO users (uuid,
                                              email,
                                              username,
                                              password_hash,
                                              full_name,
                                              bio,
                                              avatar_url,
                                              role,
                                              is_active,
                                              is_verified,
                                              settings,
                                              created_at,
                                              updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                           """, (
                               user_uuid,
                               email,
                               username,
                               password_hash,
                               user_data['full_name'],
                               user_data.get('bio', ''),
                               user_data.get('avatar_url'),
                               user_data['role'],
                               user_data['is_active'],
                               user_data['is_verified'],
                               settings_json,
                               datetime.utcnow(),
                               datetime.utcnow()
                           ))

            user_id = cursor.fetchone()[0]

            print(f"✅ Added: {email}")
            print(f"   ID: {user_id}")
            print(f"   Username: {username}")
            print(f"   Role: {user_data['role']}")
            print(f"   Password: {user_data['password']}")
            print()

            added_count += 1

        except Exception as e:
            print(f"❌ Failed to add {email}: {e}")
            print()

    # Commit changes
    conn.commit()

    print("-" * 80)
    print(f"Summary:")
    print(f"  Added: {added_count} users")
    print(f"  Skipped: {skipped_count} users (already exist)")
    print(f"  Total in database: {existing_count + added_count} users")
    print()

    # Display all users
    print("→ Current users in database:")
    print()

    cursor.execute("""
                   SELECT id,
                          email,
                          username,
                          full_name,
                          role,
                          is_active,
                          is_verified,
                          created_at
                   FROM users
                   ORDER BY id
                   """)

    users = cursor.fetchall()

    print(f"{'ID':<5} {'Email':<30} {'Username':<20} {'Role':<15} {'Status':<15}")
    print("-" * 90)

    for user in users:
        user_id, email, username, full_name, role, is_active, is_verified, created_at = user

        status = "Active" if is_active else "Inactive"
        if not is_verified:
            status += " (Unverified)"

        print(f"{user_id:<5} {email:<30} {username:<20} {role:<15} {status:<15}")

    print()

    # Close connection
    cursor.close()
    conn.close()

    print("✅ Done!")
    print()

    # Show credentials
    if added_count > 0:
        print("=" * 80)
        print("LOGIN CREDENTIALS")
        print("=" * 80)
        print()
        print("Use these credentials to log in:")
        print()
        for user_data in USERS_TO_ADD:
            if user_data['email'] not in existing_emails and user_data['username'] not in existing_usernames:
                print(f"  Username: {user_data['username']}")
                print(f"  Password: {user_data['password']}")
                print(f"  Role: {user_data['role']}")
                print()
        print("=" * 80)
        print()


# ═══════════════════════════════════════════════════════════
# ADDITIONAL FUNCTIONS
# ═══════════════════════════════════════════════════════════

def list_users():
    """
    List all users in the database
    """
    print()
    print("=" * 80)
    print("LISTING ALL USERS")
    print("=" * 80)
    print()

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        cursor = conn.cursor()

        cursor.execute("""
                       SELECT id,
                              uuid,
                              email,
                              username,
                              full_name,
                              role,
                              is_active,
                              is_verified,
                              bio,
                              created_at,
                              last_login_at
                       FROM users
                       ORDER BY id
                       """)

        users = cursor.fetchall()

        if not users:
            print("No users found in database.")
            print()
        else:
            print(f"Found {len(users)} users:")
            print()

            for user in users:
                (user_id, user_uuid, email, username, full_name,
                 role, is_active, is_verified, bio, created_at, last_login_at) = user

                print(f"{'─' * 80}")
                print(f"ID: {user_id}")
                print(f"  UUID: {user_uuid}")
                print(f"  Email: {email}")
                print(f"  Username: {username}")
                print(f"  Full Name: {full_name}")
                print(f"  Role: {role}")
                print(f"  Active: {'Yes' if is_active else 'No'}")
                print(f"  Verified: {'Yes' if is_verified else 'No'}")
                if bio:
                    print(f"  Bio: {bio}")
                print(f"  Created: {created_at}")
                if last_login_at:
                    print(f"  Last Login: {last_login_at}")
                print()

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        print()


def delete_user(email: str):
    """
    Delete a user by email

    Args:
        email: User email to delete
    """
    print()
    print("=" * 80)
    print(f"DELETING USER: {email}")
    print("=" * 80)
    print()

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            print(f"❌ User not found: {email}")
            print()
            cursor.close()
            conn.close()
            return

        user_id, username = user

        # Check for related data
        cursor.execute("SELECT COUNT(*) FROM documents WHERE user_id = %s", (user_id,))
        doc_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM collections WHERE user_id = %s", (user_id,))
        col_count = cursor.fetchone()[0]

        if doc_count > 0 or col_count > 0:
            print(f"⚠️  Warning: User has related data:")
            print(f"   Documents: {doc_count}")
            print(f"   Collections: {col_count}")
            print()
            response = input("Delete anyway? This will CASCADE delete all related data (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Cancelled")
                print()
                cursor.close()
                conn.close()
                return

        # Delete user (CASCADE will handle related data)
        cursor.execute("DELETE FROM users WHERE email = %s", (email,))
        conn.commit()

        print(f"✅ Deleted user: {email} (ID: {user_id}, Username: {username})")
        print()

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        print()


def delete_all_users():
    """
    Delete ALL users from the database (USE WITH CAUTION!)
    """
    print()
    print("=" * 80)
    print("⚠️  DELETE ALL USERS")
    print("=" * 80)
    print()

    response = input("Are you sure you want to DELETE ALL USERS? (type 'DELETE ALL' to confirm): ")

    if response != 'DELETE ALL':
        print()
        print("❌ Cancelled")
        print()
        return

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        cursor = conn.cursor()

        # Count users
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]

        print(f"→ Deleting {count} users...")

        # Delete all users (CASCADE will handle related data)
        cursor.execute("DELETE FROM users")
        conn.commit()

        print(f"✅ Deleted {count} users")
        print()

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        print()


def show_user_stats():
    """Show user statistics"""
    print()
    print("=" * 80)
    print("USER STATISTICS")
    print("=" * 80)
    print()

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        cursor = conn.cursor()

        # Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]

        # Active users
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = true")
        active = cursor.fetchone()[0]

        # Verified users
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_verified = true")
        verified = cursor.fetchone()[0]

        # Users by role
        cursor.execute("""
                       SELECT role, COUNT(*)
                       FROM users
                       GROUP BY role
                       ORDER BY COUNT(*) DESC
                       """)
        roles = cursor.fetchall()

        print(f"Total Users: {total}")
        print(f"Active Users: {active}")
        print(f"Verified Users: {verified}")
        print()

        print("Users by Role:")
        for role, count in roles:
            print(f"  {role}: {count}")
        print()

        # Recent users
        cursor.execute("""
                       SELECT username, email, created_at
                       FROM users
                       ORDER BY created_at DESC LIMIT 5
                       """)
        recent = cursor.fetchall()

        print("Recent Users:")
        for username, email, created_at in recent:
            print(f"  {username} ({email}) - {created_at}")
        print()

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        print()


# ═══════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════

def show_menu():
    """Show interactive menu"""
    print()
    print("=" * 80)
    print("USER MANAGEMENT - MENU")
    print("=" * 80)
    print()
    print("1. Add users (from USERS_TO_ADD list)")
    print("2. List all users")
    print("3. Show user statistics")
    print("4. Delete user by email")
    print("5. Delete ALL users (dangerous!)")
    print("6. Exit")
    print()


def main():
    """
    Main function with interactive menu
    """
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "USER MANAGEMENT SCRIPT - Updated for New Tables".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    # Check if running with arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'add':
            add_users()
        elif command == 'list':
            list_users()
        elif command == 'stats':
            show_user_stats()
        elif command == 'delete':
            if len(sys.argv) > 2:
                delete_user(sys.argv[2])
            else:
                print("Usage: python add_users.py delete <email>")
        elif command == 'delete-all':
            delete_all_users()
        else:
            print(f"Unknown command: {command}")
            print()
            print("Usage:")
            print("  python add_users.py add              # Add users")
            print("  python add_users.py list             # List users")
            print("  python add_users.py stats            # Show statistics")
            print("  python add_users.py delete <email>   # Delete user")
            print("  python add_users.py delete-all       # Delete all users")
            print()

        return

    # Interactive menu
    while True:
        show_menu()

        choice = input("Enter your choice (1-6): ").strip()

        if choice == '1':
            add_users()
        elif choice == '2':
            list_users()
        elif choice == '3':
            show_user_stats()
        elif choice == '4':
            email = input("Enter user email to delete: ").strip()
            if email:
                delete_user(email)
        elif choice == '5':
            delete_all_users()
        elif choice == '6':
            print()
            print("Goodbye!")
            print()
            break
        else:
            print()
            print("❌ Invalid choice. Please try again.")
            print()


# ═══════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)