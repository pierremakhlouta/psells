// Registers PSells' service worker, /sw.js, and shows the page's "You're
// offline" line while the connection is gone. Loaded by every page from
// base.html, as a file: the security policy allows PSells' own script files
// and no inline script.

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

function showConnection() {
  const notice = document.getElementById("offline-notice");
  if (notice) {
    notice.hidden = navigator.onLine;
  }
}

window.addEventListener("online", showConnection);
window.addEventListener("offline", showConnection);
document.addEventListener("DOMContentLoaded", showConnection);
