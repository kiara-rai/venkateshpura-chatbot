# main.py
import os
import json
import time
import traceback
from fastapi import FastAPI, HTTPException, UploadFile, File
import requests
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv


# OpenAI client import (you're already using this)
from openai import OpenAI
import openai as openai_pkg  # for checking exception types when available

load_dotenv()  # load local .env in development

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Put your key in a .env file or Render environment variables.")
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")
# Optional check for the new key (good practice)
if not PLANTNET_API_KEY:
    # Modify the existing check to include the Pl@ntNet key error, 
    # or just assume it's only needed for the /api/identify endpoint
    print("Warning: PLANTNET_API_KEY not found. Identification endpoint will fail.")

    # main.py

# ... (After environment setup, before FastAPI instance 'app = FastAPI(...)')

def get_species_contribution(scientific_name: str) -> str:
    """Returns a simple ecological contribution text for the identified species."""
    # NOTE: You should expand this dictionary with species relevant to your lake!
    species_contributions = { 
        "Nymphaea alba": "The White Water Lily is a vital **producer** that provides shade, cover for fish spawning, and stabilizes bottom sediment, which helps reduce lake cloudiness (turbidity).",
        "Typha latifolia": "Broadleaf Cattail is important for **shoreline stability** and provides nesting habitat, but its dense growth can lead to marsh encroachment.",
        "Potamogeton crispus": "Curled Pondweed provides good cover for juvenile fish and invertebrates, but can become invasive in nutrient-rich water.",
    }
    
    # Fallback for plants not explicitly listed
    generic_plant_text = "This type of aquatic vegetation is a **primary producer**, playing a key role in oxygenating the water and providing crucial food and shelter for insects and young fish."
    
    # Look up the specific name, falling back to the generic text
    return species_contributions.get(scientific_name, generic_plant_text)

# ... rest of your code (app = FastAPI(...), CORS setup, etc.)


# Behavior toggles
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "*")  # comma-separated or '*' for dev

# Create OpenAI client
client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI(title="Venkateshpura Chatbot (Phase1)")

# CORS setup: allow origins from FRONTEND_ORIGINS env var (comma separated)
if FRONTEND_ORIGINS.strip() == "*" or FRONTEND_ORIGINS.strip() == "":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in FRONTEND_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === REPORT ISSUE ENDPOINT ===
from fastapi import BackgroundTasks

class Report(BaseModel):
    name: str | None = None
    email: str | None = None
    category: str | None = None
    details: str | None = None
    ts: str | None = None

REPORT_LOG = "reports.jsonl"

def log_report(entry):
    try:
        with open(REPORT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("Failed to log report:", e)

@app.post("/report")
async def report_endpoint(r: Report, background_tasks: BackgroundTasks):
    entry = r.dict()
    entry["received_at"] = time.time()
    background_tasks.add_task(log_report, entry)
    return {"status": "ok", "message": "Report received"}

# main.py

# ... (After your existing @app.post("/report") endpoint)

# === SPECIES IDENTIFICATION ENDPOINT ===
PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"

@app.post("/api/identify")
async def identify_plant(image: UploadFile = File(...)):
    """Handles image upload, calls Pl@ntNet, and returns identification plus contribution."""

    if not PLANTNET_API_KEY:
        # Prevent API call if key is missing
        raise HTTPException(status_code=500, detail="Pl@ntNet API Key not configured on server.")

    # 1. Prepare data for Pl@ntNet API call
    # FastAPI's UploadFile object provides 'file.file' which is the underlying stream/file object.
    files = {'images': (image.filename, image.file)} 
    
    params = {
        'api-key': PLANTNET_API_KEY,
       # 'organs': 'auto' # Use 'auto' to let the AI decide
    }
    
    # 2. Call Pl@ntNet API
    try:
        response = requests.post(PLANTNET_URL, params=params, files=files)
        response.raise_for_status() # Raise exception for 4xx/5xx errors
        
        data = response.json()
        
        # 3. Process the top result
        if data['results']:
            top_match = data['results'][0]
            
            # Extract key data points
            scientific_name = top_match['species']['scientificName']
            # Fallback for common name if list is empty
            common_name = top_match['species']['commonNames'][0] if top_match['species']['commonNames'] else scientific_name 
            
            # Get the contribution text using your new function
            contribution_text = get_species_contribution(scientific_name)
            
            return {
                "scientificName": scientific_name,
                "commonName": common_name,
                "confidence": round(top_match['score'] * 100, 2), # Convert score to percentage
                "contribution": contribution_text
            }
        else:
            return {"message": "Could not identify species with high confidence. Please try another photo."}

    except requests.exceptions.HTTPError as e:
        # Catch errors from the external API (e.g., rate limit, bad request)
        print(f"Pl@ntNet HTTP Error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Pl@ntNet API Error: {e.response.text}")
    except Exception as e:
        # Catch generic errors (network, etc.)
        tb = traceback.format_exc()
        print("==== Exception in /api/identify ====\n", tb)
        raise HTTPException(status_code=500, detail="Internal server error during identification.")

class ChatRequest(BaseModel):
    message: str

LOGFILE = "chat_logs.jsonl"

def log_chat(user_message: str, reply_text: str):
    try:
        entry = {"ts": time.time(), "message": user_message, "reply": reply_text}
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # don't fail chat because logging failed
        print("Warning: failed to write log:", e)

@app.get("/")
def health():
    return {"status":"ok", "service":"Venkateshpura Chatbot"}

@app.post("/chat")
async def chat(req: ChatRequest):
    user_message = (req.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")

    # 1) MOCK mode quick reply (useful if billing/quota issues)
    if MOCK_MODE:
        mock_reply = "This is a temporary mock reply (MOCK_MODE)."
        log_chat(user_message, mock_reply)
        return {"reply": mock_reply}

    # 2) Call OpenAI (safe wrapper)
    try:
        # Use the chat completion endpoint you used earlier
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # change to a model you have access to if needed
            messages=[
                {"role": "system", "content": "You are a friendly assistant that knows about lakes and ecology. Keep answers short (2-4 sentences)."},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            temperature=0.3,
        )

        # Attempt to extract reply in multiple possible shapes
        reply = None
        try:
            # new style: resp.choices[0].message["content"]
            reply = resp.choices[0].message["content"].strip()
        except Exception:
            try:
                reply = resp.choices[0].message.content.strip()
            except Exception:
                # fallback stringify
                reply = str(resp)

        # Log
        log_chat(user_message, reply)
        return {"reply": reply}

    except Exception as e:
        tb = traceback.format_exc()
        print("==== Exception in /chat ====\n", tb)

        # If it's a known OpenAI quota/rate error, surface friendlier message
        err_text = str(e)
        # Attempt to detect rate/insufficient_quota
        if hasattr(e, "code") and e.code in ("insufficient_quota", "rate_limit_exceeded"):
            friendly = "Service temporarily unavailable due to quota/limits. Try again later."
            log_chat(user_message, friendly)
            return {"reply": friendly}
        # If openai package provides a RateLimitError, try to detect that
        try:
            if isinstance(e, getattr(openai_pkg.error, "RateLimitError", Exception)):
                friendly = "OpenAI rate-limit reached. Try again shortly."
                log_chat(user_message, friendly)
                return {"reply": friendly}
        except Exception:
            pass

        # Generic fallback
        raise HTTPException(status_code=500, detail=f"Server error during OpenAI call: {err_text}")
