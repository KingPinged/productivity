"""
AI-powered NSFW content detection engine.
Two-tier analysis: free OpenAI Moderation API + cheap GPT-4o-mini for ambiguous cases.
"""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Tuple

from src.data.nsfw_cache import NSFWCache, CacheEntry


@dataclass
class PageSignals:
    """Lightweight page signals extracted by the browser extension."""
    url: str
    domain: str
    title: str
    meta_description: str
    body_text: str


# Thresholds for two-tier detection
MODERATION_SAFE_THRESHOLD = 0.4
MODERATION_NSFW_THRESHOLD = 0.9


class NSFWDetector:
    """
    Two-tier AI NSFW detection engine.

    Tier 1: OpenAI Moderation API (FREE) - catches obvious NSFW content.
    Tier 2: GPT-4o-mini (~$0.00005/check) - for ambiguous cases only.

    Fail-open on API errors (don't block if API is down).
    """

    def __init__(self, api_key: str, cache: NSFWCache,
                 on_nsfw_detected: Optional[Callable[[str], None]] = None):
        self.api_key = api_key
        self.cache = cache
        self.on_nsfw_detected = on_nsfw_detected

    def update_api_key(self, key: str) -> None:
        """Update the OpenAI API key."""
        self.api_key = key

    def _has_page_content(self, signals: PageSignals) -> bool:
        """Check if signals contain actual page content beyond just a domain/URL."""
        return bool(signals.title or signals.meta_description or signals.body_text)

    def check_content_sync(self, signals: PageSignals) -> dict:
        """
        Synchronous content check. Called from HTTP handler thread.

        Returns:
            Dict with keys: is_nsfw, confidence, cached, method
        """
        domain = signals.domain.lower()
        print(f"[NSFW] check_content_sync called for domain={domain}")

        # Check cache first
        cached = self.cache.get(domain)
        if cached is not None:
            print(f"[NSFW] Cache hit for {domain}: is_nsfw={cached.is_nsfw}")
            return {
                'is_nsfw': cached.is_nsfw,
                'confidence': cached.confidence,
                'cached': True,
                'method': cached.method,
            }

        # No API key = can't check
        if not self.api_key:
            print(f"[NSFW] No API key set - cannot check {domain}")
            return {
                'is_nsfw': False,
                'confidence': 0.0,
                'cached': False,
                'method': 'no_api_key',
            }

        # If we only have a domain (no page content), skip Moderation API and
        # go straight to GPT-4o-mini. The Moderation API is a text content
        # moderator — it can't classify domains by name. A URL string like
        # "https://pornsite.com" scores low because the TEXT isn't explicit.
        if not self._has_page_content(signals):
            print(f"[NSFW] Domain-only check for {domain}, skipping moderation -> straight to LLM")
            return self._check_domain_only(signals)

        # Has page content — use two-tier approach
        # Build text to analyze
        text = self._build_analysis_text(signals)
        print(f"[NSFW] Tier 1: Calling Moderation API for {domain} ({len(text)} chars)")

        # Tier 1: Moderation API (free)
        try:
            score = self._call_moderation_api(text)
        except Exception as e:
            print(f"[NSFW] Moderation API error for {domain}: {e}")
            # Fall through to LLM instead of failing open
            print(f"[NSFW] Falling through to LLM for {domain}")
            return self._check_domain_only(signals)

        print(f"[NSFW] Tier 1 score for {domain}: {score:.4f}")

        # Evaluate Tier 1 result
        if score >= MODERATION_NSFW_THRESHOLD:
            # Clearly NSFW - cache, notify, and return
            print(f"[NSFW] {domain} -> NSFW (score {score:.4f} >= {MODERATION_NSFW_THRESHOLD})")
            self._cache_result(domain, True, score, 'moderation')
            if self.on_nsfw_detected:
                self.on_nsfw_detected(domain)
            return {
                'is_nsfw': True,
                'confidence': score,
                'cached': False,
                'method': 'moderation',
            }

        # Score below NSFW threshold — always verify with LLM
        # The moderation API is unreliable for domain/URL classification
        print(f"[NSFW] {domain} -> moderation score {score:.4f}, verifying with LLM...")
        try:
            is_nsfw, confidence = self._call_llm_verification(signals, score)
        except Exception as e:
            print(f"[NSFW] LLM verification error for {domain}: {e}")
            # Fail open on LLM errors
            self._cache_result(domain, False, score, 'error')
            return {
                'is_nsfw': False,
                'confidence': score,
                'cached': False,
                'method': 'error',
            }

        print(f"[NSFW] Tier 2 result for {domain}: is_nsfw={is_nsfw}, confidence={confidence:.4f}")
        self._cache_result(domain, is_nsfw, confidence, 'llm')
        if is_nsfw and self.on_nsfw_detected:
            self.on_nsfw_detected(domain)

        return {
            'is_nsfw': is_nsfw,
            'confidence': confidence,
            'cached': False,
            'method': 'llm',
        }

    def _check_domain_only(self, signals: PageSignals) -> dict:
        """Direct LLM check for domain-only signals (no page content)."""
        domain = signals.domain.lower()
        try:
            is_nsfw, confidence = self._call_llm_domain_check(domain)
        except Exception as e:
            print(f"[NSFW] LLM domain check error for {domain}: {e}")
            return {
                'is_nsfw': False,
                'confidence': 0.0,
                'cached': False,
                'method': 'error',
            }

        print(f"[NSFW] LLM domain check for {domain}: is_nsfw={is_nsfw}, confidence={confidence:.4f}")
        self._cache_result(domain, is_nsfw, confidence, 'llm_domain')
        if is_nsfw and self.on_nsfw_detected:
            self.on_nsfw_detected(domain)

        return {
            'is_nsfw': is_nsfw,
            'confidence': confidence,
            'cached': False,
            'method': 'llm_domain',
        }

    def _build_analysis_text(self, signals: PageSignals) -> str:
        """Build a compact text representation for analysis."""
        parts = []
        if signals.title:
            parts.append(f"Title: {signals.title}")
        if signals.meta_description:
            parts.append(f"Description: {signals.meta_description}")
        if signals.url:
            parts.append(f"URL: {signals.url}")
        if signals.body_text:
            # Limit body text to avoid token waste
            body = signals.body_text[:500]
            parts.append(f"Content: {body}")
        return "\n".join(parts)

    def _call_moderation_api(self, text: str) -> float:
        """
        Call OpenAI Moderation API (free endpoint).

        Returns:
            Maximum category score (0.0 to 1.0). Higher = more likely NSFW.
        """
        url = "https://api.openai.com/v1/moderations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = json.dumps({"input": text}).encode()

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        # Extract the maximum sexual/nsfw-related score
        results = data.get("results", [{}])
        if not results:
            return 0.0

        scores = results[0].get("category_scores", {})
        # Focus on sexual content categories
        nsfw_score = max(
            scores.get("sexual", 0.0),
            scores.get("sexual/minors", 0.0),
        )
        return nsfw_score

    def _call_llm_domain_check(self, domain: str) -> Tuple[bool, float]:
        """
        Call GPT-4o-mini to classify a domain name as NSFW or safe.
        Used when we only have a domain (DNS monitor path) and no page content.
        Very cheap — ~10 tokens input.
        """
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": (
                    "You classify website domains as NSFW (adult/pornographic) or safe. "
                    "Respond with ONLY a JSON object: {\"nsfw\": true/false}\n"
                    "NSFW = site's primary purpose is pornographic/adult sexual content.\n"
                    "NOT NSFW = health, medical, education, news, tech, shopping, social media, art, dating apps, lingerie stores."
                )},
                {"role": "user", "content": domain},
            ],
            "max_tokens": 20,
            "temperature": 0,
        }).encode()

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        content = data["choices"][0]["message"]["content"].strip()

        try:
            result = json.loads(content)
            is_nsfw = result.get("nsfw", False)
            return is_nsfw, 0.95 if is_nsfw else 0.95
        except json.JSONDecodeError:
            content_lower = content.lower()
            if "true" in content_lower:
                return True, 0.8
            return False, 0.8

    def _call_llm_verification(self, signals: PageSignals, moderation_score: float) -> Tuple[bool, float]:
        """
        Call GPT-4o-mini to verify ambiguous cases.

        Returns:
            Tuple of (is_nsfw, confidence)
        """
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        system_prompt = (
            "You are a content classifier. Determine if a website is an adult/pornographic site. "
            "Respond with ONLY a JSON object: {\"is_nsfw\": true/false, \"confidence\": 0.0-1.0}\n"
            "Health, medical, educational, and art sites are NOT nsfw. "
            "Only classify as nsfw if the site's primary purpose is pornographic content."
        )

        user_prompt = (
            f"Domain: {signals.domain}\n"
            f"Title: {signals.title}\n"
            f"Description: {signals.meta_description}\n"
            f"URL: {signals.url}\n"
            f"Body excerpt: {signals.body_text[:300]}\n"
            f"Moderation API sexual score: {moderation_score:.3f}\n"
            "\nIs this an adult/pornographic website?"
        )

        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 50,
            "temperature": 0,
        }).encode()

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        try:
            result = json.loads(content)
            return result.get("is_nsfw", False), result.get("confidence", 0.5)
        except json.JSONDecodeError:
            # If LLM didn't return valid JSON, check for keywords
            content_lower = content.lower()
            if "true" in content_lower or "nsfw" in content_lower:
                return True, 0.7
            return False, 0.5

    def _cache_result(self, domain: str, is_nsfw: bool, confidence: float, method: str) -> None:
        """Cache a detection result."""
        entry = CacheEntry(
            domain=domain,
            is_nsfw=is_nsfw,
            confidence=confidence,
            checked_at=datetime.now().isoformat(),
            method=method,
        )
        self.cache.put(entry)
