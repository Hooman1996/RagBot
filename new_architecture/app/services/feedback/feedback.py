# app/services/feedback/feedback.py

"""
Feedback Service - Minimal Safe Version
========================================
Handles user feedback on query responses
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime

import psycopg2
import psycopg2.extras

import os
from dotenv import load_dotenv
load_dotenv()


class FeedbackService:
    """Service for managing user feedback"""

    def __init__(
            self,
            db_host: str = os.getenv("POSTGRES_HOST"),
            db_port: int = os.getenv("POSTGRES_PORT"),
            db_name: str = os.getenv("POSTGRES_DB"),
            db_user: str = os.getenv("POSTGRES_USER"),
            db_password: str = os.getenv("POSTGRES_PASSWORD"),

    ):
        """
        Initialize feedback service

        Args:
            db_host: Database host
            db_port: Database port
            db_name: Database name
            db_user: Database user
            db_password: Database password
        """
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password

    def _get_connection(self):
        """Get database connection"""
        return psycopg2.connect(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password
        )

    def submit_feedback(
            self,
            user_id: int,
            query_id: int,
            rating: Optional[int] = None,
            is_helpful: Optional[bool] = None,
            comment: Optional[str] = None,
            accuracy: Optional[int] = None,
            relevance: Optional[int] = None,
            completeness: Optional[int] = None,
            clarity: Optional[int] = None,
            improvement_suggestions: Optional[str] = None,
            issue_types: Optional[List[str]] = None,
            feedback_type: str = "rating",
            meta_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit feedback for a query

        Args:
            user_id: User ID
            query_id: Query ID
            rating: Overall rating (1-5)
            is_helpful: Simple helpful/not helpful
            comment: Text comment
            accuracy: Accuracy rating (1-5)
            relevance: Relevance rating (1-5)
            completeness: Completeness rating (1-5)
            clarity: Clarity rating (1-5)
            improvement_suggestions: Suggestions for improvement
            issue_types: List of issue types
            feedback_type: Type of feedback
            meta_data: Additional meta_data

        Returns:
            Dictionary with feedback result
        """
        print()
        print("=" * 80)
        print("SUBMITTING FEEDBACK")
        print("=" * 80)
        print()

        # Validate rating
        if rating is not None and (rating < 1 or rating > 5):
            return {
                'success': False,
                'error': 'Rating must be between 1 and 5'
            }

        # Validate other ratings
        for name, value in [
            ('accuracy', accuracy),
            ('relevance', relevance),
            ('completeness', completeness),
            ('clarity', clarity)
        ]:
            if value is not None and (value < 1 or value > 5):
                return {
                    'success': False,
                    'error': f'{name.capitalize()} must be between 1 and 5'
                }

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Check if query exists and belongs to user
            cursor.execute("""
                           SELECT id, user_id
                           FROM queries
                           WHERE id = %s
                           """, (query_id,))

            query = cursor.fetchone()

            if not query:
                cursor.close()
                conn.close()
                return {
                    'success': False,
                    'error': 'Query not found'
                }

            query_user_id = query[1]

            if query_user_id != user_id:
                cursor.close()
                conn.close()
                return {
                    'success': False,
                    'error': 'Unauthorized: Query belongs to another user'
                }

            # Check if feedback already exists
            cursor.execute("""
                           SELECT id
                           FROM feedbacks
                           WHERE query_id = %s
                           """, (query_id,))

            existing_feedback = cursor.fetchone()

            if existing_feedback:
                # Update existing feedback
                feedback_id = existing_feedback[0]

                print(f"→ Updating existing feedback (ID: {feedback_id})...")

                cursor.execute("""
                               UPDATE feedbacks
                               SET rating                  = COALESCE(%s, rating),
                                   is_helpful              = COALESCE(%s, is_helpful),
                                   comment                 = COALESCE(%s, comment),
                                   accuracy                = COALESCE(%s, accuracy),
                                   relevance               = COALESCE(%s, relevance),
                                   completeness            = COALESCE(%s, completeness),
                                   clarity                 = COALESCE(%s, clarity),
                                   improvement_suggestions = COALESCE(%s, improvement_suggestions),
                                   issue_types             = COALESCE(%s, issue_types),
                                   has_issues              = %s,
                                   feedback_type           = %s,
                                   meta_data                = COALESCE(%s, meta_data),
                                   updated_at              = %s
                               WHERE id = %s RETURNING id
                               """, (
                                   rating,
                                   is_helpful,
                                   comment,
                                   accuracy,
                                   relevance,
                                   completeness,
                                   clarity,
                                   improvement_suggestions,
                                   json.dumps(issue_types or []),
                                   bool(issue_types),
                                   feedback_type,
                                   json.dumps(meta_data or {}),
                                   datetime.utcnow(),
                                   feedback_id
                               ))

                print(f"  ✓ Updated feedback")

            else:
                # Create new feedback
                print(f"→ Creating new feedback...")

                # Determine sentiment
                sentiment = self._determine_sentiment(rating, is_helpful)

                cursor.execute("""
                               INSERT INTO feedbacks (uuid, user_id, query_id, rating, is_helpful,
                                                      comment, accuracy, relevance, completeness, clarity,
                                                      improvement_suggestions, feedback_type, sentiment,
                                                      has_issues, issue_types, meta_data,
                                                      status, created_at, updated_at)
                               VALUES (gen_random_uuid()::text, %s, %s, %s, %s,
                                       %s, %s, %s, %s, %s,
                                       %s, %s, %s,
                                       %s, %s, %s,
                                       %s, %s, %s) RETURNING id
                               """, (
                                   user_id,
                                   query_id,
                                   rating,
                                   is_helpful,
                                   comment,
                                   accuracy,
                                   relevance,
                                   completeness,
                                   clarity,
                                   improvement_suggestions,
                                   feedback_type,
                                   sentiment,
                                   bool(issue_types),
                                   json.dumps(issue_types or []),
                                   json.dumps(meta_data or {}),
                                   'submitted',
                                   datetime.utcnow(),
                                   datetime.utcnow()
                               ))

                feedback_id = cursor.fetchone()[0]

                print(f"  ✓ Created feedback (ID: {feedback_id})")

            # Update query with feedback flag
            cursor.execute("""
                           UPDATE queries
                           SET is_helpful = %s,
                               updated_at = %s
                           WHERE id = %s
                           """, (
                               1 if is_helpful else 0 if is_helpful is False else None,
                               datetime.utcnow(),
                               query_id
                           ))

            conn.commit()

            cursor.close()
            conn.close()

            print()
            print("=" * 80)
            print("✅ FEEDBACK SUBMITTED")
            print("=" * 80)
            print()

            return {
                'success': True,
                'feedback_id': feedback_id,
                'message': 'Feedback submitted successfully'
            }

        except Exception as e:
            print(f"❌ Error: {e}")
            print()
            return {
                'success': False,
                'error': str(e)
            }

    def _determine_sentiment(
            self,
            rating: Optional[int],
            is_helpful: Optional[bool]
    ) -> str:
        """Determine sentiment from rating and helpful flag"""
        if is_helpful is not None:
            return "positive" if is_helpful else "negative"

        if rating is not None:
            if rating >= 4:
                return "positive"
            elif rating <= 2:
                return "negative"
            else:
                return "neutral"

        return "neutral"

    def get_feedback(self, feedback_id: int) -> Optional[Dict[str, Any]]:
        """
        Get feedback by ID

        Args:
            feedback_id: Feedback ID

        Returns:
            Feedback dictionary or None
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cursor.execute("""
                           SELECT *
                           FROM feedbacks
                           WHERE id = %s
                           """, (feedback_id,))

            feedback = cursor.fetchone()

            cursor.close()
            conn.close()

            return dict(feedback) if feedback else None

        except Exception as e:
            print(f"Error getting feedback: {e}")
            return None

    def get_query_feedback(self, query_id: int) -> Optional[Dict[str, Any]]:
        """
        Get feedback for a specific query

        Args:
            query_id: Query ID

        Returns:
            Feedback dictionary or None
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cursor.execute("""
                           SELECT *
                           FROM feedbacks
                           WHERE query_id = %s
                           """, (query_id,))

            feedback = cursor.fetchone()

            cursor.close()
            conn.close()

            return dict(feedback) if feedback else None

        except Exception as e:
            print(f"Error getting feedback: {e}")
            return None

    def get_user_feedbacks(
            self,
            user_id: int,
            limit: int = 50,
            offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all feedbacks by a user

        Args:
            user_id: User ID
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of feedback dictionaries
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cursor.execute("""
                           SELECT f.*, q.query_text, q.response_text
                           FROM feedbacks f
                                    JOIN queries q ON f.query_id = q.id
                           WHERE f.user_id = %s
                           ORDER BY f.created_at DESC
                               LIMIT %s
                           OFFSET %s
                           """, (user_id, limit, offset))

            feedbacks = cursor.fetchall()

            cursor.close()
            conn.close()

            return [dict(f) for f in feedbacks]

        except Exception as e:
            print(f"Error getting feedbacks: {e}")
            return []

    def delete_feedback(self, feedback_id: int, user_id: int) -> bool:
        """
        Delete feedback

        Args:
            feedback_id: Feedback ID
            user_id: User ID (for authorization)

        Returns:
            True if successful
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Check ownership
            cursor.execute("""
                           SELECT user_id
                           FROM feedbacks
                           WHERE id = %s
                           """, (feedback_id,))

            result = cursor.fetchone()

            if not result:
                cursor.close()
                conn.close()
                return False

            feedback_user_id = result[0]

            if feedback_user_id != user_id:
                cursor.close()
                conn.close()
                return False

            # Delete feedback
            cursor.execute("""
                           DELETE
                           FROM feedbacks
                           WHERE id = %s
                           """, (feedback_id,))

            conn.commit()

            cursor.close()
            conn.close()

            return True

        except Exception as e:
            print(f"Error deleting feedback: {e}")
            return False