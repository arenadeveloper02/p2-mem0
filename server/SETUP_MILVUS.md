# Setting Up Mem0 REST API Server with Milvus

This guide will help you set up and run the Mem0 REST API server using Milvus as the vector database.

## Prerequisites

1. **Docker and Docker Compose** - Required for running the services
2. **OpenAI API Key** - Required for LLM and embeddings

## Step-by-Step Setup

### Step 1: Navigate to the Server Directory

```bash
cd /Users/hanuvendra.pandey/Projects/mem0/server
```

### Step 2: Create Environment File

Copy the example environment file and edit it with your values:

```bash
cp .env.example .env
```

Edit `.env` and set your OpenAI API key:

```bash
# Required - Get your key from https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-your-actual-openai-api-key-here
```

The other Milvus and Neo4j settings have sensible defaults for local Docker setup, but you can customize them if needed.

### Step 3: Build and Start Services

Start all services (Milvus, Neo4j, and the Mem0 API server):

```bash
docker compose up --build
```

This will:
- Build the Mem0 API server Docker image
- Start Milvus (with etcd and MinIO dependencies)
- Start Neo4j (for graph memory features)
- Start the Mem0 REST API server

**First-time startup may take 2-3 minutes** as Docker needs to:
- Pull images for Milvus, etcd, MinIO, and Neo4j
- Initialize the databases
- Build the Mem0 server container

### Step 4: Verify Services Are Running

Once started, you should see output indicating all services are healthy. The API will be available at:

- **Mem0 REST API**: http://localhost:8888
- **API Documentation**: http://localhost:8888/docs
- **Milvus**: http://localhost:19530 (gRPC) and http://localhost:9091 (HTTP/health)
- **Neo4j Browser**: http://localhost:8474
- **Neo4j Bolt**: localhost:8687

### Step 5: Test the API

Open your browser or use curl to test:

```bash
# View API documentation
open http://localhost:8888/docs

# Or test with curl
curl http://localhost:8888/docs
```

## Configuration Options

### Milvus Configuration

The server supports both local Milvus and Zilliz Cloud:

**Local Milvus (default):**
```env
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_URL=http://milvus:19530
MILVUS_TOKEN=
```

**Zilliz Cloud:**
```env
MILVUS_URL=https://your-cluster-endpoint.zillizcloud.com
MILVUS_TOKEN=your-zilliz-api-token
MILVUS_DB_NAME=your-database-name
```

### Embedding Dimensions

The default is 1536 dimensions (for `text-embedding-3-small`). If you use a different embedding model, update:

```env
MILVUS_EMBEDDING_DIMS=1536  # or 3072 for text-embedding-3-large
```

### Metric Type

Choose the similarity metric:
- `COSINE` - Best for semantic similarity (default)
- `L2` - Euclidean distance
- `IP` - Inner product

```env
MILVUS_METRIC_TYPE=COSINE
```

## API Usage Examples

### Create a Memory

```bash
curl -X POST "http://localhost:8888/memories" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I love Ethiopian coffee"},
      {"role": "assistant", "content": "That sounds wonderful!"}
    ],
    "user_id": "alice"
  }'
```

### Search Memories

```bash
curl -X POST "http://localhost:8888/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What do I like?",
    "user_id": "alice"
  }'
```

### Get All Memories

```bash
curl "http://localhost:8888/memories?user_id=alice"
```

## Stopping the Services

Press `Ctrl+C` in the terminal where `docker compose up` is running, or run:

```bash
docker compose down
```

To remove all data volumes (⚠️ this deletes all memories):

```bash
docker compose down -v
```

## Troubleshooting

### Milvus Health Check Failing

If Milvus takes longer to start, you can increase the health check timeout or wait a bit longer. Milvus standalone typically takes 30-60 seconds to initialize.

### Port Conflicts

If ports 8888, 19530, 9091, 8474, or 8687 are already in use, modify the port mappings in `docker-compose.yaml` or stop the conflicting services.

### Memory Issues

Milvus requires adequate memory. Ensure Docker has at least 4GB allocated. For production, consider 8GB+.

### Check Logs

View logs for specific services:

```bash
docker compose logs mem0    # API server logs
docker compose logs milvus   # Milvus logs
docker compose logs neo4j    # Neo4j logs
```

## Next Steps

- Explore the API documentation at http://localhost:8888/docs
- Integrate the REST API into your applications
- Consider using the SDKs (Python/TypeScript) for easier integration
- Configure additional features like reranking or custom LLMs

