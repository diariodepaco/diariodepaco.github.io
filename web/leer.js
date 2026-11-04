/* El Diario de Paco: muestra una noticia guardada dentro del Diario (texto cifrado con la clave familiar). */
(function () {
  var caja = document.getElementById('lectura');
  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  function esc(t) { var d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; }
  function b64(t) { var s = atob(t), a = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i); return a; }
  function mensaje(html) { caja.innerHTML = '<p class="vacio">' + html + '</p><p><a class="mas" href="index.html">Volver al Diario</a></p>'; }
  function clave() { try { return localStorage.getItem('diario_clave'); } catch (x) { return null; } }
  function fecha(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    return d.getDate() + ' de ' + MESES[d.getMonth()] + ', ' + d.getHours() + ':' + ('0' + d.getMinutes()).slice(-2);
  }
  function pintar(n) {
    document.title = n.t + ' · El Diario de Paco';
    var otros = esc((n.o || []).map(function (x) { return x[0]; }).join(', '));
    caja.innerHTML =
      '<a class="volver" href="index.html" id="volver">‹ Volver</a>' +
      '<div class="meta"><span class="medio">' + esc(n.f) + '</span>' + (n.d ? ' · ' + esc(fecha(n.d)) : '') +
      (n.s ? ' · ' + esc(n.s) : '') + '</div>' +
      '<h1>' + esc(n.t) + '</h1>' +
      '<div class="cuerpo">' + n.h + '</div>' +
      '<div class="origen">Noticia de <b>' + esc(n.f) + '</b>' + (n.d ? ', publicada el ' + esc(fecha(n.d)) : '') + '.' +
      (otros ? '<br>También lo cuentan: ' + otros : '') + '</div>' +
      '<a class="mas" href="index.html" id="volver2">‹ Volver al Diario</a>';
    var volver = function (e) {
      if (document.referrer && document.referrer.indexOf(location.origin) === 0 && history.length > 1) { e.preventDefault(); history.back(); }
    };
    document.getElementById('volver').onclick = volver;
    document.getElementById('volver2').onclick = volver;
    window.scrollTo(0, 0);
  }
  function abrir(lista) {
    var id = (location.hash || '').slice(1), n = lista[id];
    if (!n) { mensaje('Esta noticia ya no está en el Diario (solo se guardan las de los últimos días).'); return; }
    pintar(n);
  }
  var k = clave();
  if (!k || !window.crypto || !crypto.subtle) { mensaje('Este aparato todavía no tiene la llave para leer las noticias. Escanea otra vez el código QR del Diario y listo.'); return; }
  fetch('lecturas.json', { cache: 'no-cache' }).then(function (r) { return r.json(); }).then(function (p) {
    var guardado = null;
    try { guardado = JSON.parse(sessionStorage.getItem('diario_lecturas') || 'null'); } catch (x) {}
    if (guardado && guardado.sal === p.sal) { abrir(guardado.lista); return; }
    var enc = new TextEncoder();
    return crypto.subtle.importKey('raw', enc.encode(k), 'PBKDF2', false, ['deriveKey']).then(function (base) {
      return crypto.subtle.deriveKey({ name: 'PBKDF2', salt: b64(p.sal), iterations: p.iter, hash: 'SHA-256' },
        base, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
    }).then(function (llave) {
      return crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(p.iv) }, llave, b64(p.datos));
    }).then(function (claro) {
      var lista = JSON.parse(new TextDecoder().decode(claro));
      try { sessionStorage.setItem('diario_lecturas', JSON.stringify({ sal: p.sal, lista: lista })); } catch (x) {}
      abrir(lista);
    });
  }).catch(function () {
    mensaje('No se ha podido abrir la noticia. Comprueba la conexión, o vuelve al Diario y tócala otra vez.');
  });
  window.addEventListener('hashchange', function () { location.reload(); });
})();
