# Running Mem0 REST API Server Locally (Without Docker)

This guide will help you run the Mem0 REST API server locally without Docker, using Milvus as the vector database.

## Prerequisites

1. **Python 3.9+** - Required
2. **OpenAI API Key** - Required for LLM and embeddings
3. **Milvus** - You have several options (see below)
4. **Neo4j** (Optional) - For graph memory features

## Option 1: Quick Setup with Milvus Lite (Easiest)

Milvus Lite is an embedded version of Milvus that runs entirely in Python - no separate server needed.

### Step 1: Navigate to Server Directory

```bash
cd /Users/hanuvendra.pandey/Projects/mem0/server
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Install basic requirements
pip install -r requirements.txt

# Install mem0 with vector_stores and graph support
# From the project root directory
cd ..
pip install -e ".[vector_stores,graph]"

# Go back to server directory
cd server
```

### Step 4: Install Milvus Lite

```bash
pip install milvus
```

**Note:** Milvus Lite uses SQLite as its backend and doesn't require separate services.

### Step 5: Set Up Environment Variables

Create a `.env` file:

```bash
cat > .env << 'EOF'
# OpenAI API Key (Required)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Milvus Lite Configuration
# For Milvus Lite, use a local path - it will create an embedded database
MILVUS_URL=http://localhost:19530
MILVUS_TOKEN=
MILVUS_COLLECTION_NAME=memories
MILVUS_DB_NAME=
MILVUS_EMBEDDING_DIMS=1536
MILVUS_METRIC_TYPE=COSINE

# Neo4j Configuration (Optional - leave empty to disable graph store)
NEO4J_URI=
NEO4J_USERNAME=
NEO4J_PASSWORD=

# History Database Path
HISTORY_DB_PATH=./history/history.db
EOF
```

**Important:** Edit `.env` and add your actual OpenAI API key.

### Step 6: Modify server/main.py for Milvus Lite

You'll need to use Milvus Lite's Python API. Create a wrapper or modify the config to use `milvus` package directly. However, the easiest approach is to use a remote Milvus instance or use Milvus standalone (see Option 2).

**Note:** The current `main.py` expects a Milvus server URL. For Milvus Lite, you'd need to modify the connection logic.

## Option 2: Using Milvus Standalone (Recommended for Local)

Run only Milvus in Docker (lightweight), but run the Mem0 server locally.

### Step 1-3: Same as Option 1 (Python setup)

### Step 4: Run Milvus in Docker (Separate Terminal)

```bash
# Start Milvus with its dependencies
docker run -d \
  --name milvus-etcd \
  -p 2379:2379 \
  -p 2380:2380 \
  quay.io/coreos/etcd:v3.5.5 \
  etcd \
    -advertise-client-urls=http://127.0.0.1:2379 \
    -initial-advertise-peer-urls=http://127.0.0.1:2380 \
    -listen-client-urls=http://0.0.0.0:2379 \
    -listen-peer-urls=http://0.0.0.0:2380 \
    -initial-cluster=default=http://127.0.0.1:2380

docker run -d \
  --name milvus-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ACCESS_KEY=minioadmin \
  -e MINIO_SECRET_KEY=minioadmin \
  minio/minio:RELEASE.2023-10-25T06-33-25Z \
  server /minio_data --console-address ":9001"

docker run -d \
  --name milvus \
  -p 19530:19530 \
  -p 9091:9091 \
  -e ETCD_ENDPOINTS=localhost:2379 \
  -e MINIO_ADDRESS=localhost:9000 \
  milvusdb/milvus:v2.4.7 \
  milvus run standalone
```

Wait ~30-60 seconds for Milvus to initialize, then verify:

```bash
curl http://localhost:9091/healthz
```

### Step 5: Set Up Environment Variables

Create `.env` file:

```bash
cat > .env << 'EOF'
# OpenAI API Key (Required)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Milvus Configuration (Local Docker instance)
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_URL=http://localhost:19530
MILVUS_TOKEN=
MILVUS_COLLECTION_NAME=memories
MILVUS_DB_NAME=
MILVUS_EMBEDDING_DIMS=1536
MILVUS_METRIC_TYPE=COSINE

# Neo4j Configuration (Optional - leave empty to disable)
NEO4J_URI=
NEO4J_USERNAME=
NEO4J_PASSWORD=

# History Database Path
HISTORY_DB_PATH=./history/history.db
EOF
```

Edit `.env` and add your OpenAI API key.

### Step 6: Run Neo4j Locally (Optional)

If you want graph memory features, install Neo4j Desktop or run Neo4j:

**Option A: Neo4j Desktop (GUI)**
- Download from https://neo4j.com/download/
- Create a local database
- Note the connection URI (usually `bolt://localhost:7687`)

**Option B: Neo4j Community Edition via Homebrew (macOS)**

```bash
brew install neo4j
brew services start neo4j
```

**Option C: Run Neo4j in Docker (if you're okay with minimal Docker usage)**

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/mem0graph \
  neo4j:5.26.4
```

Then update `.env`:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=mem0graph
```

### Step 7: Run the API Server

```bash
# Make sure you're in the server directory
cd /Users/hanuvendra.pandey/Projects/mem0/server

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8888 --reload
```

The API will be available at:
- **API Server**: http://localhost:8888
- **API Documentation**: http://localhost:8888/docs

## Option 3: Using Zilliz Cloud (Easiest - No Local Setup)

Use a managed Milvus instance from Zilliz Cloud.

### Step 1-3: Same as Option 1 (Python setup)

### Step 4: Sign Up for Zilliz Cloud

1. Go to https://cloud.zilliz.com/
2. Sign up and create a cluster
3. Get your cluster endpoint and API token

### Step 5: Set Up Environment Variables

```bash
cat > .env << 'EOF'
# OpenAI API Key (Required)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Zilliz Cloud Configuration
MILVUS_URL=https://your-cluster-endpoint.zillizcloud.com
MILVUS_TOKEN=your-zilliz-api-token
MILVUS_DB_NAME=your-database-name
MILVUS_COLLECTION_NAME=memories
MILVUS_EMBEDDING_DIMS=1536
MILVUS_METRIC_TYPE=COSINE

# Neo4j (Optional)
NEO4J_URI=
NEO4J_USERNAME=
NEO4J_PASSWORD=

# History Database Path
HISTORY_DB_PATH=./history/history.db
EOF
```

### Step 6: Run the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8888 --reload
```

## Verifying Installation

Test that everything works:

```bash
# Check API docs
curl http://localhost:8888/docs

# Create a test memory
curl -X POST "http://localhost:8888/memories" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I love Ethiopian coffee"},
      {"role": "assistant", "content": "That sounds wonderful!"}
    ],
    "user_id": "test_user"
  }'
```

## Troubleshooting

### Port Already in Use

If port 8888 is busy, use a different port:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Milvus Connection Errors

- **Check Milvus is running**: `curl http://localhost:9091/healthz`
- **Verify URL in .env**: Should be `http://localhost:19530` for local
- **Check firewall**: Ensure ports 19530 and 9091 are accessible

### Missing Dependencies

If you get import errors:

```bash
# Reinstall with all extras
cd /Users/hanuvendra.pandey/Projects/mem0
pip install -e ".[vector_stores,graph,extras]"
```

### Neo4j Connection Issues

If you're not using Neo4j, make sure to leave the Neo4j config empty in `.env`:

```env
NEO4J_URI=
```

Or modify `main.py` to disable graph store when empty.

### History Database Path

Create the history directory if it doesn't exist:

```bash
mkdir -p ./history
```

## Stopping Services

### Milvus (Docker containers from Option 2)

```bash
docker stop milvus milvus-etcd milvus-minio
docker rm milvus milvus-etcd milvus-minio
```

### Neo4j (if installed via Homebrew)

```bash
brew services stop neo4j
```

### API Server

Press `Ctrl+C` in the terminal running `uvicorn`.

## Recommended Setup for Local Development

**Best balance of ease and control:**

1. Use **Option 2** (Milvus in Docker) - minimal Docker usage, just for the database
2. Run **Neo4j Desktop** or skip it if you don't need graph features
3. Run the **Mem0 server locally** in Python
4. Use **Zilliz Cloud** if you prefer no local database setup

This gives you:
- Full control over the API server code (hot reload works)
- Easy debugging with Python debugger
- No need to rebuild Docker images for code changes
- Clean separation between services

