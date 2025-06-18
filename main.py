from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import base64
import numpy as np
from typing import List, Dict
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI()

# Initialize OpenAI client
client = OpenAI(
    api_key=os.getenv("AIPIPE_TOKEN"),
    base_url="https://aipipe.org/openai/v1"
)

# Load data (1).json
try:
    logger.info(f"Loading data from {os.path.abspath('data (1).json')}")
    with open("data (1).json", "r") as f:
        course_data = json.load(f)
    logger.info(f"Loaded data of type {type(course_data)} with {len(course_data)} items")
except FileNotFoundError as e:
    logger.error(f"data (1).json not found: {e}")
    raise
except json.JSONDecodeError as e:
    logger.error(f"Invalid JSON in data (1).json: {e}")
    raise

# Initialize data structures
context_items: List[Dict] = []
embeddings: List[List[float]] = []

# Process course_data
github_files = []
discourse_threads = []
if isinstance(course_data, list):
    for data_item in course_data:
        if not isinstance(data_item, dict) or not data_item:  # Skip empty or non-dict items
            logger.warning(f"Skipping invalid data item: {data_item}")
            continue
        github_files.extend(data_item.get("github_files", []))
        discourse_threads.extend(data_item.get("discourse_threads", []))
elif isinstance(course_data, dict):
    github_files = course_data.get("github_files", [])
    discourse_threads = course_data.get("discourse_threads", [])
else:
    logger.error(f"Unexpected data type: {type(course_data)}")
    raise ValueError("data (1).json must be a list or dictionary")

logger.info(f"Extracted {len(github_files)} github files and {len(discourse_threads)} discourse threads")

# Pre-embed course notes
for note in github_files:
    path = note.get("path", "")
    content = note.get("content", "")[:4000]  # Increased limit
    if not content:
        logger.warning(f"Empty content for note: {path}")
        continue
    text = f"Course Note ({path}): {content}"
    context_items.append({"type": "note", "text": text, "url": ""})

# Pre-embed Discourse posts
for thread in discourse_threads:
    title = thread.get("title", "")
    slug = thread.get("slug", "")
    thread_id = thread.get("id", "")
    for post in thread.get("posts", []):
        post_number = post.get("post_number", "")
        content = post.get("cooked", "")[:4000]
        if not content or not slug or not thread_id or not post_number:
            logger.warning(f"Skipping invalid post in thread: {title}")
            continue
        text = f"Discourse Post (Thread: {title}, Post #{post_number}): {content}"
        url = f"https://discourse.onlinedegree.iitm.ac.in/t/{slug}/{thread_id}/{post_number}"
        context_items.append({"type": "post", "text": text, "url": url})

logger.info(f"Created {len(context_items)} context items")

# Generate embeddings with error handling
for item in context_items:
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=item["text"],
            service_tier="flex"
        )
        embeddings.append(response.data[0].embedding)
    except Exception as e:
        logger.error(f"Error generating embedding for {item['text'][:50]}...: {e}")
        embeddings.append([0.0] * 1536)  # Fallback embedding (matches text-embedding-3-small)

logger.info(f"Generated {len(embeddings)} embeddings")

# Cosine similarity
def cosine_similarity(a: List[float], b: List[float]) -> float:
    a = np.array(a)
    b = np.array(b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)

# Pydantic models
class QuestionRequest(BaseModel):
    question: str
    image: str | None = None

class QuestionResponse(BaseModel):
    answer: str
    links: List[Dict[str, str]]

@app.post("/api/", response_model=QuestionResponse)
async def answer_question(request: QuestionRequest):
    logger.info(f"Received question: {request.question}")
    try:
        # Handle image
        image_content = ""
        if request.image:
            try:
                image_data = base64.b64decode(request.image)
                image_content = f"Image provided (size: {len(image_data)} bytes)."
                logger.info(image_content)
            except Exception as e:
                image_content = f"Invalid image data: {str(e)}"
                logger.warning(image_content)

        # Embed question
        question_text = request.question  # Exclude image_content from embedding
        try:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=question_text,
                service_tier="flex"
            )
            question_embedding = response.data[0].embedding
        except Exception as e:
            logger.error(f"Error embedding question: {e}")
            raise HTTPException(status_code=500, detail=f"Embedding error: {str(e)}")

        # Find top-3 relevant contexts
        similarities = [cosine_similarity(question_embedding, emb) for emb in embeddings]
        top_indices = np.argsort(similarities)[-3:][::-1]
        relevant_context = [context_items[i] for i in top_indices]
        context_text = "\n".join(item["text"] for item in relevant_context)[:8000]  # Increased limit
        links = [
            {"url": item["url"], "text": item["text"][:100] + "..."}
            for item in relevant_context if item["url"]
        ]
        logger.info(f"Found {len(relevant_context)} relevant contexts")

        # LLM prompt
        prompt = f"""
        You are a virtual Teaching Assistant for the Tools in Data Science course (Jan 2025, IIT Madras).
        Answer the question based on the provided context (course notes and Discourse posts, Jan 1–Apr 14, 2025).
        Keep the answer concise and include relevant Discourse links if applicable.
        Question: {request.question}
        Image Info: {image_content}
        Context: {context_text}
        Return a JSON object: {"answer": "Your answer", "links": [{"url": "link", "text": "description"}]}
        """
        # Call AI Pipe
        try:
            response = client.chat.completions.create(
                model="openai/gpt-3.5-turbo-0125",
                messages=[
                    {"role": "system", "content": "You are a helpful TA for TDS."},
                    {"role": "user", "content": prompt}
                ],
                service_tier="flex",
                timeout=20
            )
            # Parse response
            try:
                result = json.loads(response.choices[0].message.content)
                result["links"] = links or result.get("links", [])
                return QuestionResponse(**result)
            except json.JSONDecodeError:
                logger.warning("LLM returned non-JSON response")
                return QuestionResponse(
                    answer=response.choices[0].message.content,
                    links=links
                )
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in /api/: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
