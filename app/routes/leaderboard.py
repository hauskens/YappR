from flask import Blueprint, render_template, jsonify
from app.logger import logger
from datetime import datetime
from app.models import db, Users, ContentQueue, ContentQueueSubmission, Broadcaster
from app.models.enums import AccountSource
from app.services import UserService
from sqlalchemy import select, func, and_, desc, case
from app.cache import cache


leaderboard_blueprint = Blueprint(
    'leaderboard', __name__, url_prefix='/leaderboard', template_folder='templates')


@leaderboard_blueprint.route("", strict_slashes=False)
def leaderboard():
    """Main leaderboard page with user and broadcaster statistics"""
    try:
        logger.info("Loading leaderboard")
        
        # Get user leaderboard data
        user_stats = get_user_leaderboard_data()
        
        # Get broadcaster leaderboard data
        broadcaster_stats = get_broadcaster_leaderboard_data()
        
        return render_template(
            "leaderboard.html",
            user_stats=user_stats,
            broadcaster_stats=broadcaster_stats,
            now=datetime.now()
        )
    except Exception as e:
        logger.error("Error loading leaderboard: %s", e)
        return "Error loading leaderboard", 500


def get_user_leaderboard_data():
    """Get user statistics for leaderboard"""
    try:
        # Query to get user statistics for clips that have been watched
        user_stats_query = (
            select(
                Users.id,
                Users.name,
                Users.external_account_id,
                func.count(ContentQueueSubmission.id).label('total_clips'),
                func.avg(ContentQueue.score).label('average_rating'),
                func.count(func.distinct(ContentQueue.broadcaster_id)).label('broadcasters_contributed_to')
            )
            .select_from(Users)
            .join(ContentQueueSubmission, Users.id == ContentQueueSubmission.user_id)
            .join(ContentQueue, ContentQueueSubmission.content_queue_id == ContentQueue.id)
            .where(and_(
                ContentQueue.watched == True,  # Only count watched clips
                Users.account_type == AccountSource.Twitch  # Only Twitch users
            ))
            .group_by(Users.id, Users.name, Users.external_account_id)
            .having(func.count(ContentQueueSubmission.id) >= 1)  # At least 1 watched clip
            .order_by(desc(func.count(ContentQueueSubmission.id) * (func.coalesce(func.avg(ContentQueue.score), 0) + 1) * 100), desc('total_clips'), desc('average_rating'))
        )
        
        result = db.session.execute(user_stats_query).all()
        
        user_stats = []
        for row in result:
            avg_rating = float(row.average_rating or 0)
            total_clips = row.total_clips
            calculated_points = (total_clips * (avg_rating + 1) * 100)
            
            user_stats.append({
                'id': row.id,
                'name': row.name,
                'external_account_id': row.external_account_id,
                'total_clips': total_clips,
                'average_rating': round(avg_rating, 2),
                'total_rating_points': round(calculated_points, 1),
                'broadcasters_contributed_to': row.broadcasters_contributed_to
            })
        
        logger.info(f"Retrieved {len(user_stats)} user statistics")
        return user_stats
        
    except Exception as e:
        logger.error(f"Error getting user leaderboard data: {e}")
        return []


def get_broadcaster_leaderboard_data():
    """Get broadcaster statistics for leaderboard"""
    try:
        # Query to get broadcaster statistics
        broadcaster_stats_query = (
            select(
                Broadcaster.id,
                Broadcaster.name,
                func.count(ContentQueue.id).label('total_clips_watched'),
                func.avg(case((ContentQueue.score.isnot(None), ContentQueue.score))).label('average_rating_given'),
                func.count(func.distinct(ContentQueueSubmission.user_id)).label('unique_contributors'),
                func.sum(case((ContentQueue.score > 0, 1), else_=0)).label('positive_ratings'),
                func.sum(case((ContentQueue.score < 0, 1), else_=0)).label('negative_ratings'),
                func.sum(case((ContentQueue.score == 0, 1), else_=0)).label('neutral_ratings')
            )
            .select_from(Broadcaster)
            .join(ContentQueue, Broadcaster.id == ContentQueue.broadcaster_id)
            .join(ContentQueueSubmission, ContentQueue.id == ContentQueueSubmission.content_queue_id)
            .where(ContentQueue.watched == True)  # Only count watched clips
            .group_by(Broadcaster.id, Broadcaster.name)
            .having(func.count(ContentQueue.id) >= 1)  # At least 1 watched clip
            .order_by(desc('total_clips_watched'), func.coalesce(func.avg(case((ContentQueue.score.isnot(None), ContentQueue.score))), 0).desc())
        )
        
        result = db.session.execute(broadcaster_stats_query).all()
        
        broadcaster_stats = []
        for row in result:
            total_watched = row.total_clips_watched
            positive_rate = (row.positive_ratings / total_watched * 100) if total_watched > 0 else 0
            negative_rate = (row.negative_ratings / total_watched * 100) if total_watched > 0 else 0
            
            broadcaster_stats.append({
                'id': row.id,
                'name': row.name,
                'total_clips_watched': total_watched,
                'average_rating_given': round(float(row.average_rating_given or 0), 2),
                'unique_contributors': row.unique_contributors,
                'positive_ratings': row.positive_ratings,
                'negative_ratings': row.negative_ratings,
                'neutral_ratings': row.neutral_ratings,
                'positive_rate': round(positive_rate, 1),
                'negative_rate': round(negative_rate, 1)
            })
        
        logger.info(f"Retrieved {len(broadcaster_stats)} broadcaster statistics")
        return broadcaster_stats
        
    except Exception as e:
        logger.error(f"Error getting broadcaster leaderboard data: {e}")
        return []


@leaderboard_blueprint.route("/api/users")
def api_user_stats():
    """API endpoint for user statistics"""
    try:
        user_stats = get_user_leaderboard_data()
        return jsonify({"status": "success", "data": user_stats})
    except Exception as e:
        logger.error(f"Error in user stats API: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@leaderboard_blueprint.route("/api/broadcasters")
def api_broadcaster_stats():
    """API endpoint for broadcaster statistics"""
    try:
        broadcaster_stats = get_broadcaster_leaderboard_data()
        return jsonify({"status": "success", "data": broadcaster_stats})
    except Exception as e:
        logger.error(f"Error in broadcaster stats API: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500