#!/bin/bash
# Start AgentRanker services

echo "🦞 Starting AgentRanker..."

# Check if we're in the right directory
if [ ! -f "src/api.py" ]; then
    echo "❌ Error: Run from agent-ranker directory"
    exit 1
fi

# Install dependencies if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Initialize data if empty
if [ ! -f "data/agent_ranker.db" ]; then
    echo "🗄️  Initializing database..."
    python3 src/mock_data.py
    python3 src/ranking.py
fi

echo "🚀 Starting API server on http://localhost:8001"
python3 src/api.py &
API_PID=$!

echo "✅ AgentRanker started!"
echo "📊 API: http://localhost:8001"
echo "🌐 Frontend: file://$(pwd)/frontend/index.html"
echo ""
echo "Press Ctrl+C to stop"

# Wait for interrupt
trap "kill $API_PID; echo '👋 Goodbye'; exit 0" INT
wait
