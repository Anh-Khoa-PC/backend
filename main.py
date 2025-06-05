import re
from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

GOOGLE_FACT_CHECK_API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
GOOGLE_API_KEY = os.getenv("GOOGLE_FACTCHECK_API_KEY", "")
GOOGLE_VISION_API = "https://vision.googleapis.com/v1/images:annotate"
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "")

class NewsCheckRequest(BaseModel):
    title: str = ""
    content: str = ""
    url: str = ""

class NewsCheckResponse(BaseModel):
    is_fake: bool
    confidence: float
    sources: list
    summary: str
    suggestions: list

# Một số từ khoá phổ biến của tin giả
FAKE_NEWS_KEYWORDS = [
    r"giật gân", r"100% (đúng|sai)", r"tin đồn", r"lừa đảo", r"chắc chắn", r"không thể tin được",
    r"bạn sẽ sốc", r"chia sẻ ngay", r"lan truyền", r"bí mật", r"shock", r"siêu hot",
]
TRUSTED_DOMAINS = [
    "vnexpress.net", "tuoitre.vn", "thanhnien.vn", "bbc.co.uk", "reuters.com", "cafef.vn",
    "zingnews.vn", "dantri.com.vn"
]

def has_fake_keywords(text):
    for kw in FAKE_NEWS_KEYWORDS:
        if re.search(kw, text, re.IGNORECASE):
            return True
    return False

def trusted_source(sources):
    for src in sources:
        for domain in TRUSTED_DOMAINS:
            if domain in src:
                return True
    return False

@app.post("/api/check-fake-news", response_model=NewsCheckResponse)
async def check_fake_news(req: NewsCheckRequest):
    query = req.url or req.title or req.content
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
            if "false" in rating or "fake" in rating or "hoax" in rating or "sai" in rating:
                is_fake = True
                confidence = 0.9
                summary = review.get("textualRating", "")
                break
            else:
                confidence = 0.7
                summary = review.get("textualRating", "")
    else:
        suggestions.append("Không tìm thấy xác thực từ Google Fact Check.")

    # Rule 1: Tin có dấu hiệu giật gân, giảm confidence
    content_to_check = " ".join([req.title, req.content])
    if has_fake_keywords(content_to_check):
        confidence -= 0.2
        suggestions.append("Có dấu hiệu giật gân/tin giả trong nội dung.")

    # Rule 2: Nguồn xác thực là báo lớn, tăng confidence
    if trusted_source(sources):
        confidence += 0.1
        suggestions.append("Nguồn xác thực uy tín: báo chính thống.")

    # Rule 3: Tin quá cũ, cảnh báo thời sự
    # (giả sử có trường date trong claim, bạn có thể bổ sung check ngày tại đây)

    # Đảm bảo confidence trong [0,1]
    confidence = max(0, min(1, confidence))

    return NewsCheckResponse(
        is_fake=confidence < 0.5,
        confidence=confidence,
        sources=sources,
        summary=summary,
        suggestions=suggestions
    )

@app.post("/api/check-fake-media", response_model=NewsCheckResponse)
async def check_fake_media(media: UploadFile = File(...)):
    file_bytes = await media.read()
    is_image = media.content_type.startswith("image/")
    if is_image and GOOGLE_VISION_API_KEY:
        encoded_image = base64.b64encode(file_bytes).decode("utf-8")
        vision_payload = {
            "requests": [{
                "image": {"content": encoded_image},
                "features": [{"type": "WEB_DETECTION", "maxResults": 5}]
            }]
        }
        res = requests.post(
            GOOGLE_VISION_API + f"?key={GOOGLE_VISION_API_KEY}",
            json=vision_payload
        )
        res_json = res.json()
        suggestions = []
        sources = []
        is_fake = False
        confidence = 0.5
        summary = "Không tìm thấy xác thực ảnh."
        try:
            web_detection = res_json["responses"][0]["webDetection"]
            if "bestGuessLabels" in web_detection:
                summary = ', '.join([lbl["label"] for lbl in web_detection["bestGuessLabels"]])
            if "webEntities" in web_detection:
                for entity in web_detection["webEntities"]:
                    if entity.get("description"):
                        suggestions.append(entity["description"])
            if "visuallySimilarImages" in web_detection:
                for img in web_detection["visuallySimilarImages"]:
                    sources.append(img["url"])
            if len(sources) > 3:
                confidence += 0.2
                suggestions.append("Ảnh có nhiều nguồn xác thực trên Internet.")
            # Nếu ảnh là meme, watermark lạ, confidence thấp (rule nâng cao)
            if summary and ("meme" in summary or "funny" in summary):
                confidence -= 0.2
                suggestions.append("Ảnh có thể là meme, không nên tin tuyệt đối.")
        except Exception as ex:
            suggestions.append("Không thể kiểm chứng ảnh.")
        confidence = max(0, min(1, confidence))
        return NewsCheckResponse(
            is_fake=confidence < 0.5,
            confidence=confidence,
            sources=sources,
            summary=summary,
            suggestions=suggestions
        )

    # Nếu là video hoặc file khác, hoặc chưa hỗ trợ
    return NewsCheckResponse(
        is_fake=False,
        confidence=0.5,
        sources=[],
        summary="Chức năng kiểm tra video sẽ được bổ sung sau.",
        suggestions=["Vui lòng kiểm tra thủ công hoặc gửi tới admin."]
    )
