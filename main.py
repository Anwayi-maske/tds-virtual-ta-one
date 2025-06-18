from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import base64
import numpy as np
from typing import List, Dict

load_dotenv()
app = FastAPI()

# Initialize OpenAI client with AI Pipe proxy
client = OpenAI(
    api_key=os.getenv("AIPIPE_TOKEN"),
    base_url="https://aipipe.org/openai/v1"
)

# Load data (1).json
try:
    with open("data (1).json", "r") as f:
        course_data = json.load(f)
except FileNotFoundError:
    raise Exception("data (1).json not found in folder")

# Handle course_data as a list or dictionary
context_items: List[Dict] = []
embeddings: List[List[str]] = []

# If course_data is a list, iterate over each dictionary
if isinstance(course_data, list):
    github_files = []
    discourse_threads = []
    for data_item in course_data:
        github_files.extend(data_item.get("github_files", []))
        discourse_threads.extend(data_item.get("discourse_threads", []))
else:
    # If course_data is a dictionary
    github_files = course_data.get("github_files", [])
    discourse_threads = course_data.get("discourse_threads", [])

# Pre-embed course notes
for note in github_files:
    text = f"Course Note ({note.get('path', '')}): {note.get('content', '')[:2000]}"
    context_items.append({"type": "note", "text": text, "url": ""})

# Pre-embed Discourse posts
for thread in discourse_threads:
    for post in thread.get("posts", []):
        text = f"Discourse Post (Thread: {thread.get('title', '')}, Post #{post.get('post_number', '')}): {post.get('cooked', '')[:2000]}"
        url = f"https://discourse.onlinedegree.iitm.ac.in/t/{thread.get('slug', '')}/{thread.get('id', '')}/{post.get('post_number', '')}"
        context_items.append({"type": "post", "text": text, "url": url})

# Generate embeddings
for item in context_items:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=item["text"],
        service_tier="flex"
    )
    embeddings.append(response.data[0].embedding)

# Cosine similarity function
def cosine_similarity(a: List[float], b: List[float]) -> float:
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Pydantic models
class QuestionRequest(BaseModel):
    question: str
    image: str | None = None

class QuestionResponse(BaseModel):
    answer: str
    links: List[Dict[str, str]]

@app.post("/api/", response_model=QuestionResponse)
async def answer_question(request: QuestionRequest):
    try:
        # Decode base64 image
        image_content = ""
        if request.image:
            try:
                image_data = base64.b64decode(request.image)
                image_content = f"Image data received (size: {len(image_data)} bytes)."
            except Exception as e:
                image_content = f"Error decoding image: {str(e)}"

        # Embed question
        question_text = f"{request.question} {image_content}"
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=question_text,
            service_tier="flex"
        )
        question_embedding = response.data[0].embedding

        # Find top-3 relevant contexts
        similarities = [cosine_similarity(question_embedding, emb) for emb in embeddings]
        top_indices = np.argsort(similarities)[-3:][::-1]
        relevant_context = [context_items[i] for i in top_indices]
        context_text = " ".join(item["text"] for item in relevant_context)
        links = [
            {"url": item["url"], "text": item["text"][:100] + "..."}
            for item in relevant_context
            if item["url"]
        ]

        # LLM prompt
        prompt = f"""
        You are a virtual Teaching Assistant for the Tools in Data Science course (Jan 2025, IIT Madras).
        Answer the student question based on the provided context from course content and Discourse posts (Jan 1–Apr 14, 2025).
        Include relevant Discourse links if applicable.
        Question: {request.question}
        Image Info: {image_content}
        Context: {context_text[:4000]}
        Return a JSON object:
        {"answer": "Your answer", "links": [{"url": "link", "text": "description"}]}
        """
        # Call AI Pipe for chat completion
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
            return QuestionResponse(
                answer=response.choices[0].message.content,
                links=links
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
