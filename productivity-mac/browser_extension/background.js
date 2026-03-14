// Productivity Timer - Website Blocker Extension (Manifest V3)
// Background service worker that blocks websites during focus sessions
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
  const data = await chrome.storage.local.get(['blockedSites', 'alwaysBlockedSites', 'whitelistedUrls', 'blockCount', 'punishmentState', 'aiCheckedDomains']);
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
    console.log("Punishment lock active on startup - blocking all traffic");
  }

  // Start syncing with desktop app
  startSync();

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
      isBlocking = status.isBlocking;

      // Always sync sites so alwaysBlockedSites stays current
      await fetchBlockedSites();

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
      await chrome.storage.local.set({ punishmentState: status });
      isPunishmentLocked = status.is_locked;
    }
  } catch (error) {
    await checkCachedPunishmentStatus();
  }
}

// Check cached punishment state (used when server is unreachable)
async function checkCachedPunishmentStatus() {
  try {
    const data = await chrome.storage.local.get(['punishmentState']);
    if (data.punishmentState) {
      const status = data.punishmentState;
      if (status.is_locked && status.lock_time_remaining > 0) {
        isPunishmentLocked = true;
      } else {
        isPunishmentLocked = false;
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

      if (data.sites && data.sites.length > 0) {
        blockedSites = data.sites;
        await chrome.storage.local.set({ blockedSites });
      }

      if (data.alwaysBlocked && data.alwaysBlocked.length > 0) {
        alwaysBlockedSites = data.alwaysBlocked;
        await chrome.storage.local.set({ alwaysBlockedSites });
        console.log('Always-blocked sites loaded:', alwaysBlockedSites.length, 'sites');
      }

      if (data.whitelist) {
        whitelistedUrls = data.whitelist;
        await chrome.storage.local.set({ whitelistedUrls });
        console.log('Whitelist loaded:', whitelistedUrls);
      }
    }
  } catch (error) {
    console.log('Could not fetch blocked sites from app');
  }
}

// Check if a URL is whitelisted
function isWhitelisted(url) {
  if (!whitelistedUrls || whitelistedUrls.length === 0) return false;

  const normalizedUrl = url.toLowerCase();

  for (const whitelistEntry of whitelistedUrls) {
    const normalizedWhitelist = whitelistEntry.toLowerCase();

    if (normalizedUrl === normalizedWhitelist) return true;
    if (normalizedUrl.startsWith(normalizedWhitelist)) return true;

    const urlWithoutProtocol = normalizedUrl.replace(/^https?:\/\//, '');
    const whitelistWithoutProtocol = normalizedWhitelist.replace(/^https?:\/\//, '');

    if (urlWithoutProtocol === whitelistWithoutProtocol) return true;
    if (urlWithoutProtocol.startsWith(whitelistWithoutProtocol)) return true;

    const urlNoWww = urlWithoutProtocol.replace(/^www\./, '');
    const whitelistNoWww = whitelistWithoutProtocol.replace(/^www\./, '');

    if (urlNoWww === whitelistNoWww || urlNoWww.startsWith(whitelistNoWww)) return true;
  }

  return false;
}

// Check if a URL matches a list of site patterns
function matchesSiteList(url, sites) {
  if (!sites || sites.length === 0) return false;

  let hostname;
  try {
    hostname = new URL(url).hostname.toLowerCase();
  } catch {
    return false;
  }

  for (const site of sites) {
    const clean = site.replace(/^(https?:\/\/)?(www\.)?/, '').toLowerCase();
    if (hostname === clean || hostname === 'www.' + clean ||
        hostname.endsWith('.' + clean)) {
      return true;
    }
  }
  return false;
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
      await chrome.storage.local.set({ punishmentState: data });
      console.log('Adult strike reported:', data);
    }
  } catch (error) {
    console.log('Could not report adult strike:', error);
  }
}

// Redirect a tab to the blocked page
function redirectToBlocked(tabId, url, flags = '') {
  const blockedPageUrl = chrome.runtime.getURL('blocked.html') +
    '?url=' + encodeURIComponent(url) + flags;
  chrome.tabs.update(tabId, { url: blockedPageUrl });
}

// Check a navigation and block if needed
function checkAndBlock(tabId, url) {
  if (!url || url.startsWith('chrome:') || url.startsWith('chrome-extension:') ||
      url.startsWith('about:') || url.startsWith('edge:')) {
    return false;
  }

  // Allow localhost (for our status server)
  if (url.includes('127.0.0.1') || url.includes('localhost')) {
    return false;
  }

  // Punishment mode - block EVERYTHING
  if (isPunishmentLocked) {
    console.log('Punishment block - ALL traffic blocked:', url);
    redirectToBlocked(tabId, url, '&adult=1&punishment=1');
    return true;
  }

  // Always-blocked sites (adult content) — ALWAYS active
  if (matchesSiteList(url, alwaysBlockedSites)) {
    blockCount++;
    chrome.storage.local.set({ blockCount });
    console.log('Always-blocked URL:', url);
    reportAdultStrike();
    redirectToBlocked(tabId, url, '&adult=1');
    return true;
  }

  // Session-based blocking — only during focus sessions
  if (isBlocking && !isWhitelisted(url) && matchesSiteList(url, blockedSites)) {
    blockCount++;
    chrome.storage.local.set({ blockCount });
    console.log('Blocked URL:', url);
    redirectToBlocked(tabId, url);
    return true;
  }

  return false;
}

// Listen for navigations (MV3 replacement for webRequest blocking)
chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  // Only block main frame navigations
  if (details.frameId !== 0) return;
  checkAndBlock(details.tabId, details.url);
});

// Also check on committed (catches redirects)
chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameId !== 0) return;
  // Skip if it's already our blocked page
  if (details.url.includes(chrome.runtime.id)) return;
  checkAndBlock(details.tabId, details.url);
});

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

  chrome.action.setIcon({ path: iconPath }).catch(() => {
    chrome.action.setIcon({ path: {
      16: "icons/icon16.png",
      48: "icons/icon48.png",
      128: "icons/icon128.png"
    }});
  });

  if (isBlocking) {
    chrome.action.setBadgeText({ text: "ON" });
    chrome.action.setBadgeBackgroundColor({ color: "#e74c3c" });
  } else if (appConnected) {
    chrome.action.setBadgeText({ text: "" });
  } else {
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#f39c12" });
  }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
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
    if (!appConnected) {
      isBlocking = !isBlocking;
      chrome.storage.local.set({ isBlocking });
      updateIcon();
      sendResponse({ isBlocking });
    } else {
      sendResponse({ error: 'Controlled by desktop app' });
    }
  } else if (message.action === 'resetCount') {
    blockCount = 0;
    chrome.storage.local.set({ blockCount });
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
        await chrome.storage.local.set({ aiCheckedDomains: Array.from(aiCheckedDomains) });
      }
    }
  } catch (error) {
    // Server unreachable - use cached set
  }
}

// Check if a domain should be sent for AI analysis
function shouldCheckDomain(domain) {
  if (!domain) return false;
  if (aiCheckedDomains.has(domain)) return false;
  if (aiCheckInProgress.has(domain)) return false;
  if (domain === '127.0.0.1' || domain === 'localhost') return false;
  if (domain.endsWith('.local')) return false;
  if (matchesSiteList('https://' + domain, alwaysBlockedSites)) return false;
  if (matchesSiteList('https://' + domain, blockedSites)) return false;
  return true;
}

// Extract page signals from a tab
async function extractPageSignals(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const meta = document.querySelector('meta[name="description"]');
        const metaDesc = meta ? meta.getAttribute('content') || '' : '';
        const bodyText = (document.body ? document.body.innerText || '' : '').substring(0, 500);
        return {
          title: document.title || '',
          meta_description: metaDesc,
          body_text: bodyText
        };
      }
    });
    if (results && results[0] && results[0].result) {
      console.log(`[AI NSFW] Extracted signals: title="${results[0].result.title}", body=${results[0].result.body_text.length} chars`);
      return results[0].result;
    }
    return null;
  } catch (error) {
    console.log('[AI NSFW] executeScript failed:', error.message || error);
    return null;
  }
}

// Send page signals to backend for AI NSFW check
async function checkPageContent(tabId, url, domain) {
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
  if (!appConnected) return;
  if (!shouldCheckDomain(domain)) return;

  console.log(`[AI NSFW] Checking domain: ${domain}`);
  aiCheckInProgress.add(domain);

  try {
    const signals = await extractPageSignals(tabId);

    const payload = {
      url: url,
      domain: domain,
      title: signals ? signals.title : '',
      meta_description: signals ? signals.meta_description : '',
      body_text: signals ? signals.body_text : ''
    };

    const response = await fetch(`${SERVER_URL}/check-content`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-cache'
    });

    if (response.ok) {
      const result = await response.json();
      console.log(`[AI NSFW] Result for ${domain}: is_nsfw=${result.is_nsfw}, confidence=${result.confidence}, method=${result.method}`);

      if (result.method !== 'disabled' && result.method !== 'no_api_key') {
        aiCheckedDomains.add(domain);
        await chrome.storage.local.set({ aiCheckedDomains: Array.from(aiCheckedDomains) });
      }

      if (result.is_nsfw) {
        console.log(`[AI NSFW] BLOCKED: ${domain}`);

        if (!alwaysBlockedSites.includes(domain)) {
          alwaysBlockedSites.push(domain);
          await chrome.storage.local.set({ alwaysBlockedSites });
        }

        redirectToBlocked(tabId, url, '&adult=1&ai=1');
        reportAdultStrike();
      }
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
      flushUsageQueue();
    } else {
      usageReportQueue.push(report);
    }
  } catch (error) {
    usageReportQueue.push(report);
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
        usageReportQueue.push(report);
      }
    } catch (error) {
      usageReportQueue.push(report);
      break;
    }
  }
}

// Track the currently active tab
async function trackActiveTab() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });

    if (tabs.length === 0 || !tabs[0].url) {
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

    if (url.startsWith('about:') || url.startsWith('chrome:') ||
        url.startsWith('chrome-extension:') || url.startsWith('edge:')) {
      return;
    }

    const domain = extractDomain(url);
    if (!domain) return;

    if (domain !== currentDomain) {
      if (currentDomain && trackingStartTime) {
        const seconds = Math.floor((Date.now() - trackingStartTime) / 1000);
        if (seconds > 0) {
          reportWebsiteUsage(currentDomain, seconds);
        }
      }

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
    if (seconds >= 10) {
      reportWebsiteUsage(currentDomain, seconds);
      trackingStartTime = Date.now();
    }
  }
}

// Start usage tracking
function startUsageTracking() {
  chrome.tabs.onActivated.addListener(trackActiveTab);

  chrome.windows.onFocusChanged.addListener((windowId) => {
    if (windowId === chrome.windows.WINDOW_ID_NONE) {
      if (currentDomain && trackingStartTime) {
        const seconds = Math.floor((Date.now() - trackingStartTime) / 1000);
        if (seconds > 0) {
          reportWebsiteUsage(currentDomain, seconds);
        }
        trackingStartTime = Date.now();
      }
    } else {
      trackActiveTab();
    }
  });

  // AI NSFW check when page finishes loading
  chrome.webNavigation.onCompleted.addListener((details) => {
    if (details.frameId !== 0) return;

    // Also track the active tab
    trackActiveTab();

    const url = details.url;
    if (url.startsWith('about:') || url.startsWith('chrome:') ||
        url.startsWith('chrome-extension:') || url.startsWith('edge:')) {
      return;
    }
    const domain = extractDomain(url);
    if (domain) {
      checkPageContent(details.tabId, url, domain);
    }
  });

  // Periodic reporting
  setInterval(periodicUsageReport, 15000);
  setInterval(flushUsageQueue, 30000);

  trackActiveTab();
  console.log('Usage tracking started');
}

// Initialize on load
initialize();
startUsageTracking();
