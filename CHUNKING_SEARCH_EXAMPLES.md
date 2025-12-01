# Chunking & Search: Concrete Examples

## Example 1: Long Message Gets Chunked

### Input (Storage):
```json
{
  "messages": [
    {
      "role": "user",
      "content": "I've been working on a machine learning project for the past 6 months. The project involves building a deep learning model using neural networks. We're using TensorFlow and PyTorch for the implementation. The model architecture consists of multiple convolutional layers followed by fully connected layers. We've achieved 95% accuracy on the test set. The training process took about 2 weeks on GPU clusters. We're planning to deploy this model to production next month."
    }
  ],
  "user_id": "user123",
  "infer": false
}
```

**Message Length:** ~600 characters (assume threshold is 2000, so this won't chunk)
**But if threshold was 500:** Would be chunked into 2 chunks

### If Chunked (threshold=500):
```
Chunk 1 (0-500): "I've been working on a machine learning project for the past 6 months. The project involves building a deep learning model using neural networks. We're using TensorFlow and PyTorch for the implementation. The model architecture consists of multiple convolutional layers followed by fully connected layers. We've achieved 95% accuracy on the test set. The training process took about 2 weeks on GPU clusters. We're planning to deploy this model to production next month."
[Last 200 chars overlap with next chunk]

Chunk 2 (300-600): "...The model architecture consists of multiple convolutional layers followed by fully connected layers. We've achieved 95% accuracy on the test set. The training process took about 2 weeks on GPU clusters. We're planning to deploy this model to production next month."
```

### Storage Result:
```json
{
  "results": [
    {
      "id": "mem_chunk_1_abc123",
      "memory": "I've been working on a machine learning project...",
      "event": "ADD",
      "chunk_index": 0,
      "total_chunks": 2,
      "original_message_id": "msg_xyz789"
    },
    {
      "id": "mem_chunk_2_def456",
      "memory": "...The model architecture consists of multiple...",
      "event": "ADD",
      "chunk_index": 1,
      "total_chunks": 2,
      "original_message_id": "msg_xyz789"
    }
  ]
}
```

---

## Example 2: Search Query Matches Chunked Message

### Search Request:
```json
{
  "query": "neural networks",
  "user_id": "user123"
}
```

### Search Process:
1. Query "neural networks" is embedded
2. Vector similarity search finds:
   - Chunk 1: score 0.85 (contains "neural networks")
   - Chunk 2: score 0.82 (contains "neural networks" in overlap)
   - Other unrelated memory: score 0.45

### Search Response (Current API - NO CHANGES NEEDED):
```json
{
  "results": [
    {
      "id": "mem_chunk_1_abc123",
      "memory": "I've been working on a machine learning project for the past 6 months. The project involves building a deep learning model using neural networks. We're using TensorFlow and PyTorch for the implementation. The model architecture consists of multiple convolutional layers followed by fully connected layers. We've achieved 95% accuracy on the test set. The training process took about 2 weeks on GPU clusters. We're planning to deploy this model to production next month.",
      "score": 0.85,
      "metadata": {
        "original_message_id": "msg_xyz789",
        "chunk_index": 0,
        "total_chunks": 2,
        "is_chunk": true,
        "role": "user",
        "user_id": "user123"
      }
    },
    {
      "id": "mem_chunk_2_def456",
      "memory": "...The model architecture consists of multiple convolutional layers followed by fully connected layers. We've achieved 95% accuracy on the test set. The training process took about 2 weeks on GPU clusters. We're planning to deploy this model to production next month.",
      "score": 0.82,
      "metadata": {
        "original_message_id": "msg_xyz789",
        "chunk_index": 1,
        "total_chunks": 2,
        "is_chunk": true,
        "role": "user",
        "user_id": "user123"
      }
    }
  ]
}
```

**✅ Both chunks are returned** - Client can see both relevant parts of the message.

---

## Example 3: Search Query Matches Only One Chunk

### Search Request:
```json
{
  "query": "TensorFlow",
  "user_id": "user123"
}
```

### Search Response:
```json
{
  "results": [
    {
      "id": "mem_chunk_1_abc123",
      "memory": "I've been working on a machine learning project... We're using TensorFlow and PyTorch...",
      "score": 0.91,
      "metadata": {
        "original_message_id": "msg_xyz789",
        "chunk_index": 0,
        "total_chunks": 2,
        "is_chunk": true,
        "role": "user",
        "user_id": "user123"
      }
    }
  ]
}
```

**✅ Only the relevant chunk is returned** - Chunk 2 doesn't mention TensorFlow, so it's not in results.

---

## Example 4: Mixed Results (Chunked + Non-Chunked)

### Search Request:
```json
{
  "query": "machine learning",
  "user_id": "user123"
}
```

### Search Response:
```json
{
  "results": [
    {
      "id": "mem_normal_111",
      "memory": "I love machine learning and AI",
      "score": 0.88,
      "metadata": {
        "role": "user",
        "user_id": "user123"
        // No chunk metadata = not chunked
      }
    },
    {
      "id": "mem_chunk_1_abc123",
      "memory": "I've been working on a machine learning project...",
      "score": 0.85,
      "metadata": {
        "original_message_id": "msg_xyz789",
        "chunk_index": 0,
        "total_chunks": 2,
        "is_chunk": true,
        "role": "user",
        "user_id": "user123"
      }
    }
  ]
}
```

**✅ Both types work together** - Search doesn't distinguish between chunked and non-chunked.

---

## Example 5: Filtering Chunked Results

### Search Request (Only Non-Chunked):
```json
{
  "query": "machine learning",
  "user_id": "user123",
  "filters": {
    "is_chunk": false
  }
}
```

### Search Response:
```json
{
  "results": [
    {
      "id": "mem_normal_111",
      "memory": "I love machine learning and AI",
      "score": 0.88,
      "metadata": {
        "role": "user",
        "user_id": "user123"
      }
    }
  ]
}
```

**✅ Filter works** - Only non-chunked results returned.

---

## Example 6: Client-Side Chunk Reconstruction (Optional)

### If Client Wants Full Message:

**Step 1:** Search returns chunk
```json
{
  "id": "mem_chunk_1_abc123",
  "memory": "I've been working on a machine learning project...",
  "metadata": {
    "original_message_id": "msg_xyz789",
    "chunk_index": 0,
    "total_chunks": 2
  }
}
```

**Step 2:** Client groups by `original_message_id` and fetches all chunks
```python
# Pseudo-code
chunks = search_results.filter(lambda r: r.metadata.original_message_id == "msg_xyz789")
chunks.sort(key=lambda c: c.metadata.chunk_index)
full_message = "".join([c.memory for c in chunks])
```

**Step 3:** Use full message in context
```
Full reconstructed message: "I've been working on a machine learning project... [chunk 1] ... [chunk 2] ..."
```

**✅ Client can reconstruct** - But this is optional, chunks work fine individually.

---

## Key Takeaways

1. **✅ Search works without changes** - Returns chunks as separate results
2. **✅ Metadata is preserved** - Client knows which chunks belong together
3. **✅ Filters work** - Can filter by `is_chunk` if needed
4. **✅ Mixed results work** - Chunked and non-chunked memories coexist
5. **✅ Client flexibility** - Use chunks individually or reconstruct as needed

---

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    STORAGE (infer=false)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Check Length    │
                    │ > threshold?    │
                    └─────────────────┘
                    │              │
            YES     │              │ NO
                    ▼              ▼
        ┌───────────────┐  ┌──────────────┐
        │ Chunk Text    │  │ Store Single │
        │ (with overlap)│  │ Vector       │
        └───────────────┘  └──────────────┘
                    │              │
                    ▼              │
        ┌───────────────────────────┐
        │ Store Each Chunk as       │
        │ Separate Vector           │
        │ + Chunk Metadata           │
        └───────────────────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │ Vector DB (Milvus)         │
        │ - Chunk 1: vector + meta   │
        │ - Chunk 2: vector + meta   │
        │ - Normal: vector + meta    │
        └───────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    SEARCH                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Embed Query     │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Vector Search   │
                    │ (Similarity)    │
                    └─────────────────┘
                              │
                              ▼
        ┌───────────────────────────────────────┐
        │ Return Top-K Results                  │
        │ - Chunked memories (if match)         │
        │ - Non-chunked memories (if match)     │
        │ - All with metadata                   │
        └───────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Client Receives │
                    │ Results         │
                    └─────────────────┘
                              │
                              ▼
        ┌───────────────────────────────────────┐
        │ Client Options:                        │
        │ 1. Use chunks as-is                    │
        │ 2. Group by original_message_id        │
        │ 3. Reconstruct full message            │
        │ 4. Filter by is_chunk metadata         │
        └───────────────────────────────────────┘
```

