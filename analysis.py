"""MonkeyForge DEMO-Lite v0.6.2 -- axiom analysis.

Provides two analysis modes:
  1. Basic: heuristic local analysis using scoring metrics, pattern detection,
     structural coherence checks (no external API needed).
  2. DeepSeek: optional AI-powered analysis via DeepSeek API (requires config).

Results are returned directly (not persisted to disk in demo-lite mode).
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _basic_analysis(axiom_data: dict) -> dict:
    """Heuristic local analysis. No external dependencies."""
    metrics = axiom_data.get("metrics", {})
    axiom_text = axiom_data.get("axiom", "")
    coords = axiom_data.get("coordinates", {})

    # Score components
    sophia = metrics.get("sophia_score", 0)
    coherence = metrics.get("coherence", 0)
    novelty = metrics.get("novelty", 0)
    paradox = metrics.get("paradox_intensity", 0)
    alienness = metrics.get("alienness", 0)
    elegance = metrics.get("elegance", 0)

    # Structural analysis
    word_count = len(axiom_text.split())
    sentence_count = axiom_text.count(".") + axiom_text.count("!") + axiom_text.count("?")
    avg_word_len = (sum(len(w) for w in axiom_text.split()) / max(1, word_count))

    # Pattern detection
    has_math = any(c in axiom_text for c in "=+-*/^()[]{}")
    has_formal = any(kw in axiom_text.lower() for kw in
                     ["entails", "necessitates", "encoded", "formalized", "via", "mediated"])

    # Coordinate analysis
    coord_vals = list(coords.values()) if isinstance(coords, dict) else list(coords)
    coord_spread = max(coord_vals) - min(coord_vals) if coord_vals else 0
    coord_balance = 1.0 - coord_spread  # closer to 1 = more balanced

    # Overall quality heuristic
    quality = round(0.25 * sophia + 0.20 * coherence + 0.15 * novelty
                    + 0.10 * elegance + 0.10 * coord_balance
                    + 0.10 * (1 if has_formal else 0.3)
                    + 0.10 * min(1.0, word_count / 30), 4)

    # Category suggestion
    categories = []
    if paradox > 0.3:
        categories.append("paradoxical")
    if alienness > 0.5:
        categories.append("alien")
    if sophia > 0.618:
        categories.append("sophia-point")
    if has_math:
        categories.append("mathematical")
    if coord_balance > 0.8:
        categories.append("balanced")
    if novelty > 0.7:
        categories.append("novel")
    if not categories:
        categories.append("standard")

    return {
        "analysis_type": "basic",
        "status": "completed",
        "quality_score": quality,
        "categories": categories,
        "linguistic": {
            "word_count": word_count,
            "sentence_count": max(1, sentence_count),
            "avg_word_length": round(avg_word_len, 2),
            "has_mathematical_content": has_math,
            "has_formal_language": has_formal,
        },
        "coordinate_analysis": {
            "spread": round(coord_spread, 4),
            "balance": round(coord_balance, 4),
        },
        "score_breakdown": {
            "sophia_contribution": round(0.25 * sophia, 4),
            "coherence_contribution": round(0.20 * coherence, 4),
            "novelty_contribution": round(0.15 * novelty, 4),
            "elegance_contribution": round(0.10 * elegance, 4),
            "balance_contribution": round(0.10 * coord_balance, 4),
        },
        "recommendations": _recommendations(quality, categories, metrics),
        "summary": _summary(quality, categories, axiom_text),
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _recommendations(quality, categories, metrics) -> list:
    recs = []
    if quality < 0.4:
        recs.append("Consider providing a more specific seed to improve coherence.")
    if metrics.get("novelty", 0) < 0.3:
        recs.append("Low novelty detected. Try using 'force phase transition' for more creative outputs.")
    if metrics.get("elegance", 0) < 0.5:
        recs.append("Axiom text length is suboptimal. The generator favors ~160 character axioms.")
    if "paradoxical" in categories:
        recs.append("Paradoxical elements detected. This axiom may challenge conventional frameworks.")
    if "sophia-point" in categories:
        recs.append("This axiom crossed the Sophia threshold - it represents a phase transition in creative space.")
    if not recs:
        recs.append("Axiom scores are within normal range. No specific recommendations.")
    return recs


def _summary(quality, categories, text) -> str:
    cat_str = ", ".join(categories)
    preview = text[:100] + ("..." if len(text) > 100 else "")
    return (f"Quality score: {quality:.2f}. Categories: {cat_str}. "
            f"Axiom preview: {preview}")


def deepseek_analysis(axiom_data: dict, api_key: str | None = None,
                      base_url: str | None = None, model: str | None = None,
                      max_tokens: int | None = None) -> dict:
    """Optional DeepSeek AI analysis. Returns error info if not configured."""
    from core import load_config
    cfg = load_config()
    api_key = api_key or cfg.get("deepseek_api_key", "")
    base_url = (base_url or cfg.get("deepseek_base_url", "https://api.deepseek.com/v1")).rstrip("/")
    model = model or cfg.get("deepseek_model", "deepseek-chat")
    max_tokens = max_tokens or cfg.get("deepseek_max_tokens", 1024)

    if not api_key:
        return {
            "analysis_type": "deepseek",
            "status": "skipped",
            "error": "DeepSeek API key not configured. Set 'deepseek_api_key' in config.json.",
            "basic_fallback": _basic_analysis(axiom_data),
        }

    prompt = (
        "You are an expert in formal ontology, theoretical physics, and creative mathematics. "
        "Analyze the following generated axiom for:\n"
        "1. Logical coherence and internal consistency\n"
        "2. Novelty and originality\n"
        "3. Potential applicability to existing frameworks\n"
        "4. Suggested improvements or extensions\n"
        "5. Related known theorems or conjectures\n\n"
        f"Axiom: {axiom_data.get('axiom', '')}\n"
        f"Framework: {axiom_data.get('framework', 'N/A')}\n"
        f"Sophia Score: {axiom_data.get('metrics', {}).get('sophia_score', 'N/A')}\n"
        f"Coordinates: {axiom_data.get('coordinates', {})}\n"
        f"Equation Reference: {axiom_data.get('equation_ref', {})}\n\n"
        "Respond in JSON format with keys: coherence_assessment, novelty_assessment, "
        "applicability, improvements, related_work, overall_score (0-1)."
    )

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        tokens_used = result.get("usage", {}).get("total_tokens", 0)
        # Try to parse JSON from response
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"raw_response": content}

        return {
            "analysis_type": "deepseek",
            "status": "completed",
            "model": model,
            "tokens_used": tokens_used,
            "duration_ms": round((time.time() - start) * 1000),
            "result": parsed,
            "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except urllib.error.HTTPError as e:
        return {
            "analysis_type": "deepseek",
            "status": "failed",
            "error": f"HTTP {e.code}: {e.reason}",
            "basic_fallback": _basic_analysis(axiom_data),
        }
    except Exception as e:
        return {
            "analysis_type": "deepseek",
            "status": "failed",
            "error": str(e),
            "basic_fallback": _basic_analysis(axiom_data),
        }


def analyze(axiom_data: dict, mode: str = "basic", **kwargs) -> dict:
    """Unified analysis entry point. mode: 'basic' or 'deepseek'."""
    if mode == "deepseek":
        return deepseek_analysis(axiom_data, **kwargs)
    return _basic_analysis(axiom_data)
