#!/usr/bin/env python3
"""
Agent Ranker - Moltbook Crawler
Scrapes agent data from Moltbook for ranking
"""

import sqlite3
import requests
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import time

# Config
DB_PATH = Path(__file__).parent.parent / "data" / "agent_ranker.db"
MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"
RATE_LIMIT_DELAY = 1  # Seconds between requests

class MoltbookCrawler:
    def __init__(self, api_key: Optional[str] = None):
        self.db_path = DB_PATH
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AgentRanker/1.0 (Analysis Bot)",
            "Accept": "application/json"
        })
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"
        
        self._init_db()
    
    def _init_db(self):
        """Initialize database with schema"""
        DB_PATH.parent.mkdir(exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        with open(Path(__file__).parent.parent / "config" / "schema.sql", "r") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
    
    def _get_db(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def fetch_recent_posts(self, limit: int = 100) -> List[Dict]:
        """Fetch recent posts from Moltbook"""
        try:
            # Try to get posts from the general submolt
            url = f"{MOLTBOOK_API_BASE}/posts"
            params = {"submolt": "general", "limit": limit}
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("posts", [])
            else:
                print(f"API error: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error fetching posts: {e}")
            return []
    
    def extract_agent_from_post(self, post: Dict) -> Optional[Dict]:
        """Extract agent info from a post"""
        author = post.get("author", {})
        if not author:
            return None
        
        return {
            "id": author.get("id"),
            "username": author.get("username"),
            "display_name": author.get("display_name"),
            "bio": author.get("bio", ""),
            "avatar_url": author.get("avatar_url"),
            "joined_at": author.get("created_at"),
            "is_verified": author.get("is_verified", False),
            "follower_count": author.get("follower_count", 0)
        }
    
    def categorize_agent(self, agent: Dict, posts: List[Dict]) -> List[str]:
        """Categorize agent based on their content"""
        categories = []
        
        # Combine all text from agent's posts
        all_text = " ".join([
            f"{p.get('title', '')} {p.get('content', '')}"
            for p in posts
        ]).lower()
        
        # Keyword-based categorization
        category_keywords = {
            "coding": ["code", "python", "javascript", "programming", "developer", "api", "github", "script", "automation", "dev"],
            "trading": ["trade", "crypto", "bitcoin", "ethereum", "market", "price", "signal", "profit", "loss", "portfolio"],
            "research": ["research", "analyze", "study", "data", "report", "findings", "investigate"],
            "writing": ["write", "content", "blog", "article", "copy", "story", "documentation"],
            "design": ["design", "ui", "ux", "visual", "graphic", "art", "creative"],
            "automation": ["automation", "workflow", "cron", "script", "bot", "schedule", "integrate"],
            "community": ["community", "moderate", "engage", "social", "discord", "telegram"],
            "data": ["data", "scrape", "extract", "csv", "json", "database", "analyze"],
            "marketing": ["marketing", "seo", "growth", "viral", "promote", "audience"]
        }
        
        for category, keywords in category_keywords.items():
            score = sum(1 for kw in keywords if kw in all_text)
            if score >= 2:  # At least 2 keyword matches
                categories.append(category)
        
        if not categories:
            categories.append("general")
        
        return categories
    
    def save_agent(self, agent: Dict):
        """Save agent to database"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO agents 
            (id, username, display_name, bio, avatar_url, joined_at, 
             follower_count, is_verified, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agent["id"],
            agent["username"],
            agent.get("display_name"),
            agent.get("bio", ""),
            agent.get("avatar_url"),
            agent.get("joined_at"),
            agent.get("follower_count", 0),
            agent.get("is_verified", False),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def save_post(self, post: Dict):
        """Save post to database"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        author = post.get("author", {})
        agent_id = author.get("id") if author else None
        
        if not agent_id:
            conn.close()
            return
        
        cursor.execute("""
            INSERT OR REPLACE INTO posts 
            (id, agent_id, title, content, submolt, upvotes, downvotes, 
             comment_count, posted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post.get("id"),
            agent_id,
            post.get("title", ""),
            post.get("content", ""),
            post.get("submolt", "general"),
            post.get("upvotes", 0),
            post.get("downvotes", 0),
            post.get("comment_count", 0),
            post.get("created_at")
        ))
        
        conn.commit()
        conn.close()
    
    def save_categories(self, agent_id: str, categories: List[str]):
        """Save agent categories"""
        conn = self._get_db()
        cursor = conn.cursor()
        
        for category_name in categories:
            # Get category ID
            cursor.execute("SELECT id FROM categories WHERE name = ?", (category_name,))
            row = cursor.fetchone()
            
            if row:
                category_id = row[0]
                
                # Link agent to category
                cursor.execute("""
                    INSERT OR REPLACE INTO agent_categories (agent_id, category_id, confidence)
                    VALUES (?, ?, ?)
                """, (agent_id, category_id, 0.7))
        
        conn.commit()
        conn.close()
    
    def crawl(self, post_limit: int = 100):
        """Main crawl function"""
        print(f"🕷️  Starting Moltbook crawl (limit: {post_limit})")
        
        posts = self.fetch_recent_posts(post_limit)
        print(f"📥 Fetched {len(posts)} posts")
        
        agents_processed = set()
        
        for post in posts:
            # Save post
            self.save_post(post)
            
            # Extract and save agent
            agent = self.extract_agent_from_post(post)
            if agent and agent["id"] not in agents_processed:
                self.save_agent(agent)
                agents_processed.add(agent["id"])
                
                # Get all posts from this agent for categorization
                agent_posts = [p for p in posts if p.get("author", {}).get("id") == agent["id"]]
                categories = self.categorize_agent(agent, agent_posts)
                self.save_categories(agent["id"], categories)
                
                print(f"  ✓ Indexed: {agent['username']} ({', '.join(categories)})")
            
            time.sleep(RATE_LIMIT_DELAY)
        
        print(f"✅ Crawl complete. Indexed {len(agents_processed)} agents")
        return len(agents_processed)

if __name__ == "__main__":
    # Use the API key from memory
    API_KEY = "moltbook_sk_-wMhZ7jrsOWTCifzeKwY-xI29vjhp_JW"
    
    crawler = MoltbookCrawler(api_key=API_KEY)
    count = crawler.crawl(post_limit=100)
    print(f"\nTotal agents indexed: {count}")
