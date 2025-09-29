/*
  Popup script:
  Sends sync and export requests to the background script when buttons are clicked.
*/
document.getElementById("exportBtn").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "START_EXPORT" });
  });

document.getElementById("scrapeBtn").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "SCRAPE_TOP_POSTS" });
});