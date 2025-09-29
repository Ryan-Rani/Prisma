// scrape_post.js

(function() {
  // --- Post Text ---
  function getPostText() {
    const postContent = document.querySelector('[data-test-id="main-feed-activity-card-content"]') ||
                       document.querySelector('.feed-shared-update-v2__description') ||
                       document.querySelector('.update-components-text');
    if (postContent) {
      return postContent.innerText.trim();
    }
    return null;
  }

  // --- Reactions ---
  function getReactions() {
    const reactionsSection = document.querySelector('.social-details-social-counts') ||
                            document.querySelector('.social-details-social-counts__reactions') ||
                            document.querySelector('[data-test-id="social-actions"]');
    if (!reactionsSection) return null;
    // Get total reactions count
    let total = null;
    const countSpan = reactionsSection.querySelector('.social-details-social-counts__reactions-count');
    if (countSpan) {
      total = parseInt(countSpan.innerText.replace(/[^\d]/g, ''), 10);
    }
    // Get types (from <img> tags)
    const types = [];
    reactionsSection.querySelectorAll('img[data-test-reactions-icon-type]').forEach(img => {
      types.push({
        type: img.getAttribute('data-test-reactions-icon-type'),
        alt: img.getAttribute('alt')
      });
    });
    // Get comments count (if present)
    let commentsCount = null;
    const commentsBtn = reactionsSection.querySelector('.social-details-social-counts__comments span');
    if (commentsBtn) {
      commentsCount = parseInt(commentsBtn.innerText.replace(/[^\d]/g, ''), 10);
    }
    return { total, types, commentsCount };
  }

  // --- Comments ---
  function getComments() {
    const commentsSection = document.querySelector('.comments-comments-list') ||
                           document.querySelector('.comments-list') ||
                           document.querySelector('[data-test-id="comments-section"]');
    if (!commentsSection) return [];
    const comments = [];
    commentsSection.querySelectorAll('.comments-comment-entity').forEach(entity => {
      const author = entity.querySelector('.comments-comment-meta__description-title')?.innerText.trim() || null;
      const text = entity.querySelector('.comments-comment-item__main-content, .update-components-text')?.innerText.trim() || null;
      comments.push({ author, text });
    });
    return comments;
  }

  // --- Format Detection ---
  function detectPostFormat() {
    // Look for video in the post content
    const hasVideo = document.querySelector('.feed-shared-update-v2__content video, .update-components-video') !== null;
    if (hasVideo) {
      return 'Text with video';
    }
    // Look for main post image (not avatars/icons)
    const hasImage = document.querySelector('.update-components-image__image') !== null;
    if (hasImage) {
      return 'Text with image';
    }
    // Default to text-only
    return 'Text-only';
  }

  // --- Collect and log all data ---
  let publishDate = null;
  let author = null;
  // Listen for publish_date and author from background script
  if (window.chrome && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
      if (msg && msg.type === 'SET_PUBLISH_DATE') {
        publishDate = msg.publish_date;
        author = msg.author;
        console.log('[Scraper] Received publish_date:', publishDate);
        console.log('[Scraper] Received author:', author);
      }
    });
  }

  // Wait a short time to allow publishDate and author to be set before scraping
  setTimeout(() => {
    const postText = getPostText();
    const reactions = getReactions();
    const comments = getComments();
    const format = detectPostFormat();

    const scraped = { postText, reactions, comments, format };
    console.log('[Scraper] Structured post data:', scraped);
    console.log('[Scraper] Detected post format:', format);

    // Send to backend
    fetch('http://127.0.0.1:5000/receive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'scraped_post', data: scraped, url: window.location.href, publish_date: publishDate, author: author })
    })
      .then(res => res.json())
      .then(data => {
        console.log('[Scraper] Backend response:', data);
        // Optionally notify background script
        if (window.chrome && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage({ type: 'POST_SCRAPED', success: true, url: window.location.href });
        }
      })
      .catch(err => {
        console.error('[Scraper] Error sending to backend:', err);
        if (window.chrome && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage({ type: 'POST_SCRAPED', success: false, url: window.location.href, error: err.message });
        }
      });
  }, 500); // Wait 500ms for publishDate and author to arrive
})(); 