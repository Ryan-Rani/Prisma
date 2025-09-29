/*
  Content script:
  Scrapes the URLs of 'Top performing posts' from the LinkedIn analytics content page and sends them to the extension.
  Also handles automated Export button clicking for XLS file download.
  Monitors for download links and intercepts them for backend processing.
*/

console.log('Content script loaded on:', window.location.href);

// Monitor for download links and intercept them
const observer = new MutationObserver((mutations) => {
  mutations.forEach((mutation) => {
    mutation.addedNodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE) {
        console.log('[Content] MutationObserver found node:', node);
        // Look for download links with various patterns
        const downloadSelectors = [
          'a[download]',
          'a[href*=".xlsx"]',
          'a[href*=".xls"]',
          'a[href*="blob:"]',
          'a[href*="export"]',
          'button[onclick*="download"]',
          'button[onclick*="export"]'
        ];
        
        downloadSelectors.forEach(selector => {
          const elements = node.querySelectorAll ? node.querySelectorAll(selector) : [];
          elements.forEach(element => {
            console.log('Found potential download element:', element);
            console.log('Element href:', element.href);
            console.log('Element onclick:', element.onclick);
            console.log('Element attributes:', element.attributes);
            
            if (element.href && element.href.startsWith('blob:')) {
              console.log('Detected blob download link:', element.href);
              interceptDownload(element.href);
            } else if (element.href && (element.href.includes('.xlsx') || element.href.includes('.xls'))) {
              console.log('Detected direct file download link:', element.href);
              interceptDownload(element.href);
            }
          });
        });
        
        // Also check if the node itself is a download link
        if (node.tagName === 'A') {
          console.log('Checking node as download link:', node);
          console.log('Node href:', node.href);
          console.log('Node download attribute:', node.hasAttribute('download'));
          
          if (node.href && node.href.startsWith('blob:')) {
            console.log('Detected blob download link (node):', node.href);
            interceptDownload(node.href);
          } else if (node.href && (node.href.includes('.xlsx') || node.href.includes('.xls'))) {
            console.log('Detected direct file download link (node):', node.href);
            interceptDownload(node.href);
          }
        }
        
        // Check for any elements with download-related text
        if (node.textContent && node.textContent.toLowerCase().includes('download')) {
          console.log('Found element with download text:', node);
        }
      }
    });
  });
});

// Start observing
observer.observe(document.body, { childList: true, subtree: true });

// Patch fetch to log all requests and look for XLS/XLSX
const originalFetch = window.fetch;
window.fetch = function(...args) {
  console.log('[Content][fetch] called with:', args);
  return originalFetch.apply(this, args).then(response => {
    // Clone response to inspect headers
    const cloned = response.clone();
    cloned.headers.forEach((value, key) => {
      if (
        value.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') ||
        value.includes('.xlsx') ||
        value.includes('.xls')
      ) {
        console.log('[Content][fetch] response looks like XLS:', key, value, cloned);
      }
    });
    // Try to log the URL and content-type
    if (
      cloned.url.includes('.xlsx') ||
      cloned.url.includes('.xls') ||
      cloned.headers.get('content-type')?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    ) {
      console.log('[Content][fetch] XLS/XLSX detected in response:', cloned.url, cloned.headers.get('content-type'));
    }
    return response;
  });
};
// Patch XHR to log all requests and look for XLS/XLSX
const originalOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url, ...rest) {
  this._url = url;
  return originalOpen.call(this, method, url, ...rest);
};
const originalSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(...args) {
  this.addEventListener('load', function() {
    try {
      const contentType = this.getResponseHeader('Content-Type') || '';
      if (
        (this._url && (this._url.includes('.xlsx') || this._url.includes('.xls')))
        || contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      ) {
        console.log('[Content][XHR] XLS/XLSX detected:', this._url, contentType, this);
      }
    } catch (e) {
      console.warn('[Content][XHR] Error inspecting XHR:', e);
    }
  });
  return originalSend.apply(this, args);
};

// Function to intercept download and send to backend
function interceptDownload(url) {
  console.log('[Content] interceptDownload called with URL:', url);
  
  if (url.startsWith('blob:')) {
    // Handle blob URLs
    fetch(url)
      .then(response => response.blob())
      .then(blob => {
        console.log('[Content] Download intercepted, blob size:', blob.size);
        
        // Create FormData and send to backend
        const formData = new FormData();
        formData.append('file', blob, 'linkedin_analytics.xlsx');
        console.log('[Content] Uploading blob to backend...');
        
        return fetch('http://127.0.0.1:5000/upload-xls', {
          method: 'POST',
          body: formData
        });
      })
      .then(response => response.json())
      .then(data => {
        console.log('[Content] File uploaded successfully:', data);
        // Notify background script
        chrome.runtime.sendMessage({ 
          type: "FILE_UPLOADED", 
          success: true, 
          data: data 
        });
      })
      .catch(error => {
        console.error('[Content] Error uploading file:', error);
        chrome.runtime.sendMessage({ 
          type: "FILE_UPLOADED", 
          success: false, 
          error: error.message 
        });
      });
  } else {
    // Handle direct file URLs
    console.log('[Content] Direct file URL detected, attempting to fetch:', url);
    fetch(url)
      .then(response => response.blob())
      .then(blob => {
        console.log('[Content] Direct file intercepted, blob size:', blob.size);
        
        const formData = new FormData();
        formData.append('file', blob, 'linkedin_analytics.xlsx');
        console.log('[Content] Uploading direct file blob to backend...');
        
        return fetch('http://127.0.0.1:5000/upload-xls', {
          method: 'POST',
          body: formData
        });
      })
      .then(response => response.json())
      .then(data => {
        console.log('[Content] File uploaded successfully:', data);
        chrome.runtime.sendMessage({ 
          type: "FILE_UPLOADED", 
          success: true, 
          data: data 
        });
      })
      .catch(error => {
        console.error('[Content] Error uploading file:', error);
        chrome.runtime.sendMessage({ 
          type: "FILE_UPLOADED", 
          success: false, 
          error: error.message 
        });
      });
  }
}

// Function to scrape top performing posts
function scrapeTopPerformingPosts() {
  console.log('Starting to scrape top performing posts...');
  
  // 1. Find the "Top performing posts" section
  const topPostsHeader = Array.from(document.querySelectorAll('h2.analytics-libra-header__title'))
    .find(h2 => h2.textContent.includes('Top performing posts'));

  let urls = [];
  if (topPostsHeader) {
    // 2. Find the closest parent container that holds the list
    const section = topPostsHeader.closest('.member-analytics-addon-loader, .member-analytics-addon-card__subcomponent-container');
    if (section) {
      // 3. Find the list of posts
      const ul = section.querySelector('ul.member-analytics-addon-analytics-object-list');
      if (ul) {
        // 4. For each list item, get the post URL
        urls = Array.from(ul.querySelectorAll('li')).map(li => {
          const a = li.querySelector('a[href*="/feed/update/urn:li:activity:"]');
          return a ? a.href : null;
        }).filter(Boolean);
      }
    }
  }

  console.log('Found URLs:', urls.length);

  // Send scraped data with error handling
  try {
    chrome.runtime.sendMessage({ type: "SCRAPED_CONTENT", payload: urls }, (response) => {
      if (chrome.runtime.lastError) {
        console.log('Message send error (likely tab closed):', chrome.runtime.lastError.message);
      } else {
        console.log('Data sent successfully:', urls.length, 'URLs found');
      }
    });
  } catch (error) {
    console.log('Error sending message:', error.message);
  }
}

// Function to trigger Export button click
function triggerExport() {
  console.log('[Content] Looking for Export button...');
  let checkCount = 0;
  const maxChecks = 30; // Wait up to ~15 seconds

  function findAndClickExport() {
    checkCount++;
    const buttons = Array.from(document.querySelectorAll('button'));
    for (const button of buttons) {
      const text = button.textContent.trim().toLowerCase();
      if (text.includes('export')) {
        console.log('[Content] Found Export button:', button);
        console.log('[Content] Button text:', button.textContent);
        console.log('[Content] Button attributes:', button.attributes);
        console.log('[Content] button.disabled:', button.disabled);
        console.log('[Content] button.classList:', Array.from(button.classList));
        if (button.disabled || button.classList.contains('artdeco-button--disabled')) {
          console.log('[Content] Export button is currently disabled, waiting...');
          setTimeout(findAndClickExport, 500);
          return;
        } else {
          console.log('[Content] Export button is enabled, waiting 500ms before clicking...');
          setTimeout(() => {
            button.click();
            console.log('[Content] Export button clicked successfully');
          }, 500);
          return;
        }
      }
    }
    if (checkCount < maxChecks) {
      setTimeout(findAndClickExport, 500);
    } else {
      console.warn('[Content] Export button not found or never enabled after waiting.');
    }
  }
  findAndClickExport();
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "TRIGGER_EXPORT") {
    console.log('[Content] Received TRIGGER_EXPORT message');
    triggerExport();
    sendResponse({ status: 'triggered' });
  }
  if (msg.type === "PING") {
    console.log('[Content] Received PING message');
    sendResponse({ status: 'pong' });
  }
  if (msg.type === "FETCH_XLS_FROM_URL") {
    console.log('[Content] Received FETCH_XLS_FROM_URL:', msg.url);
    fetch(msg.url)
      .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.blob();
      })
      .then(blob => {
        console.log('[Content] Fetched XLS blob from URL, size:', blob.size);
        const formData = new FormData();
        formData.append('file', blob, msg.filename || 'linkedin_analytics.xlsx');
        console.log('[Content] Uploading fetched XLS blob to backend...');
        return fetch('http://127.0.0.1:5000/upload-xls', {
          method: 'POST',
          body: formData
        });
      })
      .then(response => response.json())
      .then(data => {
        console.log('[Content] File uploaded successfully from download intercept:', data);
        chrome.runtime.sendMessage({ type: "FILE_UPLOADED", success: true, data: data });
      })
      .catch(error => {
        console.error('[Content] Error fetching/uploading XLS from URL:', error);
        chrome.runtime.sendMessage({ type: "FILE_UPLOADED", success: false, error: error.message });
      });
  }
});

console.log('Content script message listener set up');

// Auto-scrape on page load (existing behavior)
// Only auto-scrape if we're on the analytics page and not being triggered by a message
// REMOVED: Auto-scrape was causing the window to close before export could be triggered
// if (window.location.href.includes('linkedin.com/analytics/creator/content')) {
//   console.log('Auto-scraping on page load...');
//   scrapeTopPerformingPosts();
// }