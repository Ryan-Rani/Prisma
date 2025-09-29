/*
  Background script:
  Listens for sync requests, opens LinkedIn analytics in a new tab,
  injects content script, and closes the tab after scraping.
  Also handles automated export functionality.
*/

// Track export state
let isExportMode = false;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    
    if (msg.type === "START_EXPORT") {
      isExportMode = true;
      console.log('Starting export process...');
      chrome.windows.create({
        url: "https://www.linkedin.com/analytics/creator/content/",
        type: "popup",
        focused: false,
        top: 5000,
        left: 5000,
        width: 1,
        height: 1
      }, (newWindow) => {
        const tab = newWindow.tabs?.[0];
        if (!tab) {
          console.error('No tab found in new window');
          return;
        }
        console.log('Created window with tab ID:', tab.id);
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["content.js"]
        }).then(() => {
          console.log('Content script injected for export');
          const sendExportMessage = (retryCount = 0) => {
            console.log(`Attempting to send export message (attempt ${retryCount + 1})...`);
            chrome.tabs.sendMessage(tab.id, { type: "PING" }, (response) => {
              if (chrome.runtime.lastError) {
                if (retryCount < 3) {
                  const delay = (retryCount + 1) * 2000;
                  setTimeout(() => sendExportMessage(retryCount + 1), delay);
                }
              } else {
                console.log('Content script is ready, sending export message');
                chrome.tabs.sendMessage(tab.id, { type: "TRIGGER_EXPORT" });
              }
            });
          };
          setTimeout(() => {
            sendExportMessage();
          }, 5000);
        }).catch((error) => {
          console.error('Error injecting content script for export:', error);
        });
        // Hide the window after export (optional: you can close it after a delay if desired)
        setTimeout(() => {
          chrome.windows.remove(newWindow.id, () => {});
        }, 20000);
      });
    }
    
    // Listen for scraped data and send to backend
    if (msg.type === "SCRAPED_CONTENT") {
      console.log('Received scraped content, export mode:', isExportMode);
      
      // Only close window and send to backend if NOT in export mode
      if (!isExportMode) {
        // Close the window after receiving data
        if (sender.tab) {
          chrome.windows.remove(sender.tab.windowId, () => {
            if (chrome.runtime.lastError) {
              console.log('Window already closed or error:', chrome.runtime.lastError.message);
            } else {
              console.log('Window closed after data received');
            }
          });
        }
        
        fetch('http://127.0.0.1:5000/receive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'top_performing_posts', urls: msg.payload })
        })
        .then(response => response.json())
        .then(data => console.log('Backend response:', data))
        .catch(error => console.error('Error sending to backend:', error));
      } else {
        console.log('In export mode, keeping window open for export process');
      }
    }
    
    // Listen for export triggered confirmation
    if (msg.type === "EXPORT_TRIGGERED") {
      console.log('Export was triggered successfully');
      isExportMode = false; // Reset export mode
      // The window will close automatically after the timeout
    }

    if (msg.type === "SCRAPE_TOP_POSTS") {
        sequentiallyScrapeTopPosts();
    }
  });

// Listen for all downloads and log them
chrome.downloads.onCreated.addListener(function(downloadItem) {
  // console.log('[Background] onCreated: Detected download:', downloadItem);
});

// Intercept XLS/XLSX downloads in onDeterminingFilename
chrome.downloads.onDeterminingFilename.addListener(function(item, suggest) {
  if (item.filename && (item.filename.endsWith('.xlsx') || item.filename.endsWith('.xls'))) {
    console.log('[Background] Intercepting XLS/XLSX download:', item.filename);
    // Cancel the download. If the download is already complete, Chrome will throw a 'Download must be in progress' error, which is safe to ignore.
    chrome.downloads.cancel(item.id, function() {
      // Assign the error to a variable to suppress Chrome's 'Unchecked runtime.lastError' warning, even if we ignore it
      const _suppressWarning = chrome.runtime.lastError;
      if (_suppressWarning && !_suppressWarning.message.includes('Download must be in progress')) {
        // Only log unexpected errors
        console.warn('[Background] Could not cancel download:', _suppressWarning.message);
      }
      chrome.tabs.query({url: 'https://www.linkedin.com/analytics/creator/content/*'}, function(tabs) {
        if (tabs && tabs.length > 0) {
          tabs.forEach(tab => {
            // Send the message to all relevant tabs. If the tab is closed or does not have the content script, Chrome will throw a 'Could not establish connection' error, which is safe to ignore.
            chrome.tabs.sendMessage(tab.id, {
              type: 'FETCH_XLS_FROM_URL',
              url: item.url,
              filename: item.filename
            }, function(response) {
              if (chrome.runtime.lastError) {
                // Suppress 'Could not establish connection' errors, which just mean the tab is closed or doesn't have the content script.
                // Only log other errors if needed.
                // console.warn('[Background] Error sending FETCH_XLS_FROM_URL to tab', tab.id, ':', chrome.runtime.lastError.message);
              }
            });
          });
        }
      });
    });
  }
  suggest();
});

// Fetch top posts from backend and log them
function fetchAndLogTopPosts() {
  fetch('http://127.0.0.1:5000/top-posts')
    .then(response => response.json())
    .then(data => {
      console.log('[Extension] Top posts by engagement:', data.top_by_engagement);
      console.log('[Extension] Top posts by impressions:', data.top_by_impressions);
    })
    .catch(error => {
      console.error('[Extension] Error fetching top posts:', error);
    });
}

// Sequentially scrape up to 10 unique top post URLs
async function sequentiallyScrapeTopPosts() {
    console.log('[Extension] Starting sequential scraping of top posts...');
    try {
        const response = await fetch('http://127.0.0.1:5000/top-posts');
        const data = await response.json();
        // Build a mapping from URL to publish_date
        const urlToDate = {};
        (data.top_by_engagement || []).forEach(post => { if (post.url) urlToDate[post.url] = post.publish_date; });
        (data.top_by_impressions || []).forEach(post => { if (post.url) urlToDate[post.url] = post.publish_date; });
        const urls = [
            ...(data.top_by_engagement?.map(post => post.url) || []),
            ...(data.top_by_impressions?.map(post => post.url) || [])
        ].filter(Boolean);
        const uniqueUrls = Array.from(new Set(urls)).slice(0, 50);
        const author = data.author || null;
        if (uniqueUrls.length === 0) {
            console.log('[Extension] No top post URLs found to scrape.');
            return;
        }
        console.log(`[Extension] Will sequentially scrape up to 50 posts. Actual count: ${uniqueUrls.length}`);
        for (let i = 0; i < uniqueUrls.length; i++) {
            const url = uniqueUrls[i];
            const publishDate = urlToDate[url] || null;
            console.log(`[Extension] Scraping post ${i+1}/${uniqueUrls.length}: ${url} (publish_date: ${publishDate}, author: ${author})`);
            await scrapeSinglePost(url, publishDate, author, i+1, uniqueUrls.length);
            if (i < uniqueUrls.length - 1) {
                console.log('[Extension] Waiting 5 seconds before next scrape...');
                await delay(5000); // 5 seconds
            }
        }
        console.log('[Extension] Finished sequential scraping of all top posts.');
    } catch (err) {
        console.error('[Extension] Error during sequential scraping:', err);
    }
}

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Open a tab, inject scraper, wait for scrape, close tab
function scrapeSinglePost(url, publishDate, author, index, total) {
    return new Promise((resolve) => {
        chrome.windows.create({
            url: url,
            type: 'popup',
            focused: false,
            top: 5000,
            left: 5000,
            width: 1,
            height: 1
        }, (newWindow) => {
            if (!newWindow.tabs || !newWindow.tabs[0]) {
                console.error(`[Extension] Could not open tab for URL: ${url}`);
                resolve();
                return;
            }
            const tab = newWindow.tabs[0];
            // Wait for tab to finish loading
            function listener(tabId, info) {
                if (tabId === tab.id && info.status === 'complete') {
                    chrome.tabs.onUpdated.removeListener(listener);
                    chrome.scripting.executeScript({
                        target: { tabId: tab.id },
                        files: ['scrape_post.js']
                    }, () => {
                        console.log(`[Extension] Injected scrape_post.js into tab ${tab.id} for post ${index}/${total}`);
                        // Send publish_date and author to content script
                        if (publishDate || author) {
                            chrome.tabs.sendMessage(tab.id, { type: 'SET_PUBLISH_DATE', publish_date: publishDate, author: author });
                        }
                    });
                }
            }
            chrome.tabs.onUpdated.addListener(listener);
            // Listen for scrape completion from content script
            function onScraped(msg, sender) {
                if (msg && msg.type === 'POST_SCRAPED' && sender.tab && sender.tab.id === tab.id) {
                    console.log(`[Extension] Scrape complete for post ${index}/${total}: ${url}`);
                    chrome.runtime.onMessage.removeListener(onScraped);
                    // Close the window after scrape
                    chrome.windows.remove(newWindow.id, () => {
                        if (chrome.runtime.lastError) {
                            console.log('[Extension] Scraping window already closed or error:', chrome.runtime.lastError.message);
                        } else {
                            console.log(`[Extension] Scraping window closed for post ${index}/${total}`);
                        }
                        resolve();
                    });
                }
            }
            chrome.runtime.onMessage.addListener(onScraped);
            // Failsafe: close window after 40 seconds if no response
            setTimeout(() => {
                chrome.runtime.onMessage.removeListener(onScraped);
                chrome.windows.remove(newWindow.id, () => {
                    if (chrome.runtime.lastError) {
                        console.log('[Extension] Failsafe: Scraping window already closed or error:', chrome.runtime.lastError.message);
                    } else {
                        console.log(`[Extension] Failsafe: Scraping window closed for post ${index}/${total}`);
                    }
                    resolve();
                });
            }, 40000);
        });
    });
}

// For testing: call on extension startup after logging top posts
fetchAndLogTopPosts();