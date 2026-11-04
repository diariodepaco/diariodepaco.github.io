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
  document.addEventListener('click', function (e) {
    if (!e.target || e.target.id !== 'btn-instalar' || !pendiente) return;
    pendiente.prompt();
    pendiente.userChoice.then(function () { pendiente = null; document.getElementById('instalar').hidden = true; });
  });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) arreglar(); });
})();
