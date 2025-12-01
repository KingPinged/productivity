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
let whitelistedUrls = [];  // URLs that are allowed even if domain is blocked
let blockCount = 0;
let appConnected = false;
let syncInterval = null;

// Initialize
async function initialize() {
  // Load saved state
  const data = await browser.storage.local.get(['blockedSites', 'whitelistedUrls', 'blockCount']);
  blockedSites = data.blockedSites || DEFAULT_BLOCKED_SITES;
  whitelistedUrls = data.whitelistedUrls || [];
  blockCount = data.blockCount || 0;

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
  } catch (error) {
    // Server not available - app might not be running
    appConnected = false;

    // If we were blocking based on app, stop
    if (isBlocking) {
      isBlocking = false;
      stopBlocking();
      updateIcon();
    }
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

// Build regex pattern for blocked sites
function buildBlockPattern() {
  if (blockedSites.length === 0) {
    return null;
  }

  const escaped = blockedSites.map(site => {
    // Remove protocol and www if present
    site = site.replace(/^(https?:\/\/)?(www\.)?/, '');
    // Escape special regex chars
    return site.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  });

  return new RegExp(`^https?://(www\\.)?(${escaped.join('|')})`, 'i');
}

// Request listener
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

// Start blocking
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

  console.log("Productivity Timer: Blocking started");
  console.log("Whitelisted URLs:", whitelistedUrls);
}

// Stop blocking
function stopBlocking() {
  if (browser.webRequest.onBeforeRequest.hasListener(blockRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(blockRequest);
  }

  console.log("Productivity Timer: Blocking stopped");
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
      whitelistedUrls,
      blockCount,
      appConnected
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

// Initialize on load
initialize();
