"""
Productivity classification engine.
Classifies apps and websites as productive or unproductive using:
  1. Known blocklists (from default_blocklists)
  2. Hardcoded productive lists
  3. Browser detection (defer to tab URL)
  4. GPT-4o-mini AI fallback (cached permanently)
"""

import json
import ssl
import urllib.request
import urllib.error
import threading
from datetime import datetime
from typing import Optional

from src.data.productivity_cache import ProductivityCache, ProductivityCacheEntry


def _make_ssl_context() -> ssl.SSLContext:
    """Create an SSL context using certifi's CA bundle (macOS Python lacks system certs)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ── Known productive apps (macOS names) ──────────────────────────────
PRODUCTIVE_APPS = {
    # System
    "finder", "system preferences", "system settings", "activity monitor",
    "keychain access", "disk utility", "console", "terminal", "iterm2",
    "migration assistant", "font book", "screenshot", "digital color meter",

    # Development
    "code", "visual studio code", "xcode", "intellij idea", "pycharm",
    "webstorm", "goland", "clion", "datagrip", "rider", "rubymine",
    "android studio", "sublime text", "atom", "nova", "bbedit",
    "textedit", "tower", "fork", "sourcetree", "github desktop",
    "postman", "insomnia", "tableplus", "sequel pro", "dbeaver",
    "docker", "docker desktop", "kitty", "warp", "alacritty", "hyper",

    # Productivity
    "preview", "notes", "calendar", "mail", "reminders", "contacts",
    "pages", "numbers", "keynote", "microsoft word", "microsoft excel",
    "microsoft powerpoint", "microsoft outlook", "microsoft onenote",
    "notion", "obsidian", "bear", "craft", "ulysses", "ia writer",
    "todoist", "things", "omnifocus", "fantastical", "spark",

    # Design
    "figma", "sketch", "affinity designer", "affinity photo",
    "affinity publisher", "pixelmator pro", "adobe photoshop",
    "adobe illustrator", "adobe xd", "adobe indesign",

    # Communication (work-oriented)
    "zoom.us", "microsoft teams", "webex",

    # Utilities
    "1password", "bitwarden", "raycast", "alfred", "bartender",
    "cleanmymac", "appcleaner", "the unarchiver", "keka",
}

# ── Known productive websites ────────────────────────────────────────
PRODUCTIVE_WEBSITES = {
    # Dev
    "github.com", "gitlab.com", "bitbucket.org", "stackoverflow.com",
    "stackexchange.com", "docs.python.org", "developer.apple.com",
    "developer.mozilla.org", "npmjs.com", "pypi.org", "crates.io",
    "pkg.go.dev", "hub.docker.com", "vercel.com", "netlify.com",
    "heroku.com", "aws.amazon.com", "console.cloud.google.com",
    "portal.azure.com", "replit.com", "codepen.io", "codesandbox.io",
    "jsfiddle.net", "leetcode.com", "hackerrank.com",

    # Productivity
    "notion.so", "linear.app", "figma.com", "miro.com",
    "trello.com", "asana.com", "jira.atlassian.com", "clickup.com",
    "monday.com", "airtable.com", "coda.io", "roamresearch.com",

    # Docs / reference
    "docs.google.com", "drive.google.com", "sheets.google.com",
    "slides.google.com", "calendar.google.com", "mail.google.com",
    "outlook.live.com", "outlook.office.com",

    # Learning
    "coursera.org", "udemy.com", "edx.org", "khanacademy.org",
    "pluralsight.com", "egghead.io", "frontendmasters.com",
    "medium.com", "dev.to", "hashnode.dev", "freecodecamp.org",
    "w3schools.com", "geeksforgeeks.org", "tutorialspoint.com",

    # Design
    "dribbble.com", "behance.net", "canva.com",

    # AI
    "chat.openai.com", "chatgpt.com", "claude.ai", "bard.google.com",
    "huggingface.co", "kaggle.com",

    # Finance / work
    "stripe.com", "quickbooks.intuit.com",
}

# ── Known browsers (skip app classification, defer to tab URL) ───────
BROWSERS = {
    "safari", "google chrome", "firefox", "arc", "brave browser",
    "microsoft edge", "opera", "vivaldi", "orion", "chromium",
    "google chrome canary", "firefox developer edition", "firefox nightly",
    "tor browser", "waterfox", "floorp", "zen browser",
}


class ProductivityMonitor:
    """
    Classifies apps and websites as productive or unproductive.

    Classification tiers:
      1. Known unproductive — matches BLOCKED_APPS / BLOCKED_WEBSITES
      2. Known productive — matches hardcoded PRODUCTIVE sets
      3. Known browser — skip, extension handles tab URLs
      4. Unknown — GPT-4o-mini API call, cached permanently
    """

    def __init__(
        self,
        blocked_apps: set,
        blocked_websites: set,
        api_key: str,
        cache: ProductivityCache,
    ):
        self._blocked_apps = {a.lower() for a in blocked_apps}
        self._blocked_websites = {w.lower() for w in blocked_websites}
        self._api_key = api_key
        self._cache = cache
        self._pending_classifications: set = set()  # avoid duplicate AI calls
        self._pending_lock = threading.Lock()

    def update_api_key(self, key: str) -> None:
        self._api_key = key

    def is_browser(self, app_name: str) -> bool:
        """Check if the app is a known browser."""
        return app_name.lower() in BROWSERS

    def classify_app(self, app_name: str) -> bool:
        """
        Classify an app as unproductive.

        Returns:
            True if unproductive, False if productive or unknown-pending.
        """
        name_lower = app_name.lower()

        # Tier 1: known unproductive
        if name_lower in self._blocked_apps:
            return True

        # Tier 2: known productive
        if name_lower in PRODUCTIVE_APPS:
            return False

        # Tier 3: browser — skip (extension handles)
        if name_lower in BROWSERS:
            return False

        # Check cache
        cached = self._cache.get(name_lower)
        if cached is not None:
            return not cached.is_productive

        # Tier 4: AI classification (async, fail-open)
        self._classify_async(name_lower, "app")
        return False  # fail-open: assume productive until AI responds

    def classify_website(self, domain: str) -> bool:
        """
        Classify a website as unproductive.

        Returns:
            True if unproductive, False if productive or unknown-pending.
        """
        domain_lower = domain.lower()

        # Tier 1: known unproductive
        if domain_lower in self._blocked_websites:
            return True

        # Tier 2: known productive
        if domain_lower in PRODUCTIVE_WEBSITES:
            return False

        # Check cache
        cached = self._cache.get(domain_lower)
        if cached is not None:
            return not cached.is_productive

        # Tier 3: AI classification (async, fail-open)
        self._classify_async(domain_lower, "website")
        return False

    def _classify_async(self, name: str, kind: str) -> None:
        """Launch a background thread to classify via AI."""
        with self._pending_lock:
            if name in self._pending_classifications:
                return
            self._pending_classifications.add(name)

        thread = threading.Thread(
            target=self._do_ai_classification,
            args=(name, kind),
            daemon=True,
        )
        thread.start()

    def _do_ai_classification(self, name: str, kind: str) -> None:
        """Call GPT-4o-mini to classify an app/website. Runs in background thread."""
        try:
            if not self._api_key:
                return

            is_productive, confidence = self._call_llm(name, kind)

            entry = ProductivityCacheEntry(
                name=name,
                is_productive=is_productive,
                confidence=confidence,
                method="ai",
                classified_at=datetime.now().isoformat(),
            )
            self._cache.put(entry)
            print(f"[Productivity] AI classified {kind} '{name}': "
                  f"productive={is_productive} (confidence={confidence:.2f})")

        except Exception as e:
            print(f"[Productivity] AI classification error for '{name}': {e}")
            # Fail-open: cache as productive so we don't re-query on every tick
            entry = ProductivityCacheEntry(
                name=name,
                is_productive=True,
                confidence=0.0,
                method="error",
                classified_at=datetime.now().isoformat(),
            )
            self._cache.put(entry)

        finally:
            with self._pending_lock:
                self._pending_classifications.discard(name)

    def _call_llm(self, name: str, kind: str) -> tuple:
        """
        Call GPT-4o-mini to classify as productive/unproductive.

        Returns:
            Tuple of (is_productive: bool, confidence: float)
        """
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        entity = "macOS application" if kind == "app" else "website"
        system_prompt = (
            f"You are a productivity classifier. Given a {entity} name, determine "
            "if it is productive (used for work, study, development, or professional tasks) "
            "or unproductive (used for entertainment, social media, gaming, or procrastination). "
            "Respond with ONLY a JSON object: {\"is_productive\": true/false, \"confidence\": 0.0-1.0}"
        )

        user_prompt = f"{entity.capitalize()}: {name}\n\nIs this productive for work/study?"

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
        ctx = _make_ssl_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode())

        content = data["choices"][0]["message"]["content"].strip()

        try:
            result = json.loads(content)
            return result.get("is_productive", True), result.get("confidence", 0.5)
        except json.JSONDecodeError:
            # Fallback parsing
            if "false" in content.lower():
                return False, 0.6
            return True, 0.5
