# main.py
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import traceback

load_dotenv()  # load .env

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Put your key in a .env file.")

# Create the new OpenAI client
client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI(title="Venkateshpura Chatbot (Phase1)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat(req: ChatRequest):
    user_message = req.message
    try:
        # New API: client.chat.completions.create(...)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # swap to a model available to you if needed
            messages=[
                {"role": "system", "content": "You are a friendly assistant that knows about lakes and ecology. Keep answers short (2-4 sentences)."},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        # The shape: resp.choices[0].message.content (new client uses `.message` or dict; handle below)
        # Convert both object and dict shapes safely:
        try:
            reply = resp.choices[0].message["content"].strip()
        except Exception:
            # fallback in case resp is dict-like
            reply = resp.choices[0].message.content.strip() if hasattr(resp.choices[0].message, "content") else str(resp)
        return {"reply": reply}
    except Exception as e:
        tb = traceback.format_exc()
        print("==== Exception in /chat ====\n", tb)
        raise HTTPException(status_code=500, detail=f"Server error during OpenAI call: {str(e)}")
