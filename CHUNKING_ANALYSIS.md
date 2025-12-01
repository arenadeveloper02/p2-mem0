# Text-Based Chunking Analysis: Implementation & Search Behavior

## Overview
This document analyzes how text-based chunking will work with the current search implementation, and whether any changes are needed to the Search API.

---

## 1. Current Flow (Without Chunking)

### Storage Flow (`infer=false`):
```
User sends message → API receives → _add_to_vector_store() 
→ For each message:
   - Extract content
   - Generate embedding (1536 dims)
   - Store as single vector with metadata
   - Return memory_id
```

**Example:**
```
Message: "This is a very long message about machine learning and deep learning..."
→ Stored as: 1 vector with full text
```

### Search Flow:
```
User query → Embed query → Vector similarity search → Return top-K results
```

**Example:**
```
Query: "machine learning"
→ Finds the full message (if it contains "machine learning")
→ Returns: {id: "mem_123", memory: "This is a very long message about machine learning...", score: 0.85}
```

---

## 2. Proposed Chunking Flow

### Storage Flow (With Chunking):
```
User sends message → API receives → Check if content length > threshold
→ If YES:
   - Split content into chunks (with overlap)
   - For each chunk:
     * Generate embedding
     * Store as separate vector
     * Add chunk metadata (original_message_id, chunk_index, total_chunks, is_chunk: true)
   - Return multiple memory_ids
→ If NO:
   - Store as normal (single vector)
```

**Example:**
```
Original Message: "This is a very long message about machine learning and deep learning. Machine learning is..."
(Length: 5000 chars, threshold: 2000 chars)

→ Chunk 1: "This is a very long message about machine learning and deep learning. Machine learning is..."
   - Stored as: vector_1
   - Metadata: {original_message_id: "msg_123", chunk_index: 0, total_chunks: 3, is_chunk: true}

→ Chunk 2: "...deep learning. Machine learning is a subset of AI. Deep learning uses neural networks..."
   - Stored as: vector_2
   - Metadata: {original_message_id: "msg_123", chunk_index: 1, total_chunks: 3, is_chunk: true}

→ Chunk 3: "...neural networks with multiple layers. These networks can learn complex patterns..."
   - Stored as: vector_3
   - Metadata: {original_message_id: "msg_123", chunk_index: 2, total_chunks: 3, is_chunk: true}
```

---

## 3. How Search Will Work With Chunked Data

### Scenario 1: Query Matches One Chunk

**Query:** "machine learning"

**Search Process:**
1. Query is embedded → vector_search
2. Vector similarity search finds:
   - Chunk 1 (score: 0.92) - contains "machine learning"
   - Chunk 2 (score: 0.88) - contains "machine learning"
   - Other unrelated memories...

**Current Search API Response:**
```json
{
  "results": [
    {
      "id": "mem_chunk_1",
      "memory": "This is a very long message about machine learning and deep learning...",
      "score": 0.92,
      "metadata": {
        "original_message_id": "msg_123",
        "chunk_index": 0,
        "total_chunks": 3,
        "is_chunk": true,
        "role": "user"
      }
    },
    {
      "id": "mem_chunk_2",
      "memory": "...deep learning. Machine learning is a subset of AI...",
      "score": 0.88,
      "metadata": {
        "original_message_id": "msg_123",
        "chunk_index": 1,
        "total_chunks": 3,
        "is_chunk": true,
        "role": "user"
      }
    }
  ]
}
```

**✅ Search API works WITHOUT changes** - It will return chunked results as separate memory items.

---

### Scenario 2: Query Matches Multiple Chunks from Same Message

**Query:** "neural networks"

**Search Process:**
1. Query is embedded → vector_search
2. Finds:
   - Chunk 2 (score: 0.91) - contains "neural networks"
   - Chunk 3 (score: 0.89) - contains "neural networks"
   - Both from same original_message_id: "msg_123"

**Current Search API Response:**
```json
{
  "results": [
    {
      "id": "mem_chunk_2",
      "memory": "...Deep learning uses neural networks...",
      "score": 0.91,
      "metadata": {
        "original_message_id": "msg_123",
        "chunk_index": 1,
        "total_chunks": 3,
        "is_chunk": true
      }
    },
    {
      "id": "mem_chunk_3",
      "memory": "...neural networks with multiple layers...",
      "score": 0.89,
      "metadata": {
        "original_message_id": "msg_123",
        "chunk_index": 2,
        "total_chunks": 3,
        "is_chunk": true
      }
    }
  ]
}
```

**✅ Search API works** - Returns both chunks. Client can:
- Use both chunks (if they want full context)
- Group by `original_message_id` to reconstruct
- Use highest scoring chunk only

---

### Scenario 3: Query Matches Non-Chunked Message

**Query:** "user preferences"

**Search Process:**
1. Query is embedded → vector_search
2. Finds:
   - Normal memory (not chunked) - score: 0.87
   - Chunk 1 from different message - score: 0.75

**Current Search API Response:**
```json
{
  "results": [
    {
      "id": "mem_normal_456",
      "memory": "User prefers dark mode and notifications",
      "score": 0.87,
      "metadata": {
        "role": "user"
        // No chunk metadata = not chunked
      }
    },
    {
      "id": "mem_chunk_5",
      "memory": "...user preferences for UI design...",
      "score": 0.75,
      "metadata": {
        "original_message_id": "msg_789",
        "chunk_index": 0,
        "total_chunks": 2,
        "is_chunk": true
      }
    }
  ]
}
```

**✅ Search API works** - Handles both chunked and non-chunked memories seamlessly.

---

## 4. Do We Need to Change the Search API?

### Answer: **NO, but we have OPTIONAL enhancements**

### Current Search API Behavior:
- ✅ Returns all matching vectors (chunked or not)
- ✅ Includes all metadata in response
- ✅ Ranks by similarity score
- ✅ Supports filters (user_id, agent_id, run_id, metadata)

### Why It Works:
1. **Vector search is chunk-agnostic**: It just finds similar vectors, doesn't care if they're chunks
2. **Metadata is preserved**: Chunk metadata (`original_message_id`, `chunk_index`, etc.) is stored and returned
3. **Client can handle grouping**: Client can group chunks by `original_message_id` if needed

---

## 5. Optional Enhancements (Not Required)

### Option A: Group Chunks in Search Response (Optional)

**Enhancement:** Automatically group chunks from the same original message in search results.

**Modified Response:**
```json
{
  "results": [
    {
      "id": "mem_chunk_1",
      "memory": "This is a very long message about machine learning...",
      "score": 0.92,
      "metadata": {...},
      "related_chunks": [
        {
          "id": "mem_chunk_2",
          "memory": "...deep learning. Machine learning is...",
          "score": 0.88,
          "chunk_index": 1
        }
      ]
    }
  ]
}
```

**Pros:**
- Easier for client to reconstruct full message
- Reduces duplicate results from same message

**Cons:**
- More complex implementation
- May hide relevant chunks if grouping logic is wrong
- Client can already do this with metadata

**Recommendation:** ❌ **Not needed** - Client can group using metadata

---

### Option B: Reconstruct Full Message (Optional)

**Enhancement:** If a chunk matches, automatically fetch and concatenate all chunks from the same original message.

**Modified Response:**
```json
{
  "results": [
    {
      "id": "msg_123",  // Original message ID
      "memory": "This is a very long message about machine learning and deep learning. Machine learning is a subset of AI. Deep learning uses neural networks with multiple layers. These networks can learn complex patterns...",
      "score": 0.92,
      "chunks_used": [0, 1, 2],
      "metadata": {...}
    }
  ]
}
```

**Pros:**
- Returns complete context
- Easier for LLM to use

**Cons:**
- May return very long text (token limit issues)
- Loses granularity (which specific chunk matched)
- More complex (need to query for related chunks)

**Recommendation:** ❌ **Not needed** - Client can fetch related chunks if needed

---

### Option C: Add Chunk Filter (Optional)

**Enhancement:** Add filter to search only chunked or only non-chunked memories.

**Usage:**
```json
{
  "query": "machine learning",
  "user_id": "user123",
  "filters": {
    "is_chunk": false  // Only non-chunked memories
  }
}
```

**Pros:**
- More control over search results
- Can avoid chunked results if not needed

**Cons:**
- Current metadata filters already support this
- `filters: {"is_chunk": false}` should already work

**Recommendation:** ✅ **Already supported** via metadata filters

---

## 6. Implementation Plan

### Step 1: Add Chunking Logic in `_add_to_vector_store()`

**Location:** `mem0/memory/main.py` - `_add_to_vector_store()` method

**Logic:**
```python
def _add_to_vector_store(self, messages, metadata, filters, infer):
    if not infer:
        returned_memories = []
        for message_dict in messages:
            # ... existing validation ...
            
            msg_content = message_dict["content"]
            
            # Check if chunking is needed
            CHUNK_SIZE = 2000  # characters
            OVERLAP = 200      # characters
            
            if len(msg_content) > CHUNK_SIZE:
                # Chunk the message
                chunks = self._chunk_text(msg_content, CHUNK_SIZE, OVERLAP)
                original_message_id = str(uuid.uuid4())
                
                for chunk_index, chunk_text in enumerate(chunks):
                    # Create metadata for chunk
                    chunk_meta = deepcopy(metadata)
                    chunk_meta["role"] = message_dict["role"]
                    chunk_meta["original_message_id"] = original_message_id
                    chunk_meta["chunk_index"] = chunk_index
                    chunk_meta["total_chunks"] = len(chunks)
                    chunk_meta["is_chunk"] = True
                    
                    # Store chunk
                    chunk_embeddings = self.embedding_model.embed(chunk_text, "add")
                    mem_id = self._create_memory(chunk_text, chunk_embeddings, chunk_meta)
                    
                    returned_memories.append({
                        "id": mem_id,
                        "memory": chunk_text,
                        "event": "ADD",
                        "chunk_index": chunk_index,
                        "total_chunks": len(chunks),
                        "original_message_id": original_message_id
                    })
            else:
                # Store normally (no chunking)
                # ... existing code ...
```

### Step 2: Add Chunking Helper Method

**Location:** `mem0/memory/main.py` - Add new method

```python
def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Text to chunk
        chunk_size: Maximum characters per chunk
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        
        # Move start position with overlap
        start = end - overlap
        
        # Prevent infinite loop
        if start >= len(text):
            break
    
    return chunks
```

### Step 3: Test Search Behavior

**Test Cases:**
1. ✅ Search for query that matches chunked message → Should return matching chunks
2. ✅ Search for query that matches non-chunked message → Should return normal result
3. ✅ Search with filters → Should work with chunked data
4. ✅ Multiple chunks from same message match → Should return all matching chunks
5. ✅ Verify metadata is preserved in search results

---

## 7. Edge Cases & Considerations

### Edge Case 1: Very Short Chunks
**Issue:** If chunk size is too small, chunks may lose context.

**Solution:** Set reasonable minimum chunk size (e.g., 500 chars) or don't chunk if message is only slightly over threshold.

### Edge Case 2: Overlap Boundary Issues
**Issue:** Overlap might split words or sentences awkwardly.

**Solution:** Try to chunk at sentence boundaries within the chunk_size limit.

### Edge Case 3: Multiple Chunks in Search Results
**Issue:** If 3 chunks from same message all match, user gets 3 results.

**Current Behavior:** ✅ This is fine - user can see all relevant chunks.

**Optional Enhancement:** Client-side grouping by `original_message_id`.

### Edge Case 4: Partial Chunk Matches
**Issue:** Query might match only part of a chunk.

**Current Behavior:** ✅ Vector similarity handles this - returns chunk if semantically similar.

### Edge Case 5: Chunked vs Non-Chunked Mix
**Issue:** Search returns mix of chunked and non-chunked results.

**Current Behavior:** ✅ This is fine - both are valid memories.

---

## 8. Summary

### ✅ Search API Works Without Changes

**Reasons:**
1. Vector search is chunk-agnostic
2. Metadata is preserved and returned
3. Current response format supports chunked data
4. Filters work with chunk metadata

### ✅ Implementation Needed

**Changes Required:**
1. Add chunking logic in `_add_to_vector_store()` when `infer=false`
2. Add `_chunk_text()` helper method
3. Add chunk metadata to stored memories
4. Test with various message lengths

**No Changes Needed:**
- ❌ Search API endpoint
- ❌ Search implementation
- ❌ Vector store
- ❌ Response format

### ✅ Client-Side Handling

**Clients can:**
- Use chunks as-is (each chunk is a valid memory)
- Group chunks by `original_message_id` if needed
- Filter by `is_chunk` metadata if needed
- Reconstruct full message by fetching all chunks

---

## 9. Recommended Configuration

```python
# Suggested defaults
CHUNK_SIZE = 2000      # characters (adjust based on embedding model context)
OVERLAP = 200          # characters (10% overlap for context preservation)
MIN_CHUNK_SIZE = 500   # Don't chunk if result would be smaller than this
```

**Rationale:**
- 2000 chars ≈ 400-500 tokens (safe for most embedding models)
- 200 char overlap preserves context between chunks
- Minimum prevents over-chunking of slightly long messages

---

## 10. Testing Checklist

Before implementing, verify:
- [ ] Chunking only happens when text length > threshold
- [ ] Chunk metadata is stored correctly
- [ ] Search returns chunked results correctly
- [ ] Search returns non-chunked results correctly
- [ ] Filters work with chunk metadata
- [ ] Multiple chunks from same message can be found
- [ ] Overlap preserves context
- [ ] Edge cases (very short, very long, empty) are handled

---

## Conclusion

**✅ Search API does NOT need changes** - It will work correctly with chunked data.

**✅ Implementation is straightforward** - Add chunking logic in storage, metadata handles the rest.

**✅ Client flexibility** - Clients can use chunks as-is or group/reconstruct as needed.

