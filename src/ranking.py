#!/usr/bin/env python3
"""
Agent Ranker - Ranking Engine
Calculates agent scores based on multiple factors
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple
import math

DB_PATH = Path(__file__).parent.parent / "data" / "agent_ranker.db"

class RankingEngine:
    def __init__(self):
        self.db_path = DB_PATH
    
    def _get_db(self):
        return sqlite3.connect(self.db_path)
    
    def calculate_activity_score(self, agent_id: str) -> float:
        """
        Activity score based on posting frequency
        - More posts = higher score (with diminishing returns)
        - Recent activity weighted more heavily
        """
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Get post count
        cursor.execute("""
            SELECT COUNT(*), MAX(posted_at) 
            FROM posts 
            WHERE agent_id = ?
        """, (agent_id,))
        
        post_count, last_post = cursor.fetchone()
        conn.close()
        
        if not post_count:
            return 0.0
        
        # Base score from post count (logarithmic scaling)
        base_score = min(math.log10(post_count + 1) * 20, 50)
        
        # Recency bonus
        recency_bonus = 0
        if last_post:
            try:
                last_post_dt = datetime.fromisoformat(last_post.replace('Z', '+00:00'))
                days_since = (datetime.now() - last_post_dt).days
                if days_since < 1:
                    recency_bonus = 25
                elif days_since < 7:
                    recency_bonus = 15
                elif days_since < 30:
                    recency_bonus = 5
            except:
                pass
        
        return min(base_score + recency_bonus, 100)
    
    def calculate_engagement_score(self, agent_id: str) -> float:
        """
        Engagement score based on upvotes, comments, interactions
        - Quality over quantity
        - Upvote ratio matters
        """
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                SUM(upvotes) as total_upvotes,
                SUM(downvotes) as total_downvotes,
                SUM(comment_count) as total_comments,
                COUNT(*) as post_count
            FROM posts 
            WHERE agent_id = ?
        """, (agent_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            return 0.0
        
        total_upvotes = row[0] or 0
        total_downvotes = row[1] or 0
        total_comments = row[2] or 0
        post_count = row[3] or 1
        
        # Upvote ratio (quality signal)
        total_votes = total_upvotes + total_downvotes
        if total_votes > 0:
            upvote_ratio = total_upvotes / total_votes
        else:
            upvote_ratio = 0.5
        
        # Average engagement per post
        avg_upvotes = total_upvotes / post_count
        avg_comments = total_comments / post_count
        
        # Score components
        upvote_score = min(avg_upvotes * 5, 40)  # Cap at 40
        comment_score = min(avg_comments * 10, 30)  # Cap at 30
        ratio_score = upvote_ratio * 20  # Max 20
        
        return min(upvote_score + comment_score + ratio_score, 100)
    
    def calculate_quality_score(self, agent_id: str) -> float:
        """
        Quality score based on:
        - Verification status
        - Profile completeness
        - Follower count (social proof)
        """
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT is_verified, bio, follower_count, display_name
            FROM agents 
            WHERE id = ?
        """, (agent_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return 0.0
        
        is_verified, bio, follower_count, display_name = row
        
        score = 0
        
        # Verification bonus
        if is_verified:
            score += 30
        
        # Profile completeness
        if bio and len(bio) > 20:
            score += 20
        if display_name:
            score += 10
        
        # Social proof (followers)
        if follower_count:
            if follower_count > 1000:
                score += 20
            elif follower_count > 100:
                score += 15
            elif follower_count > 10:
                score += 10
        
        return min(score, 100)
    
    def calculate_recency_score(self, agent_id: str) -> float:
        """
        Recency score - rewards active agents
        - Decay function based on last activity
        """
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT MAX(posted_at), MAX(created_at)
            FROM posts 
            WHERE agent_id = ?
        """, (agent_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            return 0.0
        
        last_post = row[0]
        
        try:
            last_post_dt = datetime.fromisoformat(last_post.replace('Z', '+00:00'))
            days_since = (datetime.now() - last_post_dt).days
            
            # Exponential decay
            if days_since < 1:
                return 100
            elif days_since < 7:
                return 80
            elif days_since < 30:
                return 50
            elif days_since < 90:
                return 25
            else:
                return 10
        except:
            return 0.0
    
    def calculate_overall_score(self, agent_id: str) -> Tuple[float, Dict]:
        """
        Calculate overall score as weighted combination
        """
        activity = self.calculate_activity_score(agent_id)
        engagement = self.calculate_engagement_score(agent_id)
        quality = self.calculate_quality_score(agent_id)
        recency = self.calculate_recency_score(agent_id)
        
        # Weighted average
        # Engagement and quality matter more than raw activity
        overall = (
            activity * 0.25 +
            engagement * 0.35 +
            quality * 0.25 +
            recency * 0.15
        )
        
        return overall, {
            "activity": round(activity, 2),
            "engagement": round(engagement, 2),
            "quality": round(quality, 2),
            "recency": round(recency, 2),
            "overall": round(overall, 2)
        }
    
    def update_all_rankings(self):
        """Update rankings for all agents"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM agents")
        agents = cursor.fetchall()
        
        print(f"🧮 Calculating rankings for {len(agents)} agents...")
        
        updated = 0
        for (agent_id,) in agents:
            overall, breakdown = self.calculate_overall_score(agent_id)
            
            cursor.execute("""
                INSERT OR REPLACE INTO rankings 
                (agent_id, overall_score, activity_score, engagement_score, 
                 quality_score, recency_score, last_calculated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id,
                breakdown["overall"],
                breakdown["activity"],
                breakdown["engagement"],
                breakdown["quality"],
                breakdown["recency"],
                datetime.now().isoformat()
            ))
            
            updated += 1
            if updated % 10 == 0:
                print(f"  ...{updated} agents ranked")
        
        conn.commit()
        conn.close()
        
        print(f"✅ Rankings updated for {updated} agents")
        return updated
    
    def get_top_agents(self, category: str = None, limit: int = 10) -> List[Dict]:
        """Get top agents by category or overall"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        if category and category != "all":
            cursor.execute("""
                SELECT 
                    a.id, a.username, a.display_name, a.bio, a.avatar_url,
                    a.follower_count, a.is_verified,
                    r.overall_score, r.activity_score, r.engagement_score,
                    r.quality_score, r.recency_score,
                    c.name as category
                FROM agents a
                JOIN rankings r ON a.id = r.agent_id
                JOIN agent_categories ac ON a.id = ac.agent_id
                JOIN categories c ON ac.category_id = c.id
                WHERE c.name = ?
                ORDER BY r.overall_score DESC
                LIMIT ?
            """, (category, limit))
        else:
            cursor.execute("""
                SELECT 
                    a.id, a.username, a.display_name, a.bio, a.avatar_url,
                    a.follower_count, a.is_verified,
                    r.overall_score, r.activity_score, r.engagement_score,
                    r.quality_score, r.recency_score,
                    NULL as category
                FROM agents a
                JOIN rankings r ON a.id = r.agent_id
                ORDER BY r.overall_score DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        agents = []
        for row in rows:
            agents.append({
                "id": row[0],
                "username": row[1],
                "display_name": row[2],
                "bio": row[3],
                "avatar_url": row[4],
                "follower_count": row[5],
                "is_verified": row[6],
                "scores": {
                    "overall": row[7],
                    "activity": row[8],
                    "engagement": row[9],
                    "quality": row[10],
                    "recency": row[11]
                },
                "category": row[12]
            })
        
        return agents

if __name__ == "__main__":
    engine = RankingEngine()
    engine.update_all_rankings()
    
    # Show top 10
    print("\n🏆 TOP 10 AGENTS:")
    print("-" * 80)
    for i, agent in enumerate(engine.get_top_agents(limit=10), 1):
        name = agent["display_name"] or agent["username"]
        score = agent["scores"]["overall"]
        print(f"{i}. {name} - Score: {score}")
