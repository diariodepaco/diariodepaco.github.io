/* El Diario de Paco: ajusta "hoy/ayer" a la hora real y avisa si la página es antigua. Sin cookies ni rastreo. */
(function () {
  var DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  // Hora de Canarias (UTC+0 en invierno, UTC+1 en verano), igual que la página
  function canarias(ms) {
    var d = new Date(ms), y = d.getUTCFullYear();
    function ultimoDomingo(mes) { var x = new Date(Date.UTC(y, mes + 1, 0, 1)); x.setUTCDate(x.getUTCDate() - x.getUTCDay()); return x.getTime(); }
    var verano = ms >= ultimoDomingo(2) && ms < ultimoDomingo(9);
    return new Date(ms + (verano ? 3600000 : 0));
  }
  function diaN(d) { return Math.floor(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 86400000); }
  function etiqueta(ts, ahora) {
    var l = canarias(ts * 1000), h = canarias(ahora);
    var hora = l.getUTCHours() + ':' + ('0' + l.getUTCMinutes()).slice(-2);
    var dif = diaN(h) - diaN(l);
    if (dif <= 0) return 'hoy, ' + hora;
    if (dif === 1) return 'ayer, ' + hora;
    if (dif < 7) return DIAS[l.getUTCDay()] + ' ' + l.getUTCDate() + ', ' + hora;
    return l.getUTCDate() + ' de ' + MESES[l.getUTCMonth()];
  }
  function arreglar() {
    var ahora = Date.now();
    var t = document.querySelectorAll('time[data-ts]');
    for (var i = 0; i < t.length; i++) t[i].textContent = etiqueta(+t[i].getAttribute('data-ts'), ahora);
    var gen = +document.body.getAttribute('data-gen') * 1000, horas = Math.floor((ahora - gen) / 3600000);
    var aviso = document.getElementById('aviso');
    if (aviso && gen && horas >= 4) {
      var cuando = horas < 48 ? 'de hace ' + horas + ' horas' : 'de hace ' + Math.floor(horas / 24) + ' días';
      aviso.innerHTML = 'Estas noticias son ' + cuando + '. <a href="#" id="recargar">Actualizar</a>';
      aviso.hidden = false;
      document.getElementById('recargar').onclick = function (e) { e.preventDefault(); location.reload(); };
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arreglar); else arreglar();

  // Clave familiar para leer las noticias aquí dentro (llega en el enlace del QR: …/#clave=XXXX)
  var m = /(?:^#|&)clave=([^&]+)/.exec(location.hash || '');
  if (m) {
    try { localStorage.setItem('diario_clave', decodeURIComponent(m[1])); } catch (x) {}
    try { history.replaceState(null, '', location.pathname + location.search); } catch (x) { location.hash = ''; }
  }
  function clave() { try { return localStorage.getItem('diario_clave'); } catch (x) { return null; } }
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[data-leer]') : null;
    if (!a) return;
    e.preventDefault();
    location.href = 'leer.html#' + a.getAttribute('data-leer');
  });

  // Botón de volver arriba: solo cuando ya se ha bajado un buen trozo
  var subir = document.getElementById('subir'), mirando = false;
  function botonSubir() {
    mirando = false;
    if (subir) subir.className = (window.pageYOffset || document.documentElement.scrollTop) > 700 ? 'subir visible' : 'subir';
  }
  window.addEventListener('scroll', function () {
    if (!mirando) { mirando = true; (window.requestAnimationFrame || setTimeout)(botonSubir, 16); }
  }, { passive: true });
  if (subir) subir.addEventListener('click', function (e) {
    e.preventDefault();
    try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (x) { window.scrollTo(0, 0); }
  });

  // Se puede instalar como aplicación (sin tienda ni APK) y se lee sin conexión
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('sw.js').catch(function () {}); });
  }
  var pendiente = null;
  var instalada = window.matchMedia && window.matchMedia('(display-mode: standalone)').matches;
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    if (instalada) return;  // dentro de la aplicación instalada no se ofrece nunca
    pendiente = e;
    var caja = document.getElementById('instalar');
    if (caja) caja.hidden = false;
  });
  window.addEventListener('appinstalled', function () {
    var caja = document.getElementById('instalar');
    if (caja) caja.hidden = true;
  });
  // En Brave no sale el aviso de instalar de Chrome: se explica cómo añadir el icono (y se puede cerrar)
  function cerrado() { try { return localStorage.getItem('diario_sin_aviso') === '1'; } catch (x) { return false; } }
  if (!instalada && navigator.brave && !cerrado()) {
    var caja = document.getElementById('instalar');
    if (caja) {
      caja.innerHTML = '<b>Para tenerlo como aplicación:</b> toca el menú <b>⋮</b> (abajo o arriba a la derecha) y luego ' +
        '<b>«Añadir a pantalla de inicio»</b>. <a href="#" id="cerrar-aviso">Ya está</a>';
      caja.hidden = false;
    }
  }
  document.addEventListener('click', function (e) {
    if (e.target && e.target.id === 'cerrar-aviso') {
      e.preventDefault();
      try { localStorage.setItem('diario_sin_aviso', '1'); } catch (x) {}
      document.getElementById('instalar').hidden = true;
      return;
    }
    if (!e.target || e.target.id !== 'btn-instalar' || !pendiente) return;
    pendiente.prompt();
    pendiente.userChoice.then(function () { pendiente = null; document.getElementById('instalar').hidden = true; });
  });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) arreglar(); });
})();
