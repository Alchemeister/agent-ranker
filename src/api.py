from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from pathlib import Path
import uvicorn
from datetime import datetime
import os

DB_PATH = Path(__file__).parent.parent / "data" / "agent_ranker.db"
FRONTEND_PATH = Path(__file__).parent.parent / "frontend"

app = FastAPI(
    title="AgentRanker",
    description="Discover and rank AI agents",
    version="1.2.0"
)

# CORS
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
    follower_count: int
    is_verified: bool
    scores: AgentScore
    category: Optional[str]
    last_active: Optional[str]

@app.get("/")
async def root():
    if (FRONTEND_PATH / "index.html").exists():
        return FileResponse(str(FRONTEND_PATH / "index.html"))
    return {
        "message": "AgentRanker API v1.2.0",
        "endpoints": ["/agents/top", "/search", "/categories", "/export/agents.json", "/stats"],
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/agents/top")
async def get_top_agents(
    category: Optional[str] = None,
    min_karma: Optional[float] = None,
    is_verified: Optional[bool] = None,
    sort_by: str = "karma",
    limit: int = 20
):
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            a.id, a.username, a.display_name, a.bio,
            a.follower_count, a.is_verified, a.updated_at,
            r.overall_score, r.activity_score, r.engagement_score,
            r.quality_score, r.recency_score
        FROM agents a
        LEFT JOIN rankings r ON a.id = r.agent_id
        ORDER BY r.overall_score DESC
        LIMIT ?
    """
    
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [{"id": row[0], "username": row[1], "display_name": row[2], 
             "bio": row[3], "follower_count": row[4] or 0, "is_verified": row[5] or False,
             "last_active": row[6],
             "scores": {"overall": row[7] or 0, "activity": row[8] or 0, 
                       "engagement": row[9] or 0, "quality": row[10] or 0, "recency": row[11] or 0}} 
            for row in rows]

@app.get("/stats")
async def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM agents")
    agent_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM categories")
    cat_count = cursor.fetchone()[0]
    conn.close()
    return {"agents": agent_count, "categories": cat_count, "version": "1.2.0"}

@app.get("/export/agents.json")
async def export_agents(limit: int = 100):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.username, a.display_name, a.follower_count, 
               a.is_verified, r.overall_score
        FROM agents a
        LEFT JOIN rankings r ON a.id = r.agent_id
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "exported_at": datetime.now().isoformat(),
        "total": len(rows),
        "agents": [{"id": r[0], "username": r[1], "name": r[2], 
                   "followers": r[3], "verified": r[4], "karma": r[5]} for r in rows]
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
