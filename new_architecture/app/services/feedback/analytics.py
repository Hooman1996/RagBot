# app/services/feedback/analytics.py

"""
Feedback Analytics - Minimal Safe Version
==========================================
Analytics and statistics for feedback data
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

import os
from dotenv import load_dotenv
load_dotenv()

class FeedbackAnalytics:
    """Analytics service for feedback data"""

    def __init__(
            self,

            db_host: str = os.getenv("POSTGRES_HOST"),
            db_port: int = os.getenv("POSTGRES_PORT"),
            db_name: str = os.getenv("POSTGRES_DB"),
            db_user: str = os.getenv("POSTGRES_USER"),
            db_password: str = os.getenv("POSTGRES_PASSWORD"),

    ):
        """Initialize analytics service"""
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

    def get_overall_stats(self) -> Dict[str, Any]:
        """
        Get overall feedback statistics

        Returns:
            Dictionary with statistics
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Total feedbacks
            cursor.execute("SELECT COUNT(*) FROM feedbacks")
            total_feedbacks = cursor.fetchone()[0]

            # Average rating
            cursor.execute("""
                           SELECT AVG(rating)
                           FROM feedbacks
                           WHERE rating IS NOT NULL
                           """)
            avg_rating = cursor.fetchone()[0]

            # Helpful vs not helpful
            cursor.execute("""
                           SELECT COUNT(CASE WHEN is_helpful = true THEN 1 END)  as helpful,
                                  COUNT(CASE WHEN is_helpful = false THEN 1 END) as not_helpful
                           FROM feedbacks
                           WHERE is_helpful IS NOT NULL
                           """)
            helpful_stats = cursor.fetchone()

            # Rating distribution
            cursor.execute("""
                           SELECT rating, COUNT(*)
                           FROM feedbacks
                           WHERE rating IS NOT NULL
                           GROUP BY rating
                           ORDER BY rating
                           """)
            rating_distribution = dict(cursor.fetchall())

            # Sentiment distribution
            cursor.execute("""
                           SELECT sentiment, COUNT(*)
                           FROM feedbacks
                           WHERE sentiment IS NOT NULL
                           GROUP BY sentiment
                           """)
            sentiment_distribution = dict(cursor.fetchall())

            # Average scores by category
            cursor.execute("""
                           SELECT AVG(accuracy)     as avg_accuracy,
                                  AVG(relevance)    as avg_relevance,
                                  AVG(completeness) as avg_completeness,
                                  AVG(clarity)      as avg_clarity
                           FROM feedbacks
                           """)
            category_averages = cursor.fetchone()

            cursor.close()
            conn.close()

            return {
                'total_feedbacks': total_feedbacks,
                'average_rating': round(float(avg_rating), 2) if avg_rating else None,
                'helpful_count': helpful_stats[0] if helpful_stats else 0,
                'not_helpful_count': helpful_stats[1] if helpful_stats else 0,
                'rating_distribution': rating_distribution,
                'sentiment_distribution': sentiment_distribution,
                'category_averages': {
                    'accuracy': round(float(category_averages[0]), 2) if category_averages[0] else None,
                    'relevance': round(float(category_averages[1]), 2) if category_averages[1] else None,
                    'completeness': round(float(category_averages[2]), 2) if category_averages[2] else None,
                    'clarity': round(float(category_averages[3]), 2) if category_averages[3] else None,
                }
            }

        except Exception as e:
            print(f"Error getting stats: {e}")
            return {}

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Get feedback statistics for a specific user

        Args:
            user_id: User ID

        Returns:
            Dictionary with user statistics
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Total feedbacks
            cursor.execute("""
                           SELECT COUNT(*)
                           FROM feedbacks
                           WHERE user_id = %s
                           """, (user_id,))
            total_feedbacks = cursor.fetchone()[0]

            # Average rating
            cursor.execute("""
                           SELECT AVG(rating)
                           FROM feedbacks
                           WHERE user_id = %s
                             AND rating IS NOT NULL
                           """, (user_id,))
            avg_rating = cursor.fetchone()[0]

            # Recent feedbacks
            cursor.execute("""
                           SELECT rating, is_helpful, created_at
                           FROM feedbacks
                           WHERE user_id = %s
                           ORDER BY created_at DESC LIMIT 10
                           """, (user_id,))
            recent_feedbacks = cursor.fetchall()

            cursor.close()
            conn.close()

            return {
                'total_feedbacks': total_feedbacks,
                'average_rating': round(float(avg_rating), 2) if avg_rating else None,
                'recent_feedbacks': [
                    {
                        'rating': r[0],
                        'is_helpful': r[1],
                        'created_at': r[2]
                    }
                    for r in recent_feedbacks
                ]
            }

        except Exception as e:
            print(f"Error getting user stats: {e}")
            return {}

    def get_trending_issues(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most common issues reported in feedback

        Args:
            limit: Maximum number of issues to return

        Returns:
            List of issue dictionaries
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT jsonb_array_elements_text(issue_types::jsonb) as issue,
                                  COUNT(*) as count
                           FROM feedbacks
                           WHERE has_issues = true AND issue_types IS NOT NULL
                           GROUP BY issue
                           ORDER BY count DESC
                               LIMIT %s
                           """, (limit,))

            issues = cursor.fetchall()

            cursor.close()
            conn.close()

            return [
                {
                    'issue_type': issue[0],
                    'count': issue[1]
                }
                for issue in issues
            ]

        except Exception as e:
            print(f"Error getting trending issues: {e}")
            return []

    def get_feedback_over_time(
            self,
            days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get feedback statistics over time

        Args:
            days: Number of days to look back

        Returns:
            List of daily statistics
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            start_date = datetime.utcnow() - timedelta(days=days)

            cursor.execute("""
                           SELECT
                               DATE (created_at) as date, COUNT (*) as total, AVG (rating) as avg_rating, COUNT (CASE WHEN is_helpful = true THEN 1 END) as helpful_count
                           FROM feedbacks
                           WHERE created_at >= %s
                           GROUP BY DATE (created_at)
                           ORDER BY date
                           """, (start_date,))

            results = cursor.fetchall()

            cursor.close()
            conn.close()

            return [
                {
                    'date': str(r[0]),
                    'total': r[1],
                    'average_rating': round(float(r[2]), 2) if r[2] else None,
                    'helpful_count': r[3]
                }
                for r in results
            ]

        except Exception as e:
            print(f"Error getting feedback over time: {e}")
            return []