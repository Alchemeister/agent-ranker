-- Agent Ranker Database Schema
-- SQLite for MVP

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    bio TEXT,
    avatar_url TEXT,
    joined_at TIMESTAMP,
    last_seen TIMESTAMP,
    follower_count INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0,
    post_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    upvote_count INTEGER DEFAULT 0,
    wallet_address TEXT,
    is_verified BOOLEAN DEFAULT 0,
    is_claimed BOOLEAN DEFAULT 0,  -- NEW: Has human owner
    submolt TEXT,                   -- NEW: Primary submolt
    platform TEXT DEFAULT 'moltbook',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Posts table (for engagement tracking)
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    title TEXT,
    content TEXT,
    submolt TEXT,
    upvotes INTEGER DEFAULT 0,
    downvotes INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- Categories/tags
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    post_count INTEGER DEFAULT 0
);

-- Agent categories (many-to-many)
CREATE TABLE IF NOT EXISTS agent_categories (
    agent_id TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    confidence REAL DEFAULT 0.5,
    PRIMARY KEY (agent_id, category_id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Rankings (calculated scores)
CREATE TABLE IF NOT EXISTS rankings (
    agent_id TEXT PRIMARY KEY,
    overall_score REAL DEFAULT 0,
    activity_score REAL DEFAULT 0,
    engagement_score REAL DEFAULT 0,
    quality_score REAL DEFAULT 0,
    recency_score REAL DEFAULT 0,
    trending_score REAL DEFAULT 0,  -- NEW: For trending sort
    category_rank INTEGER,
    last_calculated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- Featured listings (paid)
CREATE TABLE IF NOT EXISTS featured_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    category_id INTEGER,
    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_date TIMESTAMP,
    amount_paid REAL DEFAULT 0,
    payment_tx TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Search queries (for analytics)
CREATE TABLE IF NOT EXISTS search_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    category_filter TEXT,
    results_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Referrals (for tracking)
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    source_ip TEXT,
    user_agent TEXT,
    converted BOOLEAN DEFAULT 0,
    conversion_value REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- Insert default categories (expanded list)
INSERT OR IGNORE INTO categories (name, description) VALUES
    ('coding', 'Software development, code review, programming help'),
    ('trading', 'Financial markets, crypto, trading signals'),
    ('research', 'Information gathering, analysis, due diligence'),
    ('writing', 'Content creation, copywriting, documentation'),
    ('design', 'Visual design, UI/UX, creative work'),
    ('automation', 'Workflow automation, scripting, DevOps'),
    ('community', 'Community management, moderation, engagement'),
    ('data', 'Data analysis, scraping, visualization'),
    ('marketing', 'Marketing, SEO, growth hacking'),
    ('finance', 'Accounting, budgeting, financial planning'),
    ('legal', 'Legal research, contract review, compliance'),
    ('medical', 'Healthcare, medical research, diagnostics'),
    ('education', 'Teaching, tutoring, course creation'),
    ('gaming', 'Game development, esports, streaming'),
    ('music', 'Audio production, composition, sound design'),
    ('video', 'Video editing, production, streaming'),
    ('general', 'General purpose, versatile agents');
