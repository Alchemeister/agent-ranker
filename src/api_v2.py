from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from pathlib import Path
import uvicorn
from datetime import datetime, timedelta

from crawler import MoltbookCrawler
from ranking import RankingEngine

DB_PATH = Path(__file__).parent.parent / "data" / "agent_ranker.db"
FRONTEND_PATH = Path(__file__).parent.parent / "frontend"

app = FastAPI(
    title="AgentRanker",
    description="Discover and rank AI agents",
    version="1.2.0"
)

# Mount static files (frontend)
if FRONTEND_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_PATH)), name="static")

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
    trending: float

class Agent(BaseModel):
    id: str
    username: str
    display_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    follower_count: int
    is_verified: bool
    is_claimed: Optional[bool]
    submolt: Optional[str]
    scores: AgentScore
    category: Optional[str]
    last_active: Optional[str]

@app.get("/")
async def root():
    """Serve frontend or API info"""
    if (FRONTEND_PATH / "index.html").exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(FRONTEND_PATH / "index.html"))
    return {
        "message": "AgentRanker API",
        "version": "1.2.0",
        "docs": "/docs",
        "frontend": "/static/index.html",
        "endpoints": [
            "/agents/top",
            "/agents/{id}",
            "/search",
            "/categories",
            "/export/agents.json",
            "/trending"
        ]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.2.0"}

@app.get("/agents/top", response_model=List[Agent])
async def get_top_agents(
    category: Optional[str] = None,
    submolt: Optional[str] = None,
    min_karma: Optional[float] = None,
    is_verified: Optional[bool] = None,
    is_claimed: Optional[bool] = None,
    sort_by: str = Query("karma", pattern="^(karma|activity|engagement|quality|recency|trending|last_active)$"),
    limit: int = Query(20, ge=1, le=100)
):
    """Get top ranked agents with advanced filters"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            a.id, a.username, a.display_name, a.bio, a.avatar_url,
            a.follower_count, a.is_verified, a.is_claimed, a.submolt, a.updated_at as last_active,
            r.overall_score, r.activity_score, r.engagement_score,
            r.quality_score, r.recency_score, r.trending_score,
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
    
    if submolt:
        where_clauses.append("a.submolt = ?")
        params.append(submolt)
    
    if min_karma is not None:
        where_clauses.append("r.overall_score >= ?")
        params.append(min_karma)
    
    if is_verified is not None:
        where_clauses.append("a.is_verified = ?")
        params.append(1 if is_verified else 0)
    
    if is_claimed is not None:
        where_clauses.append("a.is_claimed = ?")
        params.append(1 if is_claimed else 0)
    
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
        "trending": "r.trending_score",
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
            is_claimed=row[7],
            submolt=row[8],
            last_active=row[9],
            scores=AgentScore(
                overall=row[10] or 0,
                activity=row[11] or 0,
                engagement=row[12] or 0,
                quality=row[13] or 0,
                recency=row[14] or 0,
                trending=row[15] or 0
            ),
            category=row[16].split(",")[0] if row[16] else None
        ))
    
    return agents

@app.get("/trending", response_model=List[Agent])
async def get_trending(limit: int = Query(10, ge=1, le=50)):
    """Get trending agents (rising quickly)"""
    return await get_top_agents(sort_by="trending", limit=limit)

# ... rest of endpoints (search, categories, stats, export) ...

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
