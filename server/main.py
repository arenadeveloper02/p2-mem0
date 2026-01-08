import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mem0 import Memory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Ensures logs go to stdout (captured by systemd)
    ]
)

# Load environment variables
load_dotenv()


# Postgres Configuration (pgvector)
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
POSTGRES_DBNAME = os.environ.get("POSTGRES_DBNAME", "postgres")
POSTGRES_COLLECTION_NAME = os.environ.get("POSTGRES_COLLECTION_NAME", "memories")
POSTGRES_EMBEDDING_DIMS = int(os.environ.get("POSTGRES_EMBEDDING_DIMS", "1536"))  # text-embedding-3-small dimensions
POSTGRES_SSLMODE = os.environ.get("POSTGRES_SSLMODE", None)  # Optional: 'require', 'prefer', 'disable', etc.
POSTGRES_CONNECTION_STRING = os.environ.get("POSTGRES_CONNECTION_STRING", None)  # Optional: full connection string

# Neo4j Configuration (for graph store - optional)
# Check if Neo4j should be enabled (via environment variable)
ENABLE_NEO4J = os.environ.get("ENABLE_NEO4J", "false").lower() == "true"
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "mem0graph")

# Test Neo4j connection if enabled (optional, won't fail if unavailable)
NEO4J_AVAILABLE = False
if ENABLE_NEO4J:
    try:
        import socket
        # Parse URI to get host and port
        # Handle bolt://, neo4j://, neo4j+s://, bolt+s://
        uri_clean = NEO4J_URI
        for prefix in ["bolt://", "neo4j://", "bolt+s://", "neo4j+s://"]:
            if uri_clean.startswith(prefix):
                uri_clean = uri_clean.replace(prefix, "")
                break
        
        uri_part = uri_clean.split("/")[0]
        if ":" in uri_part:
            host, port = uri_part.split(":")
        else:
            host, port = uri_part, "7687"
        port = int(port)
        
        # Test if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        NEO4J_AVAILABLE = result == 0
    except Exception as e:
        # If connection test fails, assume unavailable (connection will be tested by Neo4j driver)
        # For cloud Neo4j (neo4j+s://), socket test might fail but connection might still work
        # So we'll let the Neo4j driver try the connection
        logging.debug(f"Neo4j socket test failed: {e}. Will let Neo4j driver handle connection.")
        # For cloud instances, assume available if URI is set (driver will verify)
        if "databases.neo4j.io" in NEO4J_URI or "neo4j+s://" in NEO4J_URI or "neo4j://" in NEO4J_URI:
            NEO4J_AVAILABLE = True  # Assume available for cloud, driver will verify
        else:
            NEO4J_AVAILABLE = False

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# History Database Path - Ensure directory exists and resolve to absolute path
_history_db_path_env = os.environ.get("HISTORY_DB_PATH", "./history/history.db")
if _history_db_path_env != ":memory:":
    # Resolve to absolute path
    _history_db_path_abs = os.path.abspath(_history_db_path_env)
    # Get directory path
    _history_db_dir = os.path.dirname(_history_db_path_abs)
    # Create directory if it doesn't exist
    os.makedirs(_history_db_dir, exist_ok=True)
    HISTORY_DB_PATH = _history_db_path_abs
else:
    HISTORY_DB_PATH = ":memory:"

DEFAULT_CONFIG = {
    "version": "v1.1",
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "host": POSTGRES_HOST,
            "port": POSTGRES_PORT,
            "user": POSTGRES_USER,
            "password": POSTGRES_PASSWORD,
            "dbname": POSTGRES_DBNAME,
            "collection_name": POSTGRES_COLLECTION_NAME,
            "embedding_model_dims": POSTGRES_EMBEDDING_DIMS,
            "hnsw": True,  # Use HNSW indexing for faster search
            "diskann": False,  # Optional: requires pgvectorscale extension
            "sslmode": POSTGRES_SSLMODE,  # Optional SSL mode
            # Alternative: use connection_string instead of individual params
            # "connection_string": POSTGRES_CONNECTION_STRING,
        },
    },
    "llm": {"provider": "openai", "config": {"api_key": OPENAI_API_KEY, "temperature": 0.2, "model": "gpt-4.1-nano-2025-04-14"}},
    "embedder": {
        "provider": "openai",
        "config": {
            "api_key": OPENAI_API_KEY,
            "model": "text-embedding-3-small",
            "max_input_tokens": 8191,
            "chunk_size_tokens": 1024,
            "chunk_overlap_tokens": 200,
            "min_chunk_size_chars": 100,
            "enable_chunking": True,
        },
    },
    "history_db_path": HISTORY_DB_PATH,
}

# Only add graph_store if Neo4j is enabled and available
if ENABLE_NEO4J and NEO4J_AVAILABLE:
    DEFAULT_CONFIG["graph_store"] = {
        "provider": "neo4j",
        "config": {"url": NEO4J_URI, "username": NEO4J_USERNAME, "password": NEO4J_PASSWORD},
    }
elif ENABLE_NEO4J and not NEO4J_AVAILABLE:
    # Don't add graph_store if Neo4j is enabled but unavailable - this will cause errors
    # Instead, log a warning and skip graph_store entirely
    logging.warning(
        f"Neo4j is enabled (ENABLE_NEO4J=true) but not available at {NEO4J_URI}. "
        "Graph memory features will be disabled. "
        "To enable Neo4j, start it and verify the connection. "
        "To disable Neo4j features, set ENABLE_NEO4J=false or leave it unset."
    )
# If ENABLE_NEO4J is false/unset, graph_store is simply not included (default behavior)


MEMORY_INSTANCE = Memory.from_config(DEFAULT_CONFIG)

app = FastAPI(
    title="Mem0 REST APIs",
    description="A REST API for managing and searching memories for your AI Agents and Apps.",
    version="1.0.0",
)

# Add CORS middleware to handle cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str = Field(..., description="Role of the message (user or assistant).")
    content: str = Field(..., description="Message content.")


class MemoryCreate(BaseModel):
    messages: List[Message] = Field(..., description="List of messages to store.")
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    infer: Optional[bool] = True


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query.")
    user_id: Optional[str] = None
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    limit: Optional[int] = Field(default=100, description="Maximum number of results to return. Defaults to 100.")


@app.post("/configure", summary="Configure Mem0")
def set_config(config: Dict[str, Any]):
    """Set memory configuration."""
    global MEMORY_INSTANCE
    MEMORY_INSTANCE = Memory.from_config(config)
    return {"message": "Configuration set successfully"}


@app.post("/memories", summary="Create memories")
def add_memory(request: Request, memory_create: MemoryCreate):
    """Store new memories."""
    # Log request details for debugging
    logging.info(f"Request headers: {request}")
    logging.info(f"Received add_memory request: user_id={memory_create.user_id}, agent_id={memory_create.agent_id}, run_id={memory_create.run_id}, messages_count={len(memory_create.messages) if memory_create.messages else 0}, infer={memory_create.infer} (type: {type(memory_create.infer)})")
    
    if not any([memory_create.user_id, memory_create.agent_id, memory_create.run_id]):
        raise HTTPException(
            status_code=400, 
            detail="At least one identifier (user_id, agent_id, run_id) is required."
        )

    if not memory_create.messages or len(memory_create.messages) == 0:
        raise HTTPException(
            status_code=400,
            detail="At least one message is required in the messages array."
        )

    params = {k: v for k, v in memory_create.model_dump().items() if v is not None and k != "messages"}
    # Explicitly include infer even if it's False (since False is falsy but not None)
    if "infer" in memory_create.model_dump():
        params["infer"] = memory_create.infer
    logging.info(f"Calling MEMORY_INSTANCE.add with params: {params}, messages_count: {len(memory_create.messages)}")
    logging.info(f"Infer value in params: {params.get('infer')} (type: {type(params.get('infer'))})")
    try:
        response = MEMORY_INSTANCE.add(messages=[m.model_dump() for m in memory_create.messages], **params)
        results_count = len(response.get('results', [])) if isinstance(response, dict) else 0
        logging.info(f"Memory add completed. Stored {results_count} memories. Response keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")
        return JSONResponse(content=response)
    except Exception as e:
        logging.exception("Error in add_memory:")  # This will log the full traceback
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories", summary="Get memories")
def get_all_memories(
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    """Retrieve stored memories."""
    if not any([user_id, run_id, agent_id]):
        raise HTTPException(status_code=400, detail="At least one identifier is required.")
    try:
        params = {
            k: v for k, v in {"user_id": user_id, "run_id": run_id, "agent_id": agent_id}.items() if v is not None
        }
        logging.info(f"Retrieving memories with filters: {params}")
        result = MEMORY_INSTANCE.get_all(**params)
        logging.info(f"Retrieved {len(result.get('results', []))} memories")
        return result
    except Exception as e:
        logging.exception("Error in get_all_memories:")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/original-prompt", summary="Get original prompt data instead of chunked data")
def get_original_prompt_memories(
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    """
    Retrieve memories with original prompt data instead of chunked data.
    For chunked memories, returns the full original content from memory_chunk_mapping table.
    For non-chunked memories, returns them as-is.
    """
    if not any([user_id, run_id, agent_id]):
        raise HTTPException(status_code=400, detail="At least one identifier is required.")
    try:
        params = {
            k: v for k, v in {"user_id": user_id, "run_id": run_id, "agent_id": agent_id}.items() if v is not None
        }
        logging.info(f"Retrieving original prompt memories with filters: {params}")
        
        # Get all memories (including chunks)
        result = MEMORY_INSTANCE.get_all(**params)
        memories = result.get("results", [])
        
        # Process memories to replace chunks with original content
        processed_memories = []
        seen_original_message_ids = set()
        
        for mem in memories:
            metadata = mem.get("metadata", {})
            is_chunk = metadata.get("is_chunk", False)
            original_message_id = metadata.get("original_message_id")
            original_content_memory_id = metadata.get("original_content_memory_id")
            
            if is_chunk and original_message_id and original_content_memory_id:
                # Skip if we've already processed this original message
                if original_message_id in seen_original_message_ids:
                    continue
                
                # Mark as seen
                seen_original_message_ids.add(original_message_id)
                
                # Fetch original content from memory_chunk_mapping table
                try:
                    mapping_data = MEMORY_INSTANCE.db.get_chunk_mapping(original_content_memory_id)
                    if mapping_data:
                        # Create a new memory entry with original content
                        original_memory = {
                            "id": original_message_id,  # Use original_message_id as the ID
                            "memory": mapping_data["original_content"],
                            "hash": None,  # Original content hash (could be computed if needed)
                            "created_at": mapping_data.get("created_at"),
                            "updated_at": None,
                            "user_id": mem.get("user_id"),
                            "agent_id": mem.get("agent_id"),
                            "run_id": mem.get("run_id"),
                            "actor_id": mem.get("actor_id"),
                            "role": mem.get("role"),
                            "metadata": {
                                "is_original_content": True,
                                "original_content_memory_id": original_content_memory_id,
                                "original_token_count": mapping_data.get("original_token_count"),
                                "total_chunks": mapping_data.get("total_chunks"),
                            }
                        }
                        processed_memories.append(original_memory)
                    else:
                        # If mapping not found, log warning and skip
                        logging.warning(f"Original content mapping not found for ID: {original_content_memory_id}")
                except Exception as e:
                    logging.warning(f"Error fetching original content for mapping ID {original_content_memory_id}: {e}")
                    # Continue with next memory
                    continue
            else:
                # Non-chunked memory, add as-is
                processed_memories.append(mem)
        
        logging.info(f"Retrieved {len(processed_memories)} original prompt memories (from {len(memories)} total memories)")
        
        # Return in same format as get_all
        response = {"results": processed_memories}
        if "relations" in result:
            response["relations"] = result["relations"]
        
        return response
    except Exception as e:
        logging.exception("Error in get_original_prompt_memories:")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{memory_id}", summary="Get a memory")
def get_memory(memory_id: str):
    """Retrieve a specific memory by ID."""
    try:
        return MEMORY_INSTANCE.get(memory_id)
    except Exception as e:
        logging.exception("Error in get_memory:")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", summary="Search memories")
def search_memories(search_req: SearchRequest):
    """Search for memories based on a query."""
    try:
        params = {k: v for k, v in search_req.model_dump().items() if v is not None and k != "query"}
        return MEMORY_INSTANCE.search(query=search_req.query, **params)
    except Exception as e:
        logging.exception("Error in search_memories:")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/memories/{memory_id}", summary="Update a memory")
def update_memory(memory_id: str, updated_memory: Dict[str, Any]):
    """Update an existing memory with new content.
    
    Args:
        memory_id (str): ID of the memory to update
        updated_memory (str): New content to update the memory with
        
    Returns:
        dict: Success message indicating the memory was updated
    """
    try:
        return MEMORY_INSTANCE.update(memory_id=memory_id, data=updated_memory)
    except Exception as e:
        logging.exception("Error in update_memory:")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{memory_id}/history", summary="Get memory history")
def memory_history(memory_id: str):
    """Retrieve memory history."""
    try:
        return MEMORY_INSTANCE.history(memory_id=memory_id)
    except Exception as e:
        logging.exception("Error in memory_history:")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memories/{memory_id}", summary="Delete a memory")
def delete_memory(memory_id: str):
    """Delete a specific memory by ID."""
    try:
        MEMORY_INSTANCE.delete(memory_id=memory_id)
        return {"message": "Memory deleted successfully"}
    except Exception as e:
        logging.exception("Error in delete_memory:")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memories", summary="Delete all memories")
def delete_all_memories(
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    """Delete all memories for a given identifier."""
    if not any([user_id, run_id, agent_id]):
        raise HTTPException(status_code=400, detail="At least one identifier is required.")
    try:
        params = {
            k: v for k, v in {"user_id": user_id, "run_id": run_id, "agent_id": agent_id}.items() if v is not None
        }
        MEMORY_INSTANCE.delete_all(**params)
        return {"message": "All relevant memories deleted"}
    except Exception as e:
        logging.exception("Error in delete_all_memories:")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset", summary="Reset all memories")
def reset_memory():
    """Completely reset stored memories."""
    try:
        MEMORY_INSTANCE.reset()
        return {"message": "All memories reset"}
    except Exception as e:
        logging.exception("Error in reset_memory:")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", summary="Health check endpoint")
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    try:
        # Basic health check - can be extended to check database connections, etc.
        return {"status": "healthy", "service": "mem0-api"}
    except Exception as e:
        logging.exception("Error in health_check:")
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/", summary="Redirect to the OpenAPI documentation", include_in_schema=False)
def home():
    """Redirect to the OpenAPI documentation."""
    return RedirectResponse(url="/docs")
