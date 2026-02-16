// Productivity Timer - Website Blocker Extension
// Background script that blocks websites during focus sessions
// Syncs with the desktop app via local HTTP server

// Server configuration
const SERVER_URL = 'http://127.0.0.1:52525';
const SYNC_INTERVAL = 2000; // Poll every 2 seconds

// Default blocked sites (fallback if server is not available)
const DEFAULT_BLOCKED_SITES = [
  "facebook.com", "twitter.com", "x.com", "instagram.com", "tiktok.com",
  "reddit.com", "youtube.com", "twitch.tv", "netflix.com", "discord.com"
];

// State
let isBlocking = false;
let blockedSites = [];
let alwaysBlockedSites = [];  // Adult sites - always blocked regardless of session
let whitelistedUrls = [];  // URLs that are allowed even if domain is blocked
let blockCount = 0;
let appConnected = false;
let syncInterval = null;
let isPunishmentLocked = false;  // When true, ALL sites are blocked (network disabled)

// Usage tracking state
let currentDomain = null;
let trackingStartTime = null;
let usageReportQueue = [];  // Queue for offline reports

// AI NSFW detection state
let aiCheckedDomains = new Set();  // Domains already checked by AI backend
let aiCheckInProgress = new Set();  // Domains currently being checked (prevent duplicates)

// Initialize
async function initialize() {
  // Load saved state
  const data = await browser.storage.local.get(['blockedSites', 'alwaysBlockedSites', 'whitelistedUrls', 'blockCount', 'punishmentState', 'aiCheckedDomains']);
  blockedSites = data.blockedSites || DEFAULT_BLOCKED_SITES;
  alwaysBlockedSites = data.alwaysBlockedSites || [];
  whitelistedUrls = data.whitelistedUrls || [];
  blockCount = data.blockCount || 0;

  // Load AI checked domains from storage
  if (data.aiCheckedDomains && Array.isArray(data.aiCheckedDomains)) {
    aiCheckedDomains = new Set(data.aiCheckedDomains);
    console.log('AI checked domains loaded:', aiCheckedDomains.size);
  }

  // Check for active punishment on startup
  if (data.punishmentState && data.punishmentState.is_locked) {
    isPunishmentLocked = true;
    startPunishmentBlocking();
    console.log("Punishment lock active on startup - blocking all traffic");
  }

  // Start syncing with desktop app
  startSync();

  // Always start the always-blocked listener (for adult content)
  startAlwaysBlocking();

  updateIcon();
}

// Start syncing with desktop app
function startSync() {
  // Initial sync
  syncWithApp();

  // Set up periodic sync
  if (syncInterval) {
    clearInterval(syncInterval);
  }
  syncInterval = setInterval(syncWithApp, SYNC_INTERVAL);
}

// Sync state with desktop app
async function syncWithApp() {
  try {
    // Try to get status from desktop app
    const response = await fetch(`${SERVER_URL}/status`, {
      method: 'GET',
      cache: 'no-cache'
    });

    if (response.ok) {
      const status = await response.json();
      appConnected = true;

      // Update blocking state based on app
      const wasBlocking = isBlocking;
      isBlocking = status.isBlocking;

      if (isBlocking && !wasBlocking) {
        // App started blocking - fetch sites and whitelist, then start
        await fetchBlockedSites();
        startBlocking();
      } else if (!isBlocking && wasBlocking) {
        // App stopped blocking
        stopBlocking();
      }

      updateIcon();
    } else {
      appConnected = false;
    }

    // Also check punishment status
    await checkPunishmentStatus();

    // Sync AI NSFW cache
    await syncAICache();

  } catch (error) {
    // Server not available - app might not be running
    appConnected = false;

    // If we were blocking based on app, stop
    if (isBlocking) {
      isBlocking = false;
      stopBlocking();
      updateIcon();
    }

    // Check cached punishment state when server is unreachable
    await checkCachedPunishmentStatus();
  }
}

// Check punishment status from server
async function checkPunishmentStatus() {
  try {
    const response = await fetch(`${SERVER_URL}/punishment-status`, {
      method: 'GET',
      cache: 'no-cache'
    });

    if (response.ok) {
      const status = await response.json();
      await browser.storage.local.set({ punishmentState: status });

      const wasLocked = isPunishmentLocked;
      isPunishmentLocked = status.is_locked;

      if (isPunishmentLocked && !wasLocked) {
        startPunishmentBlocking();
      } else if (!isPunishmentLocked && wasLocked) {
        stopPunishmentBlocking();
      }
    }
  } catch (error) {
    // Server unreachable, use cached state
    await checkCachedPunishmentStatus();
  }
}

// Check cached punishment state (used when server is unreachable)
async function checkCachedPunishmentStatus() {
  try {
    const data = await browser.storage.local.get(['punishmentState']);
    if (data.punishmentState) {
      const status = data.punishmentState;
      const wasLocked = isPunishmentLocked;

      // Check if lock is still active based on time
      if (status.is_locked && status.lock_time_remaining > 0) {
        isPunishmentLocked = true;
        if (!wasLocked) {
          startPunishmentBlocking();
        }
      } else {
        isPunishmentLocked = false;
        if (wasLocked) {
          stopPunishmentBlocking();
        }
      }
    }
  } catch (error) {
    console.log('Could not check cached punishment status');
  }
}

// Fetch blocked sites and whitelist from desktop app
async function fetchBlockedSites() {
  try {
    const response = await fetch(`${SERVER_URL}/sites`, {
      method: 'GET',
      cache: 'no-cache'
    });

    if (response.ok) {
      const data = await response.json();

      // Update blocked sites
      if (data.sites && data.sites.length > 0) {
        blockedSites = data.sites;
        await browser.storage.local.set({ blockedSites });
      }

      // Update always-blocked sites (adult content)
      if (data.alwaysBlocked && data.alwaysBlocked.length > 0) {
        alwaysBlockedSites = data.alwaysBlocked;
        await browser.storage.local.set({ alwaysBlockedSites });
        console.log('Always-blocked sites loaded:', alwaysBlockedSites.length, 'sites');
      }

      // Update whitelist
      if (data.whitelist) {
        whitelistedUrls = data.whitelist;
        await browser.storage.local.set({ whitelistedUrls });
        console.log('Whitelist loaded:', whitelistedUrls);
      }
    }
  } catch (error) {
    console.log('Could not fetch blocked sites from app');
  }
}

// Check if a URL is whitelisted
function isWhitelisted(url) {
  if (!whitelistedUrls || whitelistedUrls.length === 0) {
    return false;
  }

  // Normalize the URL for comparison
  const normalizedUrl = url.toLowerCase();

  for (const whitelistEntry of whitelistedUrls) {
    const normalizedWhitelist = whitelistEntry.toLowerCase();

    // Check exact match
    if (normalizedUrl === normalizedWhitelist) {
      return true;
    }

    // Check if URL starts with whitelist entry (for path matching)
    if (normalizedUrl.startsWith(normalizedWhitelist)) {
      return true;
    }

    // Check without protocol
    const urlWithoutProtocol = normalizedUrl.replace(/^https?:\/\//, '');
    const whitelistWithoutProtocol = normalizedWhitelist.replace(/^https?:\/\//, '');

    if (urlWithoutProtocol === whitelistWithoutProtocol) {
      return true;
    }

    if (urlWithoutProtocol.startsWith(whitelistWithoutProtocol)) {
      return true;
    }

    // Handle www variants
    const urlNoWww = urlWithoutProtocol.replace(/^www\./, '');
    const whitelistNoWww = whitelistWithoutProtocol.replace(/^www\./, '');

    if (urlNoWww === whitelistNoWww || urlNoWww.startsWith(whitelistNoWww)) {
      return true;
    }
  }

  return false;
}

// Build regex pattern for a list of sites
function buildPatternForSites(sites) {
  if (!sites || sites.length === 0) {
    return null;
  }

  const escaped = sites.map(site => {
    // Remove protocol and www if present
    site = site.replace(/^(https?:\/\/)?(www\.)?/, '');
    // Escape special regex chars
    return site.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  });

  return new RegExp(`^https?://(www\\.)?(${escaped.join('|')})`, 'i');
}

// Build regex pattern for session-blocked sites
function buildBlockPattern() {
  return buildPatternForSites(blockedSites);
}

// Build regex pattern for always-blocked sites (adult content)
function buildAlwaysBlockPattern() {
  return buildPatternForSites(alwaysBlockedSites);
}

// Request listener for session-based blocking
function blockRequest(details) {
  const url = details.url;

  // First check if URL is whitelisted
  if (isWhitelisted(url)) {
    console.log('Whitelisted URL allowed:', url);
    return {};  // Allow the request
  }

  const pattern = buildBlockPattern();

  if (pattern && pattern.test(url)) {
    blockCount++;
    browser.storage.local.set({ blockCount });

    console.log('Blocked URL:', url);

    // Redirect to blocked page
    return {
      redirectUrl: browser.runtime.getURL('blocked.html') + '?url=' + encodeURIComponent(url)
    };
  }

  return {};
}

// Report adult site strike to desktop app
async function reportAdultStrike() {
  try {
    const response = await fetch(`${SERVER_URL}/adult-strike`, {
      method: 'POST',
      cache: 'no-cache'
    });
    if (response.ok) {
      const data = await response.json();
      // Store punishment state for block page to access
      await browser.storage.local.set({ punishmentState: data });
      console.log('Adult strike reported:', data);
    }
  } catch (error) {
    console.log('Could not report adult strike:', error);
  }
}

// Request listener for always-blocked sites (adult content) - ALWAYS ACTIVE
function alwaysBlockRequest(details) {
  const url = details.url;

  const pattern = buildAlwaysBlockPattern();

  if (pattern && pattern.test(url)) {
    blockCount++;
    browser.storage.local.set({ blockCount });

    console.log('Always-blocked URL:', url);

    // Report strike to desktop app (fire and forget)
    reportAdultStrike();

    // Redirect to blocked page with adult flag
    return {
      redirectUrl: browser.runtime.getURL('blocked.html') + '?url=' + encodeURIComponent(url) + '&adult=1'
    };
  }

  return {};
}

// Start always-blocking (for adult content) - runs on extension load
function startAlwaysBlocking() {
  // Remove existing listener if any
  if (browser.webRequest.onBeforeRequest.hasListener(alwaysBlockRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(alwaysBlockRequest);
  }

  // Add listener - this is ALWAYS active
  browser.webRequest.onBeforeRequest.addListener(
    alwaysBlockRequest,
    { urls: ["<all_urls>"], types: ["main_frame"] },
    ["blocking"]
  );

  console.log("Productivity Timer: Always-blocking started (adult content)");
  console.log("Always-blocked sites:", alwaysBlockedSites.length);
}

// Start session-based blocking
function startBlocking() {
  // Remove existing listener if any
  if (browser.webRequest.onBeforeRequest.hasListener(blockRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(blockRequest);
  }

  // Add listener
  browser.webRequest.onBeforeRequest.addListener(
    blockRequest,
    { urls: ["<all_urls>"], types: ["main_frame"] },
    ["blocking"]
  );

  console.log("Productivity Timer: Session blocking started");
  console.log("Whitelisted URLs:", whitelistedUrls);
}

// Stop blocking
function stopBlocking() {
  if (browser.webRequest.onBeforeRequest.hasListener(blockRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(blockRequest);
  }

  console.log("Productivity Timer: Blocking stopped");
}

// Request listener for punishment mode - blocks ALL websites
function punishmentBlockRequest(details) {
  const url = details.url;

  // Allow extension pages
  if (url.startsWith(browser.runtime.getURL(''))) {
    return {};
  }

  // Allow localhost (for our status server, though it won't work with network disabled)
  if (url.includes('127.0.0.1') || url.includes('localhost')) {
    return {};
  }

  console.log('Punishment block - ALL traffic blocked:', url);

  // Redirect to blocked page with punishment flag
  return {
    redirectUrl: browser.runtime.getURL('blocked.html') + '?url=' + encodeURIComponent(url) + '&adult=1&punishment=1'
  };
}

// Start punishment blocking - blocks ALL internet traffic
function startPunishmentBlocking() {
  // Remove existing listener if any
  if (browser.webRequest.onBeforeRequest.hasListener(punishmentBlockRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(punishmentBlockRequest);
  }

  // Add listener for ALL URLs
  browser.webRequest.onBeforeRequest.addListener(
    punishmentBlockRequest,
    { urls: ["<all_urls>"], types: ["main_frame"] },
    ["blocking"]
  );

  console.log("Productivity Timer: PUNISHMENT BLOCKING ACTIVE - All traffic blocked");
}

// Stop punishment blocking
function stopPunishmentBlocking() {
  if (browser.webRequest.onBeforeRequest.hasListener(punishmentBlockRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(punishmentBlockRequest);
  }

  console.log("Productivity Timer: Punishment blocking stopped");
}

// Update extension icon based on state
function updateIcon() {
  const iconPath = isBlocking ? {
    16: "icons/icon16-active.png",
    48: "icons/icon48-active.png",
    128: "icons/icon128-active.png"
  } : {
    16: "icons/icon16.png",
    48: "icons/icon48.png",
    128: "icons/icon128.png"
  };

  browser.browserAction.setIcon({ path: iconPath }).catch(() => {
    // Fallback if active icons don't exist
    browser.browserAction.setIcon({ path: {
      16: "icons/icon16.png",
      48: "icons/icon48.png",
      128: "icons/icon128.png"
    }});
  });

  // Update badge
  if (isBlocking) {
    browser.browserAction.setBadgeText({ text: "ON" });
    browser.browserAction.setBadgeBackgroundColor({ color: "#e74c3c" });
  } else if (appConnected) {
    browser.browserAction.setBadgeText({ text: "" });
  } else {
    browser.browserAction.setBadgeText({ text: "!" });
    browser.browserAction.setBadgeBackgroundColor({ color: "#f39c12" });
  }
}

// Listen for messages from popup
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getStatus') {
    sendResponse({
      isBlocking,
      blockedSites,
      alwaysBlockedSites,
      whitelistedUrls,
      blockCount,
      appConnected,
      isPunishmentLocked
    });
  } else if (message.action === 'manualToggle') {
    // Manual toggle only works if app is not connected
    if (!appConnected) {
      isBlocking = !isBlocking;
      if (isBlocking) {
        startBlocking();
      } else {
        stopBlocking();
      }
      browser.storage.local.set({ isBlocking });
      updateIcon();
      sendResponse({ isBlocking });
    } else {
      sendResponse({ error: 'Controlled by desktop app' });
    }
  } else if (message.action === 'resetCount') {
    blockCount = 0;
    browser.storage.local.set({ blockCount });
    sendResponse({ success: true });
  } else if (message.action === 'forceSync') {
    syncWithApp().then(() => {
      sendResponse({ success: true, isBlocking, appConnected });
    });
    return true; // Keep channel open for async response
  }

  return true;
});

// ============================================
// AI NSFW Detection Functions
// ============================================

// Sync checked domains from backend cache
async function syncAICache() {
  try {
    const response = await fetch(`${SERVER_URL}/nsfw-cache`, {
      method: 'GET',
      cache: 'no-cache'
    });

    if (response.ok) {
      const data = await response.json();
      if (data.checked_domains && Array.isArray(data.checked_domains)) {
        aiCheckedDomains = new Set(data.checked_domains);
        await browser.storage.local.set({ aiCheckedDomains: Array.from(aiCheckedDomains) });
      }
    }
  } catch (error) {
    // Server unreachable - use cached set
  }
}

// Check if a domain should be sent for AI analysis
function shouldCheckDomain(domain) {
  if (!domain) return false;

  // Skip if already checked by AI
  if (aiCheckedDomains.has(domain)) {
    console.log(`[AI NSFW] Skipping ${domain}: already checked`);
    return false;
  }

  // Skip if check already in progress
  if (aiCheckInProgress.has(domain)) return false;

  // Skip internal/browser pages
  if (domain === '127.0.0.1' || domain === 'localhost') return false;
  if (domain.endsWith('.local')) return false;

  // Skip if in static always-blocked list (already handled)
  const pattern = buildAlwaysBlockPattern();
  if (pattern && pattern.test('https://' + domain)) {
    console.log(`[AI NSFW] Skipping ${domain}: in static blocklist`);
    return false;
  }

  // Skip if in session blocked list
  const sessionPattern = buildBlockPattern();
  if (sessionPattern && sessionPattern.test('https://' + domain)) {
    console.log(`[AI NSFW] Skipping ${domain}: in session blocklist`);
    return false;
  }

  return true;
}

// Extract page signals from a tab
async function extractPageSignals(tabId) {
  try {
    const results = await browser.tabs.executeScript(tabId, {
      code: `
        (function() {
          const meta = document.querySelector('meta[name="description"]');
          const metaDesc = meta ? meta.getAttribute('content') || '' : '';
          const bodyText = (document.body ? document.body.innerText || '' : '').substring(0, 500);
          return {
            title: document.title || '',
            meta_description: metaDesc,
            body_text: bodyText
          };
        })();
      `
    });
    if (results && results[0]) {
      console.log(`[AI NSFW] Extracted signals: title="${results[0].title}", body=${results[0].body_text.length} chars`);
      return results[0];
    }
    console.log('[AI NSFW] executeScript returned empty results');
    return null;
  } catch (error) {
    console.log('[AI NSFW] executeScript failed:', error.message || error);
    return null;
  }
}

// Send page signals to backend for AI NSFW check
async function checkPageContent(tabId, url, domain) {
  // If not connected yet, try a quick ping before giving up
  if (!appConnected) {
    try {
      const ping = await fetch(`${SERVER_URL}/ping`, { method: 'GET', cache: 'no-cache' });
      if (ping.ok) {
        appConnected = true;
        console.log('[AI NSFW] App connected via on-demand ping');
      }
    } catch (e) {
      // genuinely not running
    }
  }
  if (!appConnected) {
    console.log(`[AI NSFW] Skipping ${domain}: app not connected`);
    return;
  }
  if (!shouldCheckDomain(domain)) return;

  console.log(`[AI NSFW] Checking domain: ${domain}`);
  aiCheckInProgress.add(domain);

  try {
    // Extract page content (best-effort - proceed even if this fails)
    const signals = await extractPageSignals(tabId);
    if (!signals) {
      console.log(`[AI NSFW] No signals extracted for ${domain}, sending domain/URL only`);
    }

    const payload = {
      url: url,
      domain: domain,
      title: signals ? signals.title : '',
      meta_description: signals ? signals.meta_description : '',
      body_text: signals ? signals.body_text : ''
    };

    console.log(`[AI NSFW] Sending to backend: ${domain}`);
    const response = await fetch(`${SERVER_URL}/check-content`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-cache'
    });

    if (response.ok) {
      const result = await response.json();
      console.log(`[AI NSFW] Result for ${domain}: is_nsfw=${result.is_nsfw}, confidence=${result.confidence}, method=${result.method}, cached=${result.cached}`);

      // Don't cache results from 'disabled' or 'no_api_key' - those should be retried after key is set
      if (result.method !== 'disabled' && result.method !== 'no_api_key') {
        aiCheckedDomains.add(domain);
        await browser.storage.local.set({ aiCheckedDomains: Array.from(aiCheckedDomains) });
      } else {
        console.log(`[AI NSFW] Not caching ${domain} (method=${result.method}) - will retry when API key is set`);
      }

      if (result.is_nsfw) {
        console.log(`[AI NSFW] BLOCKED: ${domain} (confidence: ${result.confidence}, method: ${result.method})`);

        // Add to always-blocked list locally
        if (!alwaysBlockedSites.includes(domain)) {
          alwaysBlockedSites.push(domain);
          await browser.storage.local.set({ alwaysBlockedSites });
        }

        // Redirect the tab to blocked page
        browser.tabs.update(tabId, {
          url: browser.runtime.getURL('blocked.html') + '?url=' + encodeURIComponent(url) + '&adult=1&ai=1'
        });

        // Report adult strike
        reportAdultStrike();
      }
    } else {
      console.log(`[AI NSFW] Backend returned HTTP ${response.status} for ${domain}`);
    }
  } catch (error) {
    console.log(`[AI NSFW] Check failed for ${domain}:`, error.message || error);
  } finally {
    aiCheckInProgress.delete(domain);
  }
}

// ============================================
// Usage Tracking Functions
// ============================================

// Extract domain from URL
function extractDomain(url) {
  try {
    const urlObj = new URL(url);
    // Remove www. prefix for cleaner tracking
    return urlObj.hostname.replace(/^www\./, '').toLowerCase();
  } catch (e) {
    return null;
  }
}

// Report website usage to desktop app
async function reportWebsiteUsage(domain, seconds) {
  if (!domain || seconds <= 0) return;

  const report = { domain, seconds };

  try {
    const response = await fetch(`${SERVER_URL}/usage/website`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
      cache: 'no-cache'
    });

    if (response.ok) {
      console.log(`Usage reported: ${domain} - ${seconds}s`);
      // Try to send any queued reports
      flushUsageQueue();
    } else {
      // Queue for later
      usageReportQueue.push(report);
    }
  } catch (error) {
    // Server unavailable - queue for later
    usageReportQueue.push(report);
    console.log(`Usage queued (offline): ${domain} - ${seconds}s`);
  }
}

// Flush queued usage reports
async function flushUsageQueue() {
  if (usageReportQueue.length === 0) return;

  const queue = [...usageReportQueue];
  usageReportQueue = [];

  for (const report of queue) {
    try {
      const response = await fetch(`${SERVER_URL}/usage/website`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(report),
        cache: 'no-cache'
      });

      if (!response.ok) {
        // Re-queue if failed
        usageReportQueue.push(report);
      }
    } catch (error) {
      // Re-queue if error
      usageReportQueue.push(report);
      break; // Stop trying if server is down
    }
  }
}

// Track the currently active tab
async function trackActiveTab() {
  try {
    const tabs = await browser.tabs.query({ active: true, currentWindow: true });

    if (tabs.length === 0 || !tabs[0].url) {
      // No active tab or no URL - report current and clear
      if (currentDomain && trackingStartTime) {
        const seconds = Math.floor((Date.now() - trackingStartTime) / 1000);
        if (seconds > 0) {
          reportWebsiteUsage(currentDomain, seconds);
        }
      }
      currentDomain = null;
      trackingStartTime = null;
      return;
    }

    const url = tabs[0].url;

    // Skip internal browser pages
    if (url.startsWith('about:') || url.startsWith('chrome:') ||
        url.startsWith('moz-extension:') || url.startsWith('chrome-extension:') ||
        url.startsWith('edge:')) {
      return;
    }

    const domain = extractDomain(url);

    if (!domain) return;

    // Check if domain changed
    if (domain !== currentDomain) {
      // Report time on previous domain
      if (currentDomain && trackingStartTime) {
        const seconds = Math.floor((Date.now() - trackingStartTime) / 1000);
        if (seconds > 0) {
          reportWebsiteUsage(currentDomain, seconds);
        }
      }

      // Start tracking new domain
      currentDomain = domain;
      trackingStartTime = Date.now();
      console.log(`Now tracking: ${domain}`);
    }
  } catch (error) {
    console.log('Error tracking active tab:', error);
  }
}

// Periodic usage reporting (in case tab stays active for a long time)
async function periodicUsageReport() {
  if (currentDomain && trackingStartTime) {
    const seconds = Math.floor((Date.now() - trackingStartTime) / 1000);
    if (seconds >= 10) {  // Report every 10 seconds of accumulated time
      console.log(`Periodic report: ${currentDomain} - ${seconds}s`);
      reportWebsiteUsage(currentDomain, seconds);
      trackingStartTime = Date.now();  // Reset tracking start
    }
  }
}

// Start usage tracking
function startUsageTracking() {
  // Track on tab activation
  browser.tabs.onActivated.addListener(trackActiveTab);

  // Track on window focus change
  browser.windows.onFocusChanged.addListener((windowId) => {
    if (windowId === browser.windows.WINDOW_ID_NONE) {
      // Window lost focus - report current usage
      if (currentDomain && trackingStartTime) {
        const seconds = Math.floor((Date.now() - trackingStartTime) / 1000);
        if (seconds > 0) {
          reportWebsiteUsage(currentDomain, seconds);
        }
        trackingStartTime = Date.now();  // Reset for when focus returns
      }
    } else {
      trackActiveTab();
    }
  });

  // Track on tab URL change + trigger AI NSFW check on page load complete
  browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.url && tab.active) {
      trackActiveTab();
    }

    // AI NSFW check when page finishes loading
    if (changeInfo.status === 'complete' && tab.url) {
      console.log(`[AI NSFW] Page loaded: ${tab.url} (active=${tab.active})`);
      // Skip internal pages
      if (tab.url.startsWith('about:') || tab.url.startsWith('chrome:') ||
          tab.url.startsWith('moz-extension:') || tab.url.startsWith('chrome-extension:') ||
          tab.url.startsWith('edge:')) {
        return;
      }
      const domain = extractDomain(tab.url);
      if (domain) {
        checkPageContent(tabId, tab.url, domain);
      }
    }
  });

  // Periodic reporting for long sessions
  setInterval(periodicUsageReport, 15000);  // Check every 15 seconds

  // Initial tracking
  trackActiveTab();

  // Try to flush queue periodically
  setInterval(flushUsageQueue, 30000);  // Try every 30 seconds

  console.log('Usage tracking started');
}

// Initialize on load
initialize();

// Start usage tracking after initialization
startUsageTracking();
