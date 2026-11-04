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

  // Noticias guardadas (cifradas): se descifran aquí, una vez por sesión
  function b64(t) { var x = atob(t), a = new Uint8Array(x.length); for (var i = 0; i < x.length; i++) a[i] = x.charCodeAt(i); return a; }
  window.diarioLecturas = function () {
    var k = clave();
    if (!k || !window.crypto || !crypto.subtle || !window.fetch) return Promise.reject(new Error('sin clave'));
    var edicion = document.body.getAttribute('data-lect') || '';
    try {
      var g = JSON.parse(sessionStorage.getItem('diario_lecturas') || 'null');
      if (g && edicion && g.sal === edicion) return Promise.resolve(g.lista);
    } catch (x) {}
    return fetch('lecturas.json').then(function (r) { return r.json(); }).then(function (p) {
      try {
        var g2 = JSON.parse(sessionStorage.getItem('diario_lecturas') || 'null');
        if (g2 && g2.sal === p.sal) return g2.lista;
      } catch (x) {}
      return crypto.subtle.importKey('raw', new TextEncoder().encode(k), 'PBKDF2', false, ['deriveKey']).then(function (base) {
        return crypto.subtle.deriveKey({ name: 'PBKDF2', salt: b64(p.sal), iterations: p.iter, hash: 'SHA-256' },
          base, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
      }).then(function (llave) {
        return crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(p.iv) }, llave, b64(p.datos));
      }).then(function (claro) {
        var lista = JSON.parse(new TextDecoder().decode(claro));
        try { sessionStorage.setItem('diario_lecturas', JSON.stringify({ sal: p.sal, lista: lista })); } catch (x) {}
        return lista;
      });
    });
  };

  // Fotos en las listas (solo en los aparatos con la llave): grande en la primera de cada bloque de la portada
  function ponerFotos() {
    if (!clave() || !document.querySelector('a[data-leer]') || document.getElementById('lectura')) return;
    window.diarioLecturas().then(function (lista) {
      var notas = document.querySelectorAll('article.nota');
      for (var i = 0; i < notas.length; i++) {
        var a = notas[i].querySelector('a[data-leer]');
        var n = a && lista[a.getAttribute('data-leer')];
        if (!n || !n.i || notas[i].querySelector('img')) continue;
        var primera = notas[i].parentNode.classList.contains('bloque') &&
          notas[i].parentNode.querySelector('article.nota') === notas[i];
        var enlace = document.createElement('a');
        enlace.href = a.getAttribute('href');
        enlace.setAttribute('data-leer', a.getAttribute('data-leer'));
        enlace.className = primera ? 'foto-grande' : 'miniatura';
        var img = document.createElement('img');
        img.alt = '';
        img.loading = 'lazy';
        img.referrerPolicy = 'no-referrer';
        img.addEventListener('error', function () { var e = this.parentNode; if (e && e.parentNode) e.parentNode.removeChild(e); });
        img.src = n.i;
        enlace.appendChild(img);
        if (primera) notas[i].insertBefore(enlace, notas[i].firstChild);
        else notas[i].insertBefore(enlace, notas[i].querySelector('h3'));
      }
    }).catch(function () {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ponerFotos); else ponerFotos();

  // Botón ↻: trae la última edición y, si hace rato que no se actualiza, le pide a GitHub una edición nueva
  function avisar(html) {
    var aviso = document.getElementById('aviso');
    if (aviso) { aviso.innerHTML = html; aviso.hidden = false; window.scrollTo(0, 0); }
  }
  function esperarEdicionNueva(antes, inicio) {
    fetch('index.html?_=' + Date.now(), { cache: 'no-store' }).then(function (r) { return r.text(); }).then(function (t) {
      var m2 = /data-gen="(\d+)"/.exec(t);
      if (m2 && +m2[1] > antes) { avisar('¡Ya están las noticias nuevas!'); setTimeout(function () { location.reload(); }, 800); return; }
      if (Date.now() - inicio > 8 * 60000) { location.reload(); return; }
      setTimeout(function () { esperarEdicionNueva(antes, inicio); }, 20000);
    }).catch(function () { setTimeout(function () { esperarEdicionNueva(antes, inicio); }, 20000); });
  }
  function horaDe(ts) { var d = new Date(ts * 1000); return d.getHours() + ':' + ('0' + d.getMinutes()).slice(-2); }
  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest ? e.target.closest('#actualizar') : null;
    if (!b) return;
    e.preventDefault();
    b.classList.add('girando');
    var gen = +document.body.getAttribute('data-gen') || 0, ahora = Date.now() / 1000, ultima = 0;
    try { ultima = +localStorage.getItem('diario_pedida') || 0; } catch (x) {}
    // ¿hay ya una edición más nueva publicada? entonces basta con traerla
    fetch('index.html?_=' + Date.now(), { cache: 'no-store' }).then(function (r) { return r.text(); }).then(function (t) {
      var m2 = /data-gen="(\d+)"/.exec(t), publicada = m2 ? +m2[1] : gen;
      if (publicada > gen) { location.reload(); return; }
      if (ahora - ultima < 10 * 60) {
        avisar('Ya se están buscando noticias nuevas… en un par de minutos se pondrá al día sola.');
        esperarEdicionNueva(gen, Date.now());
        return;
      }
      if (ahora - gen < 10 * 60 || !clave()) {
        b.classList.remove('girando');
        avisar('Ya tienes las noticias más recientes (de las ' + horaDe(gen) + '). El Diario se renueva solo cada dos horas.');
        return;
      }
      return window.diarioLecturas().then(function (lista) {
        var a = lista._actualizar;
        if (!a || !a.t) throw new Error('sin permiso');
        return fetch('https://api.github.com/repos/' + a.r + '/actions/workflows/' + a.w + '/dispatches', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + a.t, 'Accept': 'application/vnd.github+json' },
          body: JSON.stringify({ ref: 'main' })
        });
      }).then(function (r) {
        if (!r.ok) throw new Error('GitHub ' + r.status);
        try { localStorage.setItem('diario_pedida', String(Math.floor(Date.now() / 1000))); } catch (x) {}
        avisar('Buscando noticias nuevas… tarda unos tres minutos. Puedes seguir leyendo: la página se pondrá al día sola.');
        esperarEdicionNueva(gen, Date.now());
      });
    }).catch(function () {
      b.classList.remove('girando');
      avisar('Ahora mismo no se pueden pedir noticias nuevas (¿hay internet?). El Diario se renueva solo cada dos horas.');
    });
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
