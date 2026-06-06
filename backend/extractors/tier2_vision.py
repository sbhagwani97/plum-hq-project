"""
backend/extractors/tier2_vision.py
Together AI vision extraction for images.
"""
from __future__ import annotations
import base64
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
client = OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")

def encode_image(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode('utf-8')

def extract_text_from_image(file_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    base64_image = encode_image(file_bytes)
    model_name = "Qwen/Qwen3.5-9B"
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all the text from this medical document exactly as it is. Preserve the structure and layout. Return ONLY the extracted text."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        max_tokens=1500,
        temperature=0.0
    )
    return response.choices[0].message.content.strip()
