import json
import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
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


# Milvus Configuration
MILVUS_HOST = os.environ.get("MILVUS_HOST", "milvus")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")
MILVUS_URL = os.environ.get("MILVUS_URL", f"http://{MILVUS_HOST}:{MILVUS_PORT}")
MILVUS_TOKEN = os.environ.get("MILVUS_TOKEN", "")  # Empty for local setup, required for Zilliz Cloud
MILVUS_COLLECTION_NAME = os.environ.get("MILVUS_COLLECTION_NAME", "memories")
MILVUS_DB_NAME = os.environ.get("MILVUS_DB_NAME", "")
MILVUS_EMBEDDING_DIMS = int(os.environ.get("MILVUS_EMBEDDING_DIMS", "1536"))  # text-embedding-3-small dimensions
MILVUS_METRIC_TYPE = os.environ.get("MILVUS_METRIC_TYPE", "COSINE")  # COSINE, L2, or IP

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
        "provider": "milvus",
        "config": {
            "url": MILVUS_URL,
            "token": MILVUS_TOKEN,
            "collection_name": MILVUS_COLLECTION_NAME,
            "embedding_model_dims": MILVUS_EMBEDDING_DIMS,
            "metric_type": MILVUS_METRIC_TYPE,
            "db_name": MILVUS_DB_NAME,
        },
    },
    "llm": {"provider": "openai", "config": {"api_key": OPENAI_API_KEY, "temperature": 0.2, "model": "gpt-4.1-nano-2025-04-14"}},
    "embedder": {"provider": "openai", "config": {"api_key": OPENAI_API_KEY, "model": "text-embedding-3-small"}},
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
    root_path="/mem",
)

# Middleware to strip /mem prefix from request paths
class PathPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Strip /mem prefix if present
        original_path = request.url.path
        original_method = request.method
        
        if original_path.startswith("/mem/"):
            # Rewrite the path by removing /mem prefix
            new_path = original_path[4:]  # Remove "/mem" (4 characters)
        elif original_path == "/mem":
            new_path = "/"
        else:
            new_path = original_path
        
        # Log path rewriting for debugging
        if new_path != original_path:
            logging.info(f"PathPrefixMiddleware: Rewriting {original_method} {original_path} -> {new_path}")
            # Create a new request with modified path
            scope = dict(request.scope)
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode()
            # Create new request with modified scope
            request = Request(scope, request.receive)
        else:
            logging.info(f"PathPrefixMiddleware: No rewrite needed for {original_method} {original_path}")
        
        return await call_next(request)


# Add middleware to log all requests with client IP
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get client IP address
        client_ip = request.client.host if request.client else "unknown"
        # Check for forwarded IP (in case behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        real_ip = request.headers.get("X-Real-IP")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip
        
        # Log request details
        logging.info(
            f"Request: {request.method} {request.url.path} | "
            f"Client IP: {client_ip} | "
            f"User-Agent: {request.headers.get('user-agent', 'unknown')} | "
            f"Origin: {request.headers.get('origin', 'unknown')}"
        )
        
        try:
            response = await call_next(request)
            
            # Log response details including headers
            response_headers = dict(response.headers) if hasattr(response, 'headers') else {}
            content_type = response_headers.get('content-type', 'unknown')
            content_length = response_headers.get('content-length', 'unknown')
            
            logging.info(
                f"Response: {request.method} {request.url.path} | "
                f"Status: {response.status_code} | "
                f"Client IP: {client_ip} | "
                f"Content-Type: {content_type} | "
                f"Content-Length: {content_length}"
            )
            
            # If status is not 200, log warning
            if response.status_code != 200:
                logging.warning(
                    f"Non-200 response detected: {response.status_code} for {request.method} {request.url.path} | "
                    f"Client IP: {client_ip}"
                )
            
            return response
        except Exception as e:
            logging.error(
                f"Error processing request: {request.method} {request.url.path} | "
                f"Client IP: {client_ip} | "
                f"Error: {str(e)}"
            )
            raise

# Needed to respect X-Forwarded headers from AWS ALB
# app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Add path prefix middleware first (strips /mem prefix)
# Note: Middleware executes in reverse order, so this will run first
app.add_middleware(PathPrefixMiddleware)
# Add logging middleware
app.add_middleware(LoggingMiddleware)

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


@app.post("/configure", summary="Configure Mem0")
def set_config(config: Dict[str, Any]):
    """Set memory configuration."""
    global MEMORY_INSTANCE
    MEMORY_INSTANCE = Memory.from_config(config)
    return {"message": "Configuration set successfully"}


@app.post("/memories", summary="Create memories")
def add_memory(request: Request, memory_create: MemoryCreate):
    """Store new memories."""
    # Get client IP for detailed logging
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    real_ip = request.headers.get("X-Real-IP")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif real_ip:
        client_ip = real_ip
    
    # Log request details for debugging
    logging.info(f"Request from IP: {client_ip}")
    logging.info(f"Request headers: {dict(request.headers)}")
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
        
        # Create JSONResponse with explicit status code
        json_response = JSONResponse(content=response, status_code=200)
        
        # Log response details for debugging
        response_str = json.dumps(response) if isinstance(response, dict) else str(response)
        response_size = len(response_str.encode('utf-8'))
        logging.info(
            f"Returning response: Status=200, Size={response_size} bytes, "
            f"Content-Type=application/json, Results={results_count}"
        )
        
        return json_response
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
    """Simple health check endpoint to test connectivity."""
    return JSONResponse(
        content={"status": "healthy", "message": "API is running"},
        status_code=200
    )


@app.get("/", summary="Redirect to the OpenAPI documentation", include_in_schema=False)
def home():
    """Redirect to the OpenAPI documentation."""
    return RedirectResponse(url="/docs")
