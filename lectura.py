"""Lectura dentro del Diario: el texto de cada noticia, limpio y sin nada más (ni cookies, ni anuncios).

- El texto sale del propio canal del medio (RSS completo, API de WordPress, API de RTVE) y, si el canal solo trae
  un resumen, de la página de la noticia (datos «articleBody» que publican los medios o, si no, el bloque con más
  párrafos).
- Los textos se guardan CIFRADOS (AES-GCM con una clave familiar): la web es pública, pero solo los dispositivos
  que tienen la clave (la del QR) pueden leerlos. Para el resto del mundo, el Diario solo muestra titulares.
- No hay archivo: cada edición lleva solo las noticias que se ven en ese momento (unos días) y luego desaparecen.
"""
import base64, hashlib, html, json, os, re
from html.parser import HTMLParser

BLOQUES = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote"}
EN_LINEA = {"strong": "strong", "b": "strong", "em": "em", "i": "em"}
FUERA = {"script", "style", "iframe", "noscript", "figure", "figcaption", "form", "button", "nav", "aside", "footer",
         "header", "svg", "video", "audio", "picture", "object", "embed", "select", "textarea", "template", "table"}
VACIOS = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "col", "embed", "param", "track"}
RELLENO = re.compile(r"(?i)^\s*(la entrada .{0,300} (se public[oó]|apareci[oó]) primero en|the post .{0,300} appeared first on|"
                     r"sig(ue|a) leyendo|seguir leyendo|leer m[aá]s|lee tambi[eé]n|te puede interesar|puede interesarte|m[aá]s informaci[oó]n|"
                     r"suscr[ií]bete|publicidad|comparte|compartir|s[ií]guenos|whatsapp|telegram|newsletter|bolet[ií]n|"
                     r"apoya|hazte socio|únete|ver galer[ií]a|ver v[ií]deo|escucha|descarga|cr[eé]dito|foto:|imagen:|"
                     r"\[?(…|\.\.\.)\]?$)")


RELLENO_CORTO = re.compile(r"(?i)(fuente de la imagen|pie de foto|t[ií]tulo de la imagen|^archivo\s*[-–]|suscrib|newsletter|"
                           r"bolet[ií]n|descarga (nuestra|la) app|s[ií]guenos|activa las notificaciones|haz clic|pincha aqu[ií]|"
                           r"lee aqu[ií]|ap[uú]ntate|^foto(grafía)?s?\s*[:|]|^imagen\s*[:|]|^v[ií]deo\s*[:|])")
ENTRADA = re.compile(r"(?i)^\s*(la entrada|the post|el art[ií]culo) .{0,400} (se public[oó]|apareci[oó]|appeared) (primero )?(en|on)\b")


def _partir(texto, objetivo=420):
    """Un párrafo enorme (p. ej. el «articleBody» de algunos medios) → varios párrafos por frases."""
    frases = re.split(r"(?<=[.!?»”\"])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«“\"])", texto)
    grupos, actual = [], ""
    for f in frases:
        actual = (actual + " " + f).strip()
        if len(actual) >= objetivo:
            grupos.append(actual)
            actual = ""
    if actual:
        grupos.append(actual)
    return grupos


def _esc(t):
    return html.escape(t, quote=False)


class _Limpiador(HTMLParser):
    """HTML del medio → HTML mínimo y seguro (párrafos, subtítulos, listas, citas, negritas y enlaces)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.fuera, self.abiertas, self.suelto = [], 0, [], []

    def _texto_actual(self):
        """Texto pendiente → HTML seguro (el texto se escapa; las marcas \x00<tag>\x00 son etiquetas permitidas)."""
        partes = "".join(self.suelto).split("\x00")
        self.suelto = []
        return "".join(p if k % 2 else _esc(re.sub(r"\s+", " ", p)) for k, p in enumerate(partes)).strip()

    def _vaciar_suelto(self):
        texto = self._texto_actual()
        if not re.sub(r"<[^>]+>", "", texto).strip():
            return
        self.out.append(("<p>%s</p>" if not self.abiertas else "%s") % texto)

    def handle_starttag(self, tag, attrs):
        if tag in FUERA:
            if tag not in VACIOS:
                self.fuera += 1
            return
        if self.fuera:
            return
        if tag == "br":
            if self.abiertas:
                self.suelto.append("\x00<br>\x00")
            else:
                self._vaciar_suelto()
            return
        if tag in BLOQUES:
            t = "h3" if tag[0] == "h" else tag
            # un párrafo (o un punto de lista) se cierra solo cuando empieza otro bloque
            for auto in ("p", "h3") + (("li",) if t == "li" else ()):
                if auto in self.abiertas:
                    self.handle_endtag(auto)
            self._vaciar_suelto()
            self.out.append("<%s>" % t)
            self.abiertas.append(t)
        elif tag in EN_LINEA:
            self.suelto.append("\x00<%s>\x00" % EN_LINEA[tag])
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self.suelto.append("\x00<a href=\"%s\" rel=\"noopener noreferrer\">\x00" % html.escape(href, quote=True)
                               if href.startswith("http") else "\x00<a>\x00")

    def handle_endtag(self, tag):
        if tag in FUERA:
            self.fuera = max(0, self.fuera - 1)
            return
        if self.fuera:
            return
        if tag in EN_LINEA:
            self.suelto.append("\x00</%s>\x00" % EN_LINEA[tag])
        elif tag == "a":
            self.suelto.append("\x00</a>\x00")
        elif tag in BLOQUES:
            t = "h3" if tag[0] == "h" else tag
            if t in self.abiertas:
                self._cerrar_texto()
                while self.abiertas:
                    x = self.abiertas.pop()
                    self.out.append("</%s>" % x)
                    if x == t:
                        break

    def _cerrar_texto(self):
        texto = self._texto_actual()
        if texto:
            self.out.append(texto)

    def handle_data(self, data):
        if not self.fuera:
            self.suelto.append(data.replace("\x00", ""))

    def resultado(self):
        self._vaciar_suelto()
        while self.abiertas:
            self.out.append("</%s>" % self.abiertas.pop())
        return "".join(self.out)


def limpiar_html(fuente):
    """Devuelve (html_limpio, número de letras). Quita párrafos vacíos y de relleno (compartir, suscríbete…)."""
    if not fuente:
        return "", 0
    fuente = re.sub(r"(?is)<!\[CDATA\[(.*?)\]\]>", r"\1", fuente)
    if "<" not in fuente:  # texto plano: un párrafo por línea
        fuente = "".join("<p>%s</p>" % html.escape(x) for x in re.split(r"\n\s*\n|\n", fuente) if x.strip())
    lim = _Limpiador()
    try:
        lim.feed(fuente)
        lim.close()
    except Exception:  # noqa: BLE001
        return "", 0
    salida = lim.resultado()
    salida = re.sub(r"<a>(.*?)</a>", r"\1", salida, flags=re.S)
    bloques = re.findall(r"(?s)<(p|h3|ul|ol|blockquote)>(.*?)</\1>", salida)
    limpio, letras = [], 0
    for k, (tag, dentro) in enumerate(bloques):
        plano = html.unescape(re.sub(r"<[^>]+>", "", dentro)).strip()
        if not plano or ENTRADA.search(plano):
            continue
        if tag in ("p", "h3") and (
                (len(plano) < 140 and RELLENO.search(plano)) or (len(plano) < 220 and RELLENO_CORTO.search(plano)) or
                (len(plano) < 45 and ("|" in plano or plano.endswith(":") and k == 0)) or
                (len(plano) < 30 and plano.upper() == plano and k < 2)):
            continue
        if tag == "p" and len(plano) > 900 and "<" not in dentro:
            for trozo in _partir(plano):
                limpio.append("<p>%s</p>" % _esc(trozo))
        else:
            limpio.append("<%s>%s</%s>" % (tag, dentro.strip(), tag))
        letras += len(plano)
    return "\n".join(limpio), letras


# ---------------------------------------------------------------------------------------------------------
# Texto desde la página de la noticia
# ---------------------------------------------------------------------------------------------------------
def _buscar_cuerpo(x, prof=0):
    if prof > 6:
        return None
    if isinstance(x, dict):
        tipo = x.get("@type")
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if isinstance(x.get("articleBody"), str) and len(x["articleBody"]) > 400 and \
                any(t and ("Article" in t or "Posting" in t or "Report" in t) for t in tipos):
            return x["articleBody"]
        for v in x.values():
            r = _buscar_cuerpo(v, prof + 1)
            if r:
                return r
    elif isinstance(x, list):
        for v in x:
            r = _buscar_cuerpo(v, prof + 1)
            if r:
                return r
    return None


class _Arbol(HTMLParser):
    """Árbol mínimo de la página para encontrar el bloque con más párrafos."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodos = [{"tag": "raiz", "padre": None, "hijos": [], "texto": []}]
        self.pila = [0]
        self.fuera = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "template", "iframe"):
            self.fuera += 1
            return
        if self.fuera or tag in VACIOS:
            if tag == "br" and not self.fuera:
                self.nodos[self.pila[-1]]["texto"].append("\n")
            return
        clase = " ".join(v for k, v in attrs if k in ("class", "id") and v).lower()
        nodo = {"tag": tag, "padre": self.pila[-1], "hijos": [], "texto": [], "clase": clase}
        self.nodos.append(nodo)
        i = len(self.nodos) - 1
        self.nodos[self.pila[-1]]["hijos"].append(("n", i))
        self.pila.append(i)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template", "iframe"):
            self.fuera = max(0, self.fuera - 1)
            return
        if self.fuera:
            return
        for k in range(len(self.pila) - 1, 0, -1):
            if self.nodos[self.pila[k]]["tag"] == tag:
                del self.pila[k:]
                return

    def handle_data(self, data):
        if not self.fuera:
            n = self.nodos[self.pila[-1]]
            n["texto"].append(data)
            n["hijos"].append(("t", data))


def _texto_nodo(arbol, i):
    out = []
    for tipo, v in arbol.nodos[i]["hijos"]:
        out.append(v if tipo == "t" else _texto_nodo(arbol, v))
    return "".join(out)


def _html_nodo(arbol, i):
    n = arbol.nodos[i]
    dentro = "".join(_esc(v) if t == "t" else _html_nodo(arbol, v) for t, v in n["hijos"])
    if n["tag"] in ("p", "h2", "h3", "h4", "li", "ul", "ol", "blockquote", "strong", "b", "em", "i"):
        return "<%s>%s</%s>" % (n["tag"], dentro, n["tag"])
    return dentro


MALOS = re.compile(r"comment|coment|related|relacionad|sidebar|footer|menu|newsletter|share|social|cookie|"
                   r"publi|banner|promo|subscribe|suscri|recomend|outbrain|taboola|tags|etiquetas|autor-bio")


def extraer_de_pagina(pagina):
    """HTML de la página → (html_limpio, letras). Primero «articleBody»; si no, el bloque con más párrafos."""
    for bloque in re.findall(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', pagina):
        try:
            cuerpo = _buscar_cuerpo(json.loads(bloque.strip()))
        except ValueError:
            continue
        if cuerpo:
            cuerpo = html.unescape(cuerpo)
            if "<p" in cuerpo:
                return limpiar_html(cuerpo)
            return limpiar_html("".join("<p>%s</p>" % html.escape(x.strip()) for x in re.split(r"\n+", cuerpo) if x.strip()))
    arbol = _Arbol()
    try:
        arbol.feed(pagina[:3_000_000])
    except Exception:  # noqa: BLE001
        return "", 0
    puntos = {}
    for i, n in enumerate(arbol.nodos):
        if n["tag"] != "p":
            continue
        largo = len(re.sub(r"\s+", " ", _texto_nodo(arbol, i)).strip())
        if largo < 60:
            continue
        j, peso = n["padre"], 1.0
        while j is not None and peso > 0.2:
            nodo = arbol.nodos[j]
            if MALOS.search(nodo.get("clase", "")):
                puntos[j] = puntos.get(j, 0) - largo
            else:
                puntos[j] = puntos.get(j, 0) + largo * peso
            j, peso = nodo["padre"], peso * 0.6
    if not puntos:
        return "", 0
    mejor = max(puntos, key=puntos.get)
    trozos = []

    def recorrer(i):
        n = arbol.nodos[i]
        if MALOS.search(n.get("clase", "")) and i != mejor:
            return
        if n["tag"] in ("p", "h2", "h3", "h4", "blockquote", "ul", "ol"):
            trozos.append(_html_nodo(arbol, i))
            return
        for t, v in n["hijos"]:
            if t == "n":
                recorrer(v)
    recorrer(mejor)
    return limpiar_html("".join(trozos))


# ---------------------------------------------------------------------------------------------------------
# Paquete cifrado
# ---------------------------------------------------------------------------------------------------------
def id_de(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def cifrar(datos, clave, iteraciones=150_000):
    """AES-256-GCM con clave derivada (PBKDF2-SHA256). Lo descifra el navegador con WebCrypto (leer.js)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    sal, iv = os.urandom(16), os.urandom(12)
    k = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, iteraciones, 32)
    cifrado = AESGCM(k).encrypt(iv, datos, None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"v": 1, "iter": iteraciones, "sal": b64(sal), "iv": b64(iv), "datos": b64(cifrado)}
