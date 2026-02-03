#!/usr/bin/env python3
"""
Agent Ranker - FastAPI Backend
REST API for agent discovery and ranking
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from pathlib import Path
import uvicorn

from crawler import MoltbookCrawler
from ranking import RankingEngine

DB_PATH = Path(__file__).parent.parent / "data" / "agent_ranker.db"

app = FastAPI(
    title="AgentRanker",
    description="Discover and rank AI agents",
    version="1.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    return sqlite3.connect(DB_PATH)

# Pydantic models
class AgentScore(BaseModel):
    overall: float
    activity: float
    engagement: float
    quality: float
    recency: float

class Agent(BaseModel):
    id: str
    username: str
    display_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    follower_count: int
    is_verified: bool
    scores: AgentScore
    category: Optional[str]

class SearchResult(BaseModel):
    query: str
    results: List[Agent]
    count: int

# Routes
@app.get("/")
async def root():
    return {
        "message": "AgentRanker API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/agents/top", response_model=List[Agent])
async def get_top_agents(
    category: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100)
):
    """Get top ranked agents"""
    engine = RankingEngine()
    agents = engine.get_top_agents(category=category, limit=limit)
    return agents

@app.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    """Get specific agent details"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            a.id, a.username, a.display_name, a.bio, a.avatar_url,
            a.follower_count, a.is_verified,
            r.overall_score, r.activity_score, r.engagement_score,
            r.quality_score, r.recency_score
        FROM agents a
        LEFT JOIN rankings r ON a.id = r.agent_id
        WHERE a.id = ?
    """, (agent_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return Agent(
        id=row[0],
        username=row[1],
        display_name=row[2],
        bio=row[3],
        avatar_url=row[4],
        follower_count=row[5] or 0,
        is_verified=row[6] or False,
        scores=AgentScore(
            overall=row[7] or 0,
            activity=row[8] or 0,
            engagement=row[9] or 0,
            quality=row[10] or 0,
            recency=row[11] or 0
        ),
        category=None
    )

@app.get("/search", response_model=SearchResult)
async def search_agents(
    q: str = Query(..., min_length=2),
    category: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50)
):
    """Search agents by name, bio, or category"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Log search query
    cursor.execute("""
        INSERT INTO search_queries (query, category_filter, results_count)
        VALUES (?, ?, ?)
    """, (q, category, 0))
    
    search_pattern = f"%{q}%"
    
    if category and category != "all":
        cursor.execute("""
            SELECT 
                a.id, a.username, a.display_name, a.bio, a.avatar_url,
                a.follower_count, a.is_verified,
                r.overall_score, r.activity_score, r.engagement_score,
                r.quality_score, r.recency_score,
                c.name as category
            FROM agents a
            LEFT JOIN rankings r ON a.id = r.agent_id
            LEFT JOIN agent_categories ac ON a.id = ac.agent_id
            LEFT JOIN categories c ON ac.category_id = c.id
            WHERE (a.username LIKE ? OR a.display_name LIKE ? OR a.bio LIKE ?)
            AND c.name = ?
            ORDER BY r.overall_score DESC
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, category, limit))
    else:
        cursor.execute("""
            SELECT 
                a.id, a.username, a.display_name, a.bio, a.avatar_url,
                a.follower_count, a.is_verified,
                r.overall_score, r.activity_score, r.engagement_score,
                r.quality_score, r.recency_score,
                NULL as category
            FROM agents a
            LEFT JOIN rankings r ON a.id = r.agent_id
            WHERE a.username LIKE ? OR a.display_name LIKE ? OR a.bio LIKE ?
            ORDER BY r.overall_score DESC
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, limit))
    
    rows = cursor.fetchall()
    conn.commit()
    conn.close()
    
    agents = []
    for row in rows:
        agents.append(Agent(
            id=row[0],
            username=row[1],
            display_name=row[2],
            bio=row[3],
            avatar_url=row[4],
            follower_count=row[5] or 0,
            is_verified=row[6] or False,
            scores=AgentScore(
                overall=row[7] or 0,
                activity=row[8] or 0,
                engagement=row[9] or 0,
                quality=row[10] or 0,
                recency=row[11] or 0
            ),
            category=row[12]
        ))
    
    return SearchResult(
        query=q,
        results=agents,
        count=len(agents)
    )

@app.get("/categories")
async def get_categories():
    """Get all categories"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name, description, post_count 
        FROM categories 
        ORDER BY name
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {"name": row[0], "description": row[1], "count": row[2]}
        for row in rows
    ]

@app.post("/admin/crawl")
async def trigger_crawl(limit: int = 100):
    """Trigger a crawl (admin only)"""
    API_KEY = "moltbook_sk_-wMhZ7jrsOWTCifzeKwY-xI29vjhp_JW"
    
    crawler = MoltbookCrawler(api_key=API_KEY)
    count = crawler.crawl(post_limit=limit)
    
    # Update rankings
    engine = RankingEngine()
    engine.update_all_rankings()
    
    return {
        "message": "Crawl completed",
        "agents_indexed": count
    }

@app.get("/stats")
async def get_stats():
    """Get platform stats"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM agents")
    agent_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM posts")
    post_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM categories")
    category_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(overall_score) FROM rankings")
    avg_score = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        "agents_indexed": agent_count,
        "posts_indexed": post_count,
        "categories": category_count,
        "average_score": round(avg_score, 2)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
