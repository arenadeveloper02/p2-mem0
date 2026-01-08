import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

from mem0.configs.prompts import (
    FACT_RETRIEVAL_PROMPT,
    USER_MEMORY_EXTRACTION_PROMPT,
    AGENT_MEMORY_EXTRACTION_PROMPT,
)

logger = logging.getLogger(__name__)


def get_fact_retrieval_messages(message, is_agent_memory=False):
    """Get fact retrieval messages based on the memory type.
    
    Args:
        message: The message content to extract facts from
        is_agent_memory: If True, use agent memory extraction prompt, else use user memory extraction prompt
        
    Returns:
        tuple: (system_prompt, user_prompt)
    """
    if is_agent_memory:
        return AGENT_MEMORY_EXTRACTION_PROMPT, f"Input:\n{message}"
    else:
        return USER_MEMORY_EXTRACTION_PROMPT, f"Input:\n{message}"


def get_fact_retrieval_messages_legacy(message):
    """Legacy function for backward compatibility."""
    return FACT_RETRIEVAL_PROMPT, f"Input:\n{message}"


def parse_messages(messages):
    response = ""
    for msg in messages:
        if msg["role"] == "system":
            response += f"system: {msg['content']}\n"
        if msg["role"] == "user":
            response += f"user: {msg['content']}\n"
        if msg["role"] == "assistant":
            response += f"assistant: {msg['content']}\n"
    return response


def format_entities(entities):
    if not entities:
        return ""

    formatted_lines = []
    for entity in entities:
        simplified = f"{entity['source']} -- {entity['relationship']} -- {entity['destination']}"
        formatted_lines.append(simplified)

    return "\n".join(formatted_lines)


def remove_code_blocks(content: str) -> str:
    """
    Removes enclosing code block markers ```[language] and ``` from a given string.

    Remarks:
    - The function uses a regex pattern to match code blocks that may start with ``` followed by an optional language tag (letters or numbers) and end with ```.
    - If a code block is detected, it returns only the inner content, stripping out the markers.
    - If no code block markers are found, the original content is returned as-is.
    """
    pattern = r"^```[a-zA-Z0-9]*\n([\s\S]*?)\n```$"
    match = re.match(pattern, content.strip())
    match_res=match.group(1).strip() if match else content.strip()
    return re.sub(r"<think>.*?</think>", "", match_res, flags=re.DOTALL).strip()



def extract_json(text):
    """
    Extracts JSON content from a string, removing enclosing triple backticks and optional 'json' tag if present.
    If no code block is found, returns the text as-is.
    """
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = text  # assume it's raw JSON
    return json_str


def get_image_description(image_obj, llm, vision_details):
    """
    Get the description of the image
    """

    if isinstance(image_obj, str):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "A user is providing an image. Provide a high level description of the image and do not include any additional text.",
                    },
                    {"type": "image_url", "image_url": {"url": image_obj, "detail": vision_details}},
                ],
            },
        ]
    else:
        messages = [image_obj]

    response = llm.generate_response(messages=messages)
    return response


def parse_vision_messages(messages, llm=None, vision_details="auto"):
    """
    Parse the vision messages from the messages
    """
    returned_messages = []
    for msg in messages:
        if msg["role"] == "system":
            returned_messages.append(msg)
            continue

        # Handle message content
        if isinstance(msg["content"], list):
            # Multiple image URLs in content
            description = get_image_description(msg, llm, vision_details)
            returned_messages.append({"role": msg["role"], "content": description})
        elif isinstance(msg["content"], dict) and msg["content"].get("type") == "image_url":
            # Single image content
            image_url = msg["content"]["image_url"]["url"]
            try:
                description = get_image_description(image_url, llm, vision_details)
                returned_messages.append({"role": msg["role"], "content": description})
            except Exception:
                raise Exception(f"Error while downloading {image_url}.")
        else:
            # Regular text content
            returned_messages.append(msg)

    return returned_messages


def process_telemetry_filters(filters):
    """
    Process the telemetry filters
    """
    if filters is None:
        return {}

    encoded_ids = {}
    if "user_id" in filters:
        encoded_ids["user_id"] = hashlib.md5(filters["user_id"].encode()).hexdigest()
    if "agent_id" in filters:
        encoded_ids["agent_id"] = hashlib.md5(filters["agent_id"].encode()).hexdigest()
    if "run_id" in filters:
        encoded_ids["run_id"] = hashlib.md5(filters["run_id"].encode()).hexdigest()

    return list(filters.keys()), encoded_ids


def sanitize_relationship_for_cypher(relationship) -> str:
    """Sanitize relationship text for Cypher queries by replacing problematic characters."""
    char_map = {
        "...": "_ellipsis_",
        "…": "_ellipsis_",
        "。": "_period_",
        "，": "_comma_",
        "；": "_semicolon_",
        "：": "_colon_",
        "！": "_exclamation_",
        "？": "_question_",
        "（": "_lparen_",
        "）": "_rparen_",
        "【": "_lbracket_",
        "】": "_rbracket_",
        "《": "_langle_",
        "》": "_rangle_",
        "'": "_apostrophe_",
        '"': "_quote_",
        "\\": "_backslash_",
        "/": "_slash_",
        "|": "_pipe_",
        "&": "_ampersand_",
        "=": "_equals_",
        "+": "_plus_",
        "*": "_asterisk_",
        "^": "_caret_",
        "%": "_percent_",
        "$": "_dollar_",
        "#": "_hash_",
        "@": "_at_",
        "!": "_bang_",
        "?": "_question_",
        "(": "_lparen_",
        ")": "_rparen_",
        "[": "_lbracket_",
        "]": "_rbracket_",
        "{": "_lbrace_",
        "}": "_rbrace_",
        "<": "_langle_",
        ">": "_rangle_",
    }

    # Apply replacements and clean up
    sanitized = relationship
    for old, new in char_map.items():
        sanitized = sanitized.replace(old, new)

    return re.sub(r"_+", "_", sanitized).strip("_")


def count_tokens(text: str, model: str = "text-embedding-3-small") -> int:
    """
    Count tokens in text using tiktoken for accurate counting.
    Falls back to character-based estimation if tiktoken is unavailable.
    
    Args:
        text: The text to count tokens for
        model: The model name to use for tokenization (default: text-embedding-3-small)
        
    Returns:
        int: Estimated token count
    """
    if not text:
        return 0
    
    if TIKTOKEN_AVAILABLE:
        try:
            # Use cl100k_base encoding which is used by text-embedding-3-small and similar models
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(f"Failed to count tokens with tiktoken: {e}. Falling back to character-based estimation.")
    
    # Fallback: approximate 1 token ≈ 4 characters
    return len(text) // 4


def chunk_text_intelligently(
    text: str,
    max_tokens: int = 1024,
    overlap_tokens: int = 200,
    min_chunk_size_chars: int = 100,
) -> List[Dict[str, Any]]:
    """
    Chunk text intelligently preserving sentence boundaries with token-aware splitting.
    
    Args:
        text: The text to chunk
        max_tokens: Maximum tokens per chunk (default: 1024)
        overlap_tokens: Number of tokens to overlap between chunks (default: 200)
        min_chunk_size_chars: Minimum chunk size in characters (default: 100)
        
    Returns:
        List of dictionaries containing:
            - text: The chunk text
            - start_pos: Starting character position in original text
            - end_pos: Ending character position in original text
            - token_count: Token count for this chunk
    """
    if not text:
        return []
    
    # Convert token limits to character estimates for initial splitting
    # 1 token ≈ 4 characters, but we'll be more conservative
    max_chars_per_chunk = max_tokens * 4
    overlap_chars = overlap_tokens * 4
    
    # If text is small enough, return as single chunk
    estimated_tokens = count_tokens(text)
    if estimated_tokens <= max_tokens:
        return [{
            "text": text,
            "start_pos": 0,
            "end_pos": len(text),
            "token_count": estimated_tokens
        }]
    
    chunks = []
    current_pos = 0
    text_length = len(text)
    
    # Sentence boundary patterns (period, exclamation, question mark, followed by space or newline)
    sentence_endings = re.compile(r'[.!?]+(?:\s+|$)')
    
    while current_pos < text_length:
        # Calculate the end position for this chunk
        chunk_end = min(current_pos + max_chars_per_chunk, text_length)
        
        # If we're not at the end of the text, try to find a sentence boundary
        if chunk_end < text_length:
            # Look for sentence endings in the last 20% of the chunk
            search_start = max(current_pos, chunk_end - int(max_chars_per_chunk * 0.2))
            search_text = text[search_start:chunk_end]
            
            matches = list(sentence_endings.finditer(search_text))
            if matches:
                # Use the last sentence boundary found
                last_match = matches[-1]
                chunk_end = search_start + last_match.end()
        
        # Extract the chunk
        chunk_text = text[current_pos:chunk_end].strip()
        
        # Skip if chunk is too small (unless it's the last chunk)
        if len(chunk_text) < min_chunk_size_chars and chunk_end < text_length:
            # Try to extend to next sentence boundary
            remaining_text = text[chunk_end:]
            next_sentence_match = sentence_endings.search(remaining_text)
            if next_sentence_match:
                chunk_end = chunk_end + next_sentence_match.end()
                chunk_text = text[current_pos:chunk_end].strip()
            else:
                # If no sentence boundary found, just take the minimum size
                chunk_end = min(current_pos + min_chunk_size_chars, text_length)
                chunk_text = text[current_pos:chunk_end].strip()
        
        # Count tokens for this chunk
        chunk_tokens = count_tokens(chunk_text)
        
        # If chunk exceeds max_tokens, we need to split more aggressively
        if chunk_tokens > max_tokens:
            # Split by sentences more aggressively
            sentences = sentence_endings.split(chunk_text)
            current_sentence_pos = current_pos
            current_sentence_chunk = ""
            current_sentence_tokens = 0
            
            for sentence in sentences:
                if not sentence.strip():
                    continue
                    
                sentence_text = sentence.strip()
                sentence_tokens = count_tokens(sentence_text)
                
                # If adding this sentence would exceed max_tokens, save current chunk and start new one
                if current_sentence_tokens + sentence_tokens > max_tokens and current_sentence_chunk:
                    chunks.append({
                        "text": current_sentence_chunk.strip(),
                        "start_pos": current_sentence_pos,
                        "end_pos": current_sentence_pos + len(current_sentence_chunk),
                        "token_count": current_sentence_tokens
                    })
                    current_sentence_pos = current_sentence_pos + len(current_sentence_chunk)
                    current_sentence_chunk = sentence_text
                    current_sentence_tokens = sentence_tokens
                else:
                    current_sentence_chunk += (" " + sentence_text if current_sentence_chunk else sentence_text)
                    current_sentence_tokens += sentence_tokens
            
            # Add the last sentence chunk
            if current_sentence_chunk:
                chunks.append({
                    "text": current_sentence_chunk.strip(),
                    "start_pos": current_sentence_pos,
                    "end_pos": current_sentence_pos + len(current_sentence_chunk),
                    "token_count": current_sentence_tokens
                })
            
            # Move position forward, accounting for overlap
            if overlap_tokens > 0 and chunk_end < text_length:
                # Find overlap position (go back by overlap_tokens worth of characters)
                overlap_chars = min(overlap_chars, len(chunk_text) // 2)  # Don't overlap more than half
                # Try to find a sentence boundary in the overlap region
                overlap_start = chunk_end - overlap_chars
                overlap_text = text[overlap_start:chunk_end]
                overlap_matches = list(sentence_endings.finditer(overlap_text))
                if overlap_matches:
                    overlap_pos = overlap_start + overlap_matches[-1].end()
                else:
                    overlap_pos = overlap_start
                current_pos = max(current_pos + 1, overlap_pos)
            else:
                current_pos = chunk_end
        else:
            # Chunk is within token limit, add it
            chunks.append({
                "text": chunk_text,
                "start_pos": current_pos,
                "end_pos": chunk_end,
                "token_count": chunk_tokens
            })
            
            # Move position forward, accounting for overlap
            if overlap_tokens > 0 and chunk_end < text_length:
                # Find overlap position
                overlap_chars = min(overlap_chars, len(chunk_text) // 2)
                overlap_start = chunk_end - overlap_chars
                overlap_text = text[overlap_start:chunk_end]
                overlap_matches = list(sentence_endings.finditer(overlap_text))
                if overlap_matches:
                    overlap_pos = overlap_start + overlap_matches[-1].end()
                else:
                    overlap_pos = overlap_start
                current_pos = max(current_pos + 1, overlap_pos)
            else:
                current_pos = chunk_end
    
    # Filter out empty chunks and ensure minimum size
    final_chunks = []
    for chunk in chunks:
        if chunk["text"] and len(chunk["text"]) >= min_chunk_size_chars:
            final_chunks.append(chunk)
        elif chunk["text"] and len(final_chunks) > 0:
            # Merge small chunk with previous one if possible
            prev_chunk = final_chunks[-1]
            combined_text = prev_chunk["text"] + " " + chunk["text"]
            combined_tokens = count_tokens(combined_text)
            if combined_tokens <= max_tokens:
                final_chunks[-1] = {
                    "text": combined_text,
                    "start_pos": prev_chunk["start_pos"],
                    "end_pos": chunk["end_pos"],
                    "token_count": combined_tokens
                }
            else:
                # Can't merge, add as separate chunk (even if small)
                final_chunks.append(chunk)
    
    return final_chunks if final_chunks else [{
        "text": text,
        "start_pos": 0,
        "end_pos": len(text),
        "token_count": count_tokens(text)
    }]

