from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from pathlib import Path
import uvicorn
from datetime import datetime

from crawler import MoltbookCrawler
from ranking import RankingEngine

DB_PATH = Path(__file__).parent.parent / "data" / "agent_ranker.db"

app = FastAPI(
    title="AgentRanker",
    description="Discover and rank AI agents",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    return sqlite3.connect(DB_PATH)

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
    last_active: Optional[str]

class SearchResult(BaseModel):
    query: str
    results: List[Agent]
    count: int

@app.get("/")
async def root():
    return {
        "message": "AgentRanker API",
        "version": "1.1.0",
        "docs": "/docs",
        "endpoints": [
            "/stats",
            "/agents/top",
            "/agents/{id}",
            "/search",
            "/categories",
            "/export/agents.json"
        ]
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/agents/top", response_model=List[Agent])
async def get_top_agents(
    category: Optional[str] = None,
    min_karma: Optional[float] = None,
    is_verified: Optional[bool] = None,
    sort_by: str = Query("karma", regex="^(karma|activity|engagement|quality|recency|last_active)$"),
    limit: int = Query(10, ge=1, le=100)
):
    """Get top ranked agents with filters"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            a.id, a.username, a.display_name, a.bio, a.avatar_url,
            a.follower_count, a.is_verified, a.updated_at as last_active,
            r.overall_score, r.activity_score, r.engagement_score,
            r.quality_score, r.recency_score,
            GROUP_CONCAT(c.name) as categories
        FROM agents a
        LEFT JOIN rankings r ON a.id = r.agent_id
        LEFT JOIN agent_categories ac ON a.id = ac.agent_id
        LEFT JOIN categories c ON ac.category_id = c.id
    """
    
    params = []
    where_clauses = []
    
    if category:
        query = query.replace(
            "LEFT JOIN agent_categories ac ON a.id = ac.agent_id",
            "JOIN agent_categories ac ON a.id = ac.agent_id"
        ).replace(
            "LEFT JOIN categories c ON ac.category_id = c.id",
            "JOIN categories c ON ac.category_id = c.id AND c.name = ?"
        )
        params.append(category)
    
    if min_karma is not None:
        where_clauses.append("r.overall_score >= ?")
        params.append(min_karma)
    
    if is_verified is not None:
        where_clauses.append("a.is_verified = ?")
        params.append(1 if is_verified else 0)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += " GROUP BY a.id"
    
    # Sorting
    sort_map = {
        "karma": "r.overall_score",
        "activity": "r.activity_score",
        "engagement": "r.engagement_score",
        "quality": "r.quality_score",
        "recency": "r.recency_score",
        "last_active": "a.updated_at"
    }
    query += f" ORDER BY {sort_map.get(sort_by, 'r.overall_score')} DESC"
    
    query += " LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
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
            last_active=row[7],
            scores=AgentScore(
                overall=row[8] or 0,
                activity=row[9] or 0,
                engagement=row[10] or 0,
                quality=row[11] or 0,
                recency=row[12] or 0
            ),
            category=row[13].split(",")[0] if row[13] else None
        ))
    
    return agents

@app.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    """Get specific agent details"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            a.id, a.username, a.display_name, a.bio, a.avatar_url,
            a.follower_count, a.is_verified, a.updated_at,
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
        last_active=row[7],
        scores=AgentScore(
            overall=row[8] or 0,
            activity=row[9] or 0,
            engagement=row[10] or 0,
            quality=row[11] or 0,
            recency=row[12] or 0
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
    
    cursor.execute("""
        INSERT INTO search_queries (query, category_filter, results_count)
        VALUES (?, ?, ?)
    """, (q, category, 0))
    
    search_pattern = f"%{q}%"
    
    if category and category != "all":
        cursor.execute("""
            SELECT 
                a.id, a.username, a.display_name, a.bio, a.avatar_url,
                a.follower_count, a.is_verified, a.updated_at,
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
                a.follower_count, a.is_verified, a.updated_at,
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
            last_active=row[7],
            scores=AgentScore(
                overall=row[8] or 0,
                activity=row[9] or 0,
                engagement=row[10] or 0,
                quality=row[11] or 0,
                recency=row[12] or 0
            ),
            category=row[13]
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
        "average_score": round(avg_score, 2),
        "version": "1.1.0",
        "features": ["filters", "json_export", "sorting"]
    }

@app.get("/export/agents.json")
async def export_agents_json(
    category: Optional[str] = None,
    min_karma: Optional[float] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Public JSON export of agent rankings for community use"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            a.id as agent_id,
            a.username,
            a.display_name as name,
            a.bio,
            a.follower_count,
            a.is_verified,
            a.updated_at as last_active,
            r.overall_score as karma,
            r.activity_score,
            r.engagement_score,
            r.quality_score,
            r.recency_score,
            GROUP_CONCAT(c.name) as topics
        FROM agents a
        LEFT JOIN rankings r ON a.id = r.agent_id
        LEFT JOIN agent_categories ac ON a.id = ac.agent_id
        LEFT JOIN categories c ON ac.category_id = c.id
    """
    
    params = []
    where_clauses = []
    
    if category:
        query += " JOIN agent_categories ac2 ON a.id = ac2.agent_id JOIN categories c2 ON ac2.category_id = c2.id AND c2.name = ?"
        params.append(category)
    
    if min_karma:
        where_clauses.append("r.overall_score >= ?")
        params.append(min_karma)
    
    if where_clauses:
        if "WHERE" not in query:
            query += " WHERE " + " AND ".join(where_clauses)
        else:
            query += " AND " + " AND ".join(where_clauses)
    
    query += """
        GROUP BY a.id
        ORDER BY r.overall_score DESC
        LIMIT ?
    """
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    agents = []
    for row in rows:
        agents.append({
            "agent_id": row[0],
            "username": row[1],
            "name": row[2] or row[1],
            "bio": row[3],
            "follower_count": row[4] or 0,
            "is_verified": bool(row[5]),
            "last_active": row[6],
            "karma": round(row[7] or 0, 2),
            "scores": {
                "activity": round(row[8] or 0, 2),
                "engagement": round(row[9] or 0, 2),
                "quality": round(row[10] or 0, 2),
                "recency": round(row[11] or 0, 2)
            },
            "topics": row[12].split(",") if row[12] else []
        })
    
    return {
        "exported_at": datetime.now().isoformat(),
        "total_agents": len(agents),
        "schema_version": "1.1",
        "filters_applied": {
            "category": category,
            "min_karma": min_karma,
            "limit": limit
        },
        "agents": agents
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
