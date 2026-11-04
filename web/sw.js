/* El Diario de Paco: guarda la última edición para leerla sin conexión. Solo toca las páginas del propio diario. */
var CACHE = 'diario-v4';
var BASICOS = ['./', 'index.html', 'leer.html', 'estilo.css', 'diario.js', 'leer.js', 'icono-192.png', 'fonts/Lora-Regular.ttf',
  'fonts/Lora-SemiBold.ttf', 'fonts/Poppins-Medium.ttf', 'fonts/Poppins-Bold.ttf'];
self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(BASICOS); }).catch(function () {}));
  self.skipWaiting();
});
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (e) {
  var u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin || /\.apk$/.test(u.pathname)) return;
  // primero internet (noticias frescas); sin conexión, lo último guardado
  e.respondWith(fetch(e.request).then(function (r) {
    if (r && r.ok) { var copia = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copia); }); }
    return r;
  }).catch(function () {
    return caches.match(e.request, { ignoreSearch: true }).then(function (r) {
      return r || (e.request.mode === 'navigate' ? caches.match('index.html') : undefined);
    });
  }));
});
