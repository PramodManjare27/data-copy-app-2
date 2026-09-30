// Client-side mirror of the server-side idle-session enforcement in app/__init__.py.
// Purely a UX nicety (warns the user, then redirects) — the server independently
// enforces the real timeout on every request regardless of this script.
(function () {
  var scriptTag = document.currentScript;
  var timeoutSeconds = parseInt(scriptTag.getAttribute("data-timeout-seconds"), 10) || 300;
  var warnBeforeSeconds = 30;
  var idleTimer = null;
  var warnTimer = null;
  var warningEl = null;

  function showWarning() {
    if (warningEl) return;
    warningEl = document.createElement("div");
    warningEl.className = "position-fixed bottom-0 end-0 m-3 alert alert-warning shadow";
    warningEl.style.zIndex = 2000;
    warningEl.innerHTML =
      '<i class="bi bi-clock-history me-1"></i>You will be signed out soon due to inactivity. Move your mouse to stay signed in.';
    document.body.appendChild(warningEl);
  }

  function clearWarning() {
    if (warningEl) {
      warningEl.remove();
      warningEl = null;
    }
  }

  function goToLogout() {
    window.location.href = "/auth/logout";
  }

  function resetTimers() {
    clearWarning();
    clearTimeout(idleTimer);
    clearTimeout(warnTimer);
    warnTimer = setTimeout(showWarning, (timeoutSeconds - warnBeforeSeconds) * 1000);
    idleTimer = setTimeout(goToLogout, timeoutSeconds * 1000);
  }

  ["mousemove", "keydown", "click", "scroll", "touchstart"].forEach(function (evt) {
    document.addEventListener(evt, resetTimers, { passive: true });
  });

  resetTimers();
})();
