import os
import re
import asyncio
import aiohttp
import hashlib
import json
import time
import random
import matplotlib.pyplot as plt
import win32com.client as win32
from typing import List
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from dotenv import load_dotenv

# =============================================================================
# CONFIGURATION & HARDCODED KEYS
# =============================================================================

# ⚠️ REPLACE THESE WITH YOUR ACTUAL KEYS
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
UNSPLASH_ACCESS_KEY = "5bOFghxGKSc0GXTbJeE54S2GucBLAgLus17Ptoa4sv4"

SAVE_FOLDER = os.path.join(os.getcwd(), "HeartPresentations")
CACHE_DIR = os.path.join(os.getcwd(), ".ppt_cache")
LOG_FILE = os.path.join(os.getcwd(), "heart_ppt.log")

os.makedirs(SAVE_FOLDER, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# =============================================================================
# LOGGING SETUP
# =============================================================================

import logging
from logging.handlers import RotatingFileHandler


def setup_logger():
    logger = logging.getLogger("HeartExpertPPT")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
        formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s')
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        logger.addHandler(ch)
        logger.addHandler(fh)
    return logger


logger = setup_logger()


# =============================================================================
# CACHE MANAGER
# =============================================================================

class CacheManager:
    def __init__(self, cache_dir: str = CACHE_DIR, ttl: int = 3600):
        self.cache_dir = cache_dir
        self.ttl = ttl

    def _get_key(self, key_str: str) -> str:
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, key_str: str):
        path = os.path.join(self.cache_dir, self._get_key(key_str))
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                if time.time() - data['timestamp'] < self.ttl:
                    return data['value']
        return None

    def set(self, key_str: str, value):
        path = os.path.join(self.cache_dir, self._get_key(key_str))
        with open(path, 'w') as f:
            json.dump({'value': value, 'timestamp': time.time()}, f)


# =============================================================================
# THEME ENGINE
# =============================================================================

class ThemeEngine:
    THEMES = {
        "tech": {"bg": RGBColor(10, 12, 20), "accent": RGBColor(0, 255, 200), "text": RGBColor(240, 240, 240),
                 "font": "Consolas"},
        "business": {"bg": RGBColor(255, 255, 255), "accent": RGBColor(0, 51, 102), "text": RGBColor(30, 30, 30),
                     "font": "Calibri"},
        "nature": {"bg": RGBColor(240, 248, 240), "accent": RGBColor(34, 139, 87), "text": RGBColor(20, 50, 20),
                   "font": "Verdana"},
        "dark_modern": {"bg": RGBColor(20, 20, 25), "accent": RGBColor(255, 100, 100), "text": RGBColor(220, 220, 220),
                        "font": "Segoe UI"},
        "academic": {"bg": RGBColor(250, 248, 240), "accent": RGBColor(139, 0, 0), "text": RGBColor(40, 40, 40),
                     "font": "Georgia"},
    }

    @staticmethod
    def get_theme(topic: str):
        t = topic.lower()
        if any(k in t for k in ["ai", "tech", "cyber", "code"]): return ThemeEngine.THEMES["tech"]
        if any(k in t for k in ["business", "finance", "market"]): return ThemeEngine.THEMES["business"]
        if any(k in t for k in ["nature", "bio", "health"]): return ThemeEngine.THEMES["nature"]
        if any(k in t for k in ["history", "law", "education"]): return ThemeEngine.THEMES["academic"]
        return ThemeEngine.THEMES["dark_modern"]


# =============================================================================
# RESEARCH ENGINE (Async)
# =============================================================================

class ResearchEngine:
    def __init__(self, api_key: str, cache: CacheManager):
        self.api_key = api_key
        self.cache = cache
        self.base_url = "https://serpapi.com/search.json"

    async def fetch_data(self, query: str):
        cache_key = f"serp:{query}"
        cached = self.cache.get(cache_key)
        if cached: return cached

        params = {"q": query, "api_key": self.api_key, "num": 5}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("organic_results", [])
                        self.cache.set(cache_key, results)
                        return results
        except Exception as e:
            logger.error(f"SerpAPI error: {e}")
        return []

    async def get_bullets(self, topic: str, section: str):
        query = f"{topic} {section} key facts statistics"
        results = await self.fetch_data(query)
        bullets = []
        for r in results:
            snippet = r.get("snippet", "")
            if snippet and len(snippet) > 20:
                clean = snippet.replace("\n", " ").strip()
                if clean not in bullets:
                    bullets.append(clean[:150])
        return bullets[:3]


# =============================================================================
# IMAGE PROVIDER (Async)
# =============================================================================

class ImageProvider:
    def __init__(self, key: str, cache: CacheManager, save_dir: str):
        self.key = key
        self.cache = cache
        self.save_dir = save_dir

    async def fetch(self, keyword: str, index: int):
        cache_key = f"img:{keyword}:{index}"
        cached_path = self.cache.get(cache_key)
        if cached_path and os.path.exists(cached_path):
            return cached_path

        url = "https://api.unsplash.com/photos/random"
        params = {"query": f"{keyword} professional cinematic", "orientation": "landscape"}
        headers = {"Authorization": f"Client-ID {self.key}"} if self.key else {}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        img_url = data["urls"]["regular"]
                        async with session.get(img_url) as img_resp:
                            if img_resp.status == 200:
                                filename = f"img_{index}_{hash(keyword)}.jpg"
                                path = os.path.join(self.save_dir, filename)
                                with open(path, 'wb') as f:
                                    f.write(await img_resp.read())
                                self.cache.set(cache_key, path)
                                return path
        except Exception as e:
            logger.warning(f"Image fetch failed: {e}")
        return None


# =============================================================================
# CHART ENGINE
# =============================================================================

class ChartEngine:
    @staticmethod
    def create_bar(topic: str, output_path: str, theme: dict):
        is_dark = theme['bg'].rgb < 50
        plt.style.use('dark_background') if is_dark else plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))

        accent_hex = '#{:02x}{:02x}{:02x}'.format(*theme['accent'].rgb)
        years = ["2023", "2024", "2025", "2026", "2027"]
        values = [random.randint(40, 60) + i * 10 for i in range(5)]

        ax.bar(years, values, color=accent_hex, alpha=0.9)
        ax.set_title(f"{topic} Growth Projection", color=theme['text'].rgb, fontsize=14)
        ax.tick_params(colors=theme['text'].rgb)

        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=theme['bg'].rgb)
        plt.close()


# =============================================================================
# LAYOUT ENGINE
# =============================================================================

class LayoutEngine:
    @staticmethod
    def add_text(shape, text: str, font: str, size: int, color: RGBColor, bold=False):
        tf = shape.text_frame
        tf.clear()
        tf.word_wrap = True
        p = tf.add_paragraph()
        p.text = text
        p.font.name = font
        p.font.size = Pt(size)
        p.font.color.rgb = color
        p.font.bold = bold
        p.alignment = PP_ALIGN.LEFT

    @staticmethod
    def add_title(slide, text: str, theme: dict):
        width = slide.part.slide_width
        box = slide.shapes.add_textbox(Inches(0.6), Inches(0.8), width - Inches(1.2), Inches(1.5))
        LayoutEngine.add_text(box, text, theme['font'], 40, theme['accent'], bold=True)


# =============================================================================
# ANIMATION ENGINE
# =============================================================================

class AnimationEngine:
    @staticmethod
    def apply_morph(path: str):
        try:
            ppt = win32.Dispatch("PowerPoint.Application")
            ppt.Visible = False
            pres = ppt.Presentations.Open(path, ReadOnly=False, WithWindow=False)
            for slide in pres.Slides:
                slide.SlideShowTransition.EntryEffect = 54  # Morph
                slide.SlideShowTransition.Duration = 1.2
            pres.Save()
            pres.Close()
            ppt.Quit()
            logger.info("Animations applied.")
        except Exception as e:
            logger.error(f"Animation failed: {e}")


# =============================================================================
# MAIN EXPERT CLASS (TRUE DYNAMIC VERSION)
# =============================================================================

class HeartExpertPPT:
    def __init__(self):
        if not SERPAPI_KEY or SERPAPI_KEY == "YOUR_SERPAPI_KEY_HERE":
            logger.warning("SERPAPI_KEY is missing. Research will be limited.")
        self.cache = CacheManager()
        self.researcher = ResearchEngine(SERPAPI_KEY, self.cache)
        self.image_provider = ImageProvider(UNSPLASH_ACCESS_KEY, self.cache, SAVE_FOLDER)

    async def _generate_dynamic_outline(self, topic: str) -> List[str]:
        """Uses SerpAPI to find how experts structure this specific topic."""
        logger.info(f"[AI] Thinking about the best structure for '{topic}'...")

        # We search for "Table of Contents" or "Syllabus" to see how humans structure this
        query = f"{topic} table of contents syllabus outline key chapters"
        results = await self.researcher.fetch_data(query)

        sections = ["Cover"]  # Always start with Cover

        # Extract unique, relevant headings from real-world sources
        seen = set()
        for r in results:
            snippet = r.get("snippet", "")
            # Split by common delimiters used in outlines
            parts = re.split(r'[,\n;•]', snippet)
            for part in parts:
                clean = part.strip().rstrip('.')
                if clean and len(clean) > 5 and len(clean) < 50 and clean.lower() not in seen:
                    # Filter out generic junk
                    if not any(junk in clean.lower() for junk in ["click here", "read more", "copyright"]):
                        sections.append(clean)
                        seen.add(clean.lower())
                if len(sections) >= 12:  # Cap at 12 content slides + Cover
                    break
            if len(sections) >= 12: break

        # Ensure we always have a Conclusion
        if "Conclusion" not in [s.capitalize() for s in sections]:
            sections.append("Conclusion & Key Takeaways")

        return sections

    async def _build_slide(self, topic, section, idx, prs, theme):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = theme['bg']
        LayoutEngine.add_title(slide, section, theme)

        if section == "Cover":
            img = await self.image_provider.fetch(topic, 0)
            if img:
                slide.shapes.add_picture(img, 0, 0, prs.slide_width, prs.slide_height)
                overlay = slide.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
                overlay.fill.solid();
                overlay.fill.fore_color.rgb = RGBColor(0, 0, 0);
                overlay.fill.transparency = 0.7;
                overlay.line.fill.background()
            LayoutEngine.add_text(
                slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(11), Inches(2)),
                topic.upper(), theme['font'], 60, RGBColor(255, 255, 255), bold=True
            )

        elif "Statistic" in section or "Growth" in section or "Market" in section:
            # Dynamic Chart Detection
            chart_path = os.path.join(SAVE_FOLDER, f"chart_{idx}.png")
            ChartEngine.create_bar(topic, chart_path, theme)
            slide.shapes.add_picture(chart_path, Inches(1.5), Inches(2), width=Inches(10))

        else:
            # Dynamic Content
            bullets = await self.researcher.get_bullets(topic, section)
            text_box = slide.shapes.add_textbox(Inches(0.6), Inches(1.8), Inches(7), Inches(5))
            tf = text_box.text_frame
            for b in bullets:
                p = tf.add_paragraph()
                p.text = f"• {b}"
                p.font.size = Pt(18)
                p.font.name = theme['font']
                p.font.color.rgb = theme['text']
                p.space_after = Pt(10)

            img = await self.image_provider.fetch(f"{topic} {section}", idx)
            if img:
                slide.shapes.add_picture(img, Inches(8.2), Inches(1.8), width=Inches(4.5))

    async def generate(self, topic: str) -> str:
        logger.info(f" [CREATOR] Starting truly dynamic generation for: {topic}")
        theme = ThemeEngine.get_theme(topic)

        # 1. THINK: Generate a custom outline for THIS specific topic
        sections = await self._generate_dynamic_outline(topic)
        logger.info(f" [AI] Created custom structure with {len(sections)} slides.")

        prs = Presentation()
        prs.slide_width = Inches(13.33)
        prs.slide_height = Inches(7.5)

        # 2. BUILD: Create slides based on the custom outline
        tasks = [self._build_slide(topic, sec, i, prs, theme) for i, sec in enumerate(sections)]
        await asyncio.gather(*tasks)

        filename = f"Heart_Dynamic_{topic.replace(' ', '_')}.pptx"
        path = os.path.join(SAVE_FOLDER, filename)
        prs.save(path)

        AnimationEngine.apply_morph(path)
        return path

expert_creator = HeartExpertPPT()