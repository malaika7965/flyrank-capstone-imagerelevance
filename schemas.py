from pydantic import BaseModel, Field
from typing import List


class ImageMetadata(BaseModel):
    """
    Yeh schema har image ke liye vision AI se aane wala data define karta hai.
    Agar AI ka jawaab is shape mein fit nahi hota, validation fail ho jayegi
    aur humein pata chal jayega ke AI ne kuch ajeeb diya hai.
    """
    subject: str = Field(description="Main cheez jo image mein hai, jaise 'red fox'")
    category: str = Field(description="Broad category, jaise 'animal', 'landscape'")
    attributes: List[str] = Field(description="Chhote descriptive words, jaise ['orange fur', 'wild']")
    caption: str = Field(description="Ek line mein image ka description")
    confidence: float = Field(ge=0.0, le=1.0, description="AI ka apna confidence score, 0 se 1 ke beech")


class Post(BaseModel):
    """Blog post jise hum image match karwayenge"""
    id: str
    title: str
    content: str


class MatchResult(BaseModel):
    """Mismatch guard ka final jawaab"""
    post_id: str
    matched: bool
    image_id: str | None = None
    similarity_score: float | None = None
    reason: str