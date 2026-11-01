// Boot safety net (fix 2026-10-24: an invitation opened from the installed Android PWA stayed on the boot screen
// forever). The static boot screen of index.html is normally removed by the app (platform/boot.ts::dismissBoot). If it
// is still there after BOOT_LIMIT_MS — script that never loaded, network that never answered, unexpected error — it is
// replaced by an explicit message with « Réessayer ». Never a token or a URL in the logs.
(function () {
  var BOOT_LIMIT_MS = 15000;
  // Reload asked by « Mettre à jour » (platform/updates.ts): say so on the boot screen instead of a silent dark screen.
  try {
    if (sessionStorage.getItem('edusync.just-updated') !== null) {
      var line = document.querySelector('#edusync-boot .staticBootLine');
      if (line) { var p = document.createElement('span'); p.textContent = 'Installation de la mise à jour…'; p.setAttribute('style', 'font-size:13.5px;color:rgba(255,255,255,.78)'); line.parentNode.appendChild(p); }
    }
  } catch (e) { /* sessionStorage unavailable */ }
  function stillBooting() {
    var el = document.getElementById('edusync-boot');
    return el && !el.classList.contains('out') ? el : null;
  }
  function showError(reason) {
    var el = stillBooting();
    if (!el || el.getAttribute('data-failed')) return;
    el.setAttribute('data-failed', reason);
    try { console.info('edusync.boot', {stage: 'fallback', result: reason, online: navigator.onLine}); } catch (e) { /* console unavailable */ }
    var offline = navigator.onLine === false;
    el.setAttribute('role', 'alert');
    el.innerHTML =
      '<div class="staticBootCore" style="max-width:320px;padding:0 24px;text-align:center">' +
      '<img class="staticBootMark" src="/icons/edusync-mark.svg" alt="" width="64" height="64" style="animation:none;width:64px;height:64px"/>' +
      '<span class="staticBootName" style="font-size:20px">EduSync ne parvient pas à démarrer</span>' +
      '<p style="margin:0;font-size:14.5px;line-height:1.5;color:rgba(255,255,255,.82)">' +
      (offline ? 'Ce téléphone n’est pas connecté à Internet. Vérifiez le Wi-Fi ou les données mobiles, puis réessayez.'
               : 'Le chargement prend trop de temps. Vérifiez votre connexion, puis réessayez. Si vous ouvriez un lien d’invitation, il reste valable.') +
      '</p>' +
      '<button type="button" id="edusync-boot-retry" style="min-height:46px;padding:0 28px;border:0;border-radius:12px;background:#2f7bff;color:#fff;font:inherit;font-size:15px;font-weight:700;cursor:pointer">Réessayer</button>' +
      '</div><div class="staticBootSign">from VolcanoTech</div>';
    document.getElementById('edusync-boot-retry').addEventListener('click', function () { location.reload(); });
  }
  window.setTimeout(function () { showError('timeout'); }, BOOT_LIMIT_MS);
  // The app module could not even load (offline first visit, missing asset): no need to wait the full delay.
  window.addEventListener('error', function (e) {
    var t = e && e.target;
    if (t && t.tagName === 'SCRIPT' && stillBooting()) window.setTimeout(function () { showError('script'); }, 1500);
  }, true);
  window.addEventListener('online', function () {
    if (stillBooting() && document.getElementById('edusync-boot').getAttribute('data-failed')) location.reload();
  });
})();
