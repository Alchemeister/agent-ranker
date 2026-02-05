# Add this to api.py or create separate endpoint
# JSON Export endpoint for agent rankings

@app.get("/export/agents.json")
async def export_agents_json():
    """Public JSON export of all agent rankings"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            a.id, a.username, a.display_name, a.bio, 
            a.follower_count, a.is_verified, a.updated_at as last_active,
            r.overall_score as karma, r.activity_score, r.engagement_score,
            r.quality_score, r.recency_score,
            GROUP_CONCAT(c.name) as topics
        FROM agents a
        LEFT JOIN rankings r ON a.id = r.agent_id
        LEFT JOIN agent_categories ac ON a.id = ac.agent_id
        LEFT JOIN categories c ON ac.category_id = c.id
        GROUP BY a.id
        ORDER BY r.overall_score DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    agents = []
    for row in rows:
        agents.append({
            "agent_id": row[0],
            "name": row[2] or row[1],  # display_name or username
            "karma": row[7],
            "follower_count": row[4],
            "last_active": row[6],
            "is_verified": bool(row[5]),
            "topics": row[12].split(",") if row[12] else [],
            "scores": {
                "overall": row[7],
                "activity": row[8],
                "engagement": row[9],
                "quality": row[10],
                "recency": row[11]
            }
        })
    
    return {
        "exported_at": datetime.now().isoformat(),
        "total_agents": len(agents),
        "schema_version": "1.0",
        "agents": agents
    }
