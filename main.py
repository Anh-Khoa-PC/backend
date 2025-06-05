from fastapi import FastAPI
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_FACT_CHECK_API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
GOOGLE_API_KEY = os.getenv("GOOGLE_FACTCHECK_API_KEY")

app = FastAPI()

class NewsCheckRequest(BaseModel):
    title: str = ""
    content: str = ""
    url: str = ""

class NewsCheckResponse(BaseModel):
    is_fake: bool
    confidence: float  # 0-1
    sources: list
    summary: str
    suggestions: list

@app.post("/api/check-fake-news", response_model=NewsCheckResponse)
async def check_fake_news(req: NewsCheckRequest):
    query = req.title or req.content
    response = requests.get(GOOGLE_FACT_CHECK_API, params={
        "query": query,
        "key": GOOGLE_API_KEY
    })
    data = response.json()
    sources = []
    is_fake = False
    confidence = 0.5
    summary = "Không tìm thấy xác thực."
    suggestions = []

    if "claims" in data:
        for claim in data["claims"]:
            review = claim["claimReview"][0]
            sources.append(review["url"])
            rating = review.get("textualRating", "").lower()
            if "false" in rating or "fake" in rating or "sai" in rating:
                is_fake = True
                confidence = 0.9
                summary = review.get("textualRating", "")
                break
            else:
                confidence = 0.7
                summary = review.get("textualRating", "")
    else:
        suggestions.append("Hãy kiểm tra thêm với các nguồn tin chính thống.")

    return NewsCheckResponse(
        is_fake=is_fake,
        confidence=confidence,
        sources=sources,
        summary=summary,
        suggestions=suggestions
    )