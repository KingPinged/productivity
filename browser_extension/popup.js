// Popup script for Productivity Timer Blocker

let isBlocking = false;
let appConnected = false;

// Load current status
document.addEventListener('DOMContentLoaded', async () => {
  await loadStatus();

  // Set up event listeners
  document.getElementById('toggle-btn').addEventListener('click', toggleBlocking);
  document.getElementById('sync-btn').addEventListener('click', forceSync);
});

// Load status from background script
async function loadStatus() {
  try {
    const response = await browser.runtime.sendMessage({ action: 'getStatus' });
    updateUI(response);
  } catch (error) {
    console.error('Error loading status:', error);
  }
}

// Update UI based on status
function updateUI(status) {
  isBlocking = status.isBlocking;
  appConnected = status.appConnected;

  const connectionDot = document.getElementById('connection-dot');
  const connectionText = document.getElementById('connection-text');
  const statusText = document.getElementById('status-text');
  const statusIndicator = document.getElementById('status-indicator');
  const toggleBtn = document.getElementById('toggle-btn');
  const controlledMessage = document.getElementById('controlled-message');
  const blockCount = document.getElementById('block-count');
  const sitesCount = document.getElementById('sites-count');
  const sitesPreview = document.getElementById('sites-preview');

  // Update connection status
  if (appConnected) {
    connectionDot.classList.add('connected');
    connectionText.textContent = 'Connected to Desktop App';
    controlledMessage.style.display = 'block';
    toggleBtn.classList.add('disabled');
    toggleBtn.textContent = isBlocking ? 'Blocking Active' : 'Waiting for Session';
  } else {
    connectionDot.classList.remove('connected');
    connectionText.textContent = 'Desktop App Not Running';
    controlledMessage.style.display = 'none';
    toggleBtn.classList.remove('disabled');
  }

  // Update blocking status
  if (isBlocking) {
    statusText.textContent = 'Blocking Active';
    statusIndicator.classList.add('active');
    if (!appConnected) {
      toggleBtn.textContent = 'Stop Blocking';
      toggleBtn.className = 'toggle-btn stop';
    }
  } else {
    statusText.textContent = 'Blocking Inactive';
    statusIndicator.classList.remove('active');
    if (!appConnected) {
      toggleBtn.textContent = 'Start Blocking';
      toggleBtn.className = 'toggle-btn start';
    }
  }

  // Update stats
  blockCount.textContent = status.blockCount || 0;
  sitesCount.textContent = status.blockedSites?.length || 0;

  // Show some blocked sites
  const sites = status.blockedSites || [];
  if (sites.length > 0) {
    const preview = sites.slice(0, 8).map(s => {
      // Clean up site name for display
      s = s.replace(/^(www\.)?/, '');
      return `<span>${s}</span>`;
    }).join('');
    const more = sites.length > 8 ? `<span>+${sites.length - 8} more</span>` : '';
    sitesPreview.innerHTML = preview + more;
  } else {
    sitesPreview.innerHTML = '<span>No sites configured</span>';
  }
}

// Toggle blocking (only works if app is not connected)
async function toggleBlocking() {
  if (appConnected) {
    // Can't toggle manually when app is connected
    return;
  }

  try {
    const response = await browser.runtime.sendMessage({ action: 'manualToggle' });
    if (response.error) {
      console.log(response.error);
    } else {
      await loadStatus();
    }
  } catch (error) {
    console.error('Error toggling:', error);
  }
}

// Force sync with desktop app
async function forceSync() {
  const syncBtn = document.getElementById('sync-btn');
  syncBtn.textContent = '↻ Syncing...';
  syncBtn.disabled = true;

  try {
    await browser.runtime.sendMessage({ action: 'forceSync' });
    await loadStatus();
  } catch (error) {
    console.error('Error syncing:', error);
  }

  syncBtn.textContent = '↻ Sync with Desktop App';
  syncBtn.disabled = false;
}
