#!/usr/bin/env python3
"""El Diario de Paco: genera una web de noticias limpia a partir de canales RSS/Atom.

Solo usa la biblioteca estándar de Python (3.9 o superior).
    python diario.py                    -> crea la web en la carpeta _site
    python diario.py --out carpeta      -> en otra carpeta
    python diario.py --muestras dir     -> sin internet: lee los canales de dir/<nombre>.xml (pruebas)

Qué hace en cada ejecución:
 1. Lee las fuentes de fuentes.json. Para cada una prueba sus canales RSS y, si ninguno funciona,
    busca el canal en la portada del medio (autodescubrimiento).
 2. Descarta titulares cebo, publicidad, deporte, opinión, directos y noticias repetidas.
 3. Ordena por secciones y escribe páginas HTML estáticas (sin anuncios, sin cookies, sin rastreo)
    y un informe técnico (estado.html / estado.json) para ver qué fuentes fallan.
"""
import argparse, concurrent.futures, datetime as dt, email.utils, gzip, html, json, os, re, shutil
import sys, unicodedata, urllib.parse, urllib.request, zlib
import xml.etree.ElementTree as ET

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Atlantic/Canary")
except Exception:  # pragma: no cover - sin base de zonas horarias
    TZ = dt.timezone.utc

AQUI = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (compatible; DiarioDePaco/1.0; lector RSS personal; +https://ansertoken.github.io/diario-paco/)"
AHORA = dt.datetime.now(dt.timezone.utc)

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]

# ----------------------------------------------------------------------------------------------
# Filtros. Se comparan sin tildes y en minúsculas.
# ----------------------------------------------------------------------------------------------
CEBO = [
    r"no te (lo )?(vas a creer|creeras|pierdas)", r"no (vas a )?creer", r"lo que (nadie|no) te (cuenta|han contado|dicen|dira)",
    r"\besto es lo que\b", r"\bes(to|te) es el\b.*\bque\b.*\b(nadie|todos)\b", r"^asi (es|son|fue|ha sido|sera|seran|ha quedado|queda|luce|reacciona)\b",
    r"\bte (sorprendera|dejara|explicamos|contamos)\b", r"\bviral\b", r"\balucina", r"\bincreible\b", r"\bbrutal\b", r"\bimpactante\b",
    r"\bel truco\b", r"\b(los|las) trucos?\b", r"\bnadie (lo )?esperaba\b", r"\bque (pasa|ocurre|sucede) si\b",
    r"\bcomo (saber|consultar|comprobar|ver online|ver en directo|ver gratis)\b", r"\bdonde ver\b", r"\ba que hora\b",
    r"\b(chollo|chollos|rebajas|black friday|cyber monday|prime day|cupones?|codigos? de descuento)\b", r"\b(mejores|las) ofertas\b", r"\bdescuentos? de hasta\b", r"\bhoroscopo\b",
    r"\bpatrocinad", r"\bpublirreportaje\b", r"\bcontenido de marca\b", r"\ben colaboracion con\b", r"\bbranded\b",
    r"^\d+ (cosas|claves|trucos|razones|consejos|motivos|lugares|series|peliculas|alimentos|senales|errores|preguntas)\b",
    r"\btodo lo que (debes|tienes que|necesitas|hay que) saber\b", r"\bminuto a minuto\b", r"^(directo|en directo|ultima hora)\b",
    r"\b(directo|en directo)\s*[|:]", r"\(directo\)", r"\bla respuesta te\b", r"\bten cuidado\b", r"\bojo con\b",
    r"\bpor que (todo el mundo|nadie)\b", r"\bel motivo (es|por el que)\b", r"\bla razon por la que\b", r"\bsecreto (de|para)\b",
    r"\bresultados? (de la )?(loteria|primitiva|bonoloto|euromillones|once|el gordo)\b", r"\bcomprobar (la )?loteria\b",
    r"!!|\?!|!\?", r"\bmeme", r"\breaccion(a|an)? en redes\b", r"\bincendia las redes\b", r"\barrasa\b", r"\bzasca\b",
]
CEBO = [re.compile(p) for p in CEBO]

DEPORTE_URL = re.compile(r"/(deportes?|futbol|baloncesto|motor|motociclismo|tenis|ciclismo|golf|atletismo|balonmano|"
                         r"natacion|vela|lucha-canaria|formula-1|f1|motogp|olimpicos?|polideportivo|mas-deporte|"
                         r"ud-las-palmas|cd-tenerife|liga|champions)(/|-|$)", re.I)
DEPORTE_TXT = re.compile(
    r"\b(futbol|futbolista|futbolistas|baloncesto|laliga|la liga|champions|europa league|conference league|ud las palmas|"
    r"cd tenerife|real madrid|fc barcelona|barca|atletico de madrid|athletic club|sevilla fc|valencia cf|real betis|"
    r"villarreal|real sociedad|osasuna|rayo vallecano|mundial de futbol|mundial de clubes|eurocopa|copa del rey|supercopa|"
    r"formula 1|formula uno|motogp|grand prix|gran premio de|tenis|tenista|nadal|alcaraz|djokovic|roland garros|wimbledon|"
    r"open de australia|us open|copa davis|nba|acb|euroliga|eurobasket|dreamland|cb gran canaria|la laguna tenerife|"
    r"lucha canaria|gol|goles|golazo|fichaje|fichajes|jugador|jugadora|jugadores|jugadoras|delantero|centrocampista|portero del|entrenador del|seleccionador|"
    r"juegos olimpicos|olimpiadas|paralimpicos|tour de francia|vuelta a espana|giro de italia|ciclista|ciclistas|"
    r"balonmano|waterpolo|medalla de (oro|plata|bronce)|liga f|primera rfef|segunda division|primera division|"
    r"jornada \d+ de|partidazo|derbi)\b")
DEPORTE_CAT = re.compile(r"^(deportes?|futbol|baloncesto|motor|tenis|ciclismo|golf|atletismo|balonmano|"
                         r"lucha canaria|formula 1|motogp|polideportivo|ud las palmas|cd tenerife|mas deporte)$")
OPINION_URL = re.compile(r"/(opinion|opiniones|tribuna|tribunas|columnas?|editorial|editoriales|blogs?/opinion|"
                         r"cartas-al-director|humor|vinetas?)(/|-|$)", re.I)
OPINION_CAT = re.compile(r"^(opinion|opiniones|tribuna|columna|columnas|editorial|cartas al director|vineta|humor|"
                         r"publicidad|patrocinado|contenido patrocinado|branded content|ofertas|compras|horoscopo)$")

GALDAR = re.compile(r"\b(galdar|galdense|galdenses|barrial|sardina del norte|cueva pintada|guayarmina|"
                    r"santiago de los caballeros)\b")
GRAN_CANARIA = re.compile(r"\b(gran canaria|grancanari|las palmas|galdar|telde|arucas|agaete|guia|moya|firgas|"
                          r"teror|ingenio|aguimes|mogan|tejeda|artenara|valsequillo|santa brigida|san bartolome de tirajana|"
                          r"maspalomas|vecindario|cabildo grancanario)\b")
ASTRO = re.compile(r"\b(astronom\w*|astrofisic\w*|planeta\w*|exoplaneta\w*|galaxia\w*|estrella\w*|universo|cosmos|"
                   r"cosmic\w*|nasa|esa|telescopio\w*|cometa\w*|asteroide\w*|meteor\w*|eclipse\w*|luna|lunar|marte|"
                   r"jupiter|saturno|venus|mercurio|neptuno|urano|pluton|sol|solar|nebulosa\w*|agujero negro|agujeros negros|"
                   r"espacial\w*|astronauta\w*|cohete\w*|satelite\w*|orbita\w*|iac|roque de los muchachos|teide|"
                   r"arqueolog\w*|yacimiento\w*|civilizacion\w*|egipt\w*|faraon\w*|maya\w*|momia\w*|aborigen\w*)\b")
HISTORIA_KW = re.compile(r"\b(arqueolog\w*|historia|historiador\w*|historic\w*|antigu\w*|roman[oa]s?|imperio\w*|egipt\w*|"
                         r"faraon\w*|medieval\w*|edad media|prehistori\w*|neandert\w*|yacimiento\w*|civilizacion\w*|"
                         r"maya\w*|inca\w*|azteca\w*|guanche\w*|aborigen\w*|momia\w*|excavacion\w*|paleolitic\w*|"
                         r"neolitic\w*|bronce|hierro|siglo [ivxlc]+|griego\w*|grecia|mesopotamia\w*|fenici\w*|vikingo\w*|"
                         r"pirami\w*|templo\w*|ruinas|tumba\w*|necropolis|papiro\w*|epigraf\w*|monarqui\w*|guerra civil|"
                         r"segunda guerra mundial|primera guerra mundial|edad de (la )?(piedra|madera)|"
                         r"edad del (bronce|hierro)|arqueologic\w*)\b")
CIENCIA_KW = re.compile(r"\b(astronom\w*|planeta\w*|galaxia\w*|estrella\w*|universo|nasa|telescopio\w*|cometa\w*|"
                        r"asteroide\w*|luna|marte|jupiter|saturno|espacial\w*|cosmos|fisic\w*|quimic\w*|biolog\w*|genetic\w*|"
                        r"genoma\w*|evolucion\w*|dinosaurio\w*|volcan\w*|terremoto\w*|clima\w*|climatic\w*|especie\w*|"
                        r"celula\w*|matematic\w*|cerebro\w*|virus|bacteria\w*|fosil\w*|lago\w*|rio|rios|"
                        r"oceano\w*|ecolog\w*|vacuna\w*|neurona\w*|atomo\w*|particula\w*|cuantic\w*|venus|mercurio)\b")
TROCITOS_FINALES = [
    r"\s*(la entrada|el post|the post|el art[ií]culo)\s.+?\s(se public[oó] primero en|apareci[oó] primero en|appeared first on|se public[oó] en)\s.+$",
    r"\s*(seguir leyendo|leer m[aá]s|sigue leyendo|continue reading|lee la noticia completa|ver m[aá]s|m[aá]s informaci[oó]n)\s*(\.|:|»|›|→)?\s*$",
]
VACIAS = set("""a al algo algun alguna algunas alguno algunos ante antes aqui asi aun bajo bien cada como con contra cual
cuales cuando de del desde donde dos el ella ellas ellos en entre era eran es esa esas ese eso esos esta estaba estado
estan estar estas este esto estos fue fueron ha han hasta hay la las le les lo los mas me mi mientras muy nada ni no
nos nuestra nuestro o os otra otras otro otros para pero poco por porque que quien se sea segun ser si sido sin sobre
solo son su sus tambien tan tanto te tiene tienen todo todos tras tu un una uno unos unas ya año años dice dicen
según tras hoy ayer este esta nuevo nueva nuevos nuevas puede pueden hace""".split())


def sin_tildes(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("ç", "c")


def limpiar_texto(t, maximo=None):
    if not t:
        return ""
    t = re.sub(r"(?is)<(script|style|figure|figcaption|iframe|noscript)\b.*?</\1>", " ", t)
    t = re.sub(r"(?s)<br\s*/?>|</p>|</div>|</li>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    for _ in range(2):
        if "&" in t:
            t = html.unescape(t)
    t = t.replace("\xa0", " ").replace("​", "")
    t = re.sub(r"\s+", " ", t).strip()
    for p in TROCITOS_FINALES:
        t = re.sub(p, "", t, flags=re.I).strip()
    t = re.sub(r"\s*(\[\s*(…|\.\.\.)\s*\]|\.\.\.|…)\s*$", "…", t)
    if maximo and len(t) > maximo:
        corte = t.rfind(" ", 0, maximo)
        t = t[:corte if corte > maximo * 0.6 else maximo].rstrip(",;:—–- ") + "…"
    return t


# ----------------------------------------------------------------------------------------------
# Descarga y lectura de canales
# ----------------------------------------------------------------------------------------------
def descargar(url, tiempo=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, text/html;q=0.8, */*;q=0.5",
        "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=tiempo) as r:
        datos = r.read(10_000_000)
        enc = (r.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip" or datos[:2] == b"\x1f\x8b":
            datos = gzip.decompress(datos)
        elif enc == "deflate":
            try:
                datos = zlib.decompress(datos)
            except zlib.error:
                datos = zlib.decompress(datos, -zlib.MAX_WBITS)
        return datos, r.geturl(), r.headers.get_content_type()


def local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def hijo(el, *nombres):
    for c in el:
        if local(c.tag) in nombres:
            return c
    return None


def texto_de(el):
    if el is None:
        return ""
    return "".join(el.itertext()) if len(el) else (el.text or "")


def fecha_de(t):
    t = (t or "").strip()
    if not t:
        return None
    try:
        d = email.utils.parsedate_to_datetime(t)
    except Exception:
        d = None
    if d is None:
        m = re.match(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?", t)
        if not m:
            return None
        txt = m.group(1) + "T" + (m.group(2) or "00:00:00")
        if len(txt) == 16:
            txt += ":00"
        zona = m.group(3) or "Z"
        zona = "+00:00" if zona == "Z" else (zona if ":" in zona else zona[:3] + ":" + zona[3:])
        try:
            d = dt.datetime.fromisoformat(txt + zona)
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=TZ)
    d = d.astimezone(dt.timezone.utc)
    return min(d, AHORA)


def xml_a_arbol(datos):
    datos = datos.lstrip(b"\xef\xbb\xbf \t\r\n")
    try:
        return ET.fromstring(datos)
    except ET.ParseError:
        pass
    txt = datos.decode("utf-8", "replace")
    txt = re.sub(r"^<\?xml[^>]*\?>", "", txt.strip())
    txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
    txt = re.sub(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#x[0-9a-fA-F]{1,6});)", "&amp;", txt)
    # entidades HTML que XML no conoce (&nbsp; &oacute; ...) -> caracteres
    txt = re.sub(r"&([a-zA-Z][a-zA-Z0-9]{1,31});",
                 lambda m: m.group(0) if m.group(1) in ("amp", "lt", "gt", "quot", "apos") else html.unescape(m.group(0)), txt)
    try:
        return ET.fromstring(txt.encode("utf-8"))
    except ET.ParseError:
        return None


def leer_canal(datos, base=""):
    """Devuelve una lista de dicts {t, u, d, r, cats}. Acepta RSS 2.0, RSS 1.0 (RDF) y Atom."""
    raiz = xml_a_arbol(datos)
    if raiz is None:
        return leer_canal_a_mano(datos, base)
    notas = []
    if local(raiz.tag) == "feed":
        for e in raiz:
            if local(e.tag) != "entry":
                continue
            enlace = ""
            for l in e:
                if local(l.tag) == "link" and l.get("rel", "alternate") == "alternate" and l.get("href"):
                    enlace = l.get("href")
                    break
            resumen = texto_de(hijo(e, "summary")) or texto_de(hijo(e, "content"))
            cats = [c.get("term") or c.get("label") or "" for c in e if local(c.tag) == "category"]
            notas.append({"t": texto_de(hijo(e, "title")), "u": enlace,
                          "d": fecha_de(texto_de(hijo(e, "published")) or texto_de(hijo(e, "updated"))),
                          "r": resumen, "cats": cats})
    else:
        for it in raiz.iter():
            if local(it.tag) != "item":
                continue
            enlace = texto_de(hijo(it, "link")).strip()
            if not enlace:
                g = hijo(it, "guid")
                if g is not None and (g.get("isPermaLink", "true") != "false") and (g.text or "").startswith("http"):
                    enlace = g.text.strip()
            fecha = None
            for nombre in ("pubdate", "date", "published", "updated", "issued"):
                f = hijo(it, nombre)
                if f is not None and (f.text or "").strip():
                    fecha = fecha_de(f.text)
                    if fecha:
                        break
            resumen = texto_de(hijo(it, "description")) or texto_de(hijo(it, "encoded"))
            cats = [texto_de(c) for c in it if local(c.tag) in ("category", "subject")]
            notas.append({"t": texto_de(hijo(it, "title")), "u": enlace, "d": fecha, "r": resumen, "cats": cats})
    for n in notas:
        n["u"] = urllib.parse.urljoin(base, n["u"].strip()) if n["u"] else ""
    return notas[:80]


def titulo_canal(datos):
    m = re.search(rb"(?is)<(?:channel|feed)\b.*?<title[^>]*>(.*?)</title>", datos[:20000])
    if not m:
        return ""
    t = re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1).decode("utf-8", "replace"))
    return limpiar_texto(t, 120)


def leer_canal_a_mano(datos, base=""):
    """Último recurso para canales con XML roto."""
    txt = datos.decode("utf-8", "replace")
    notas = []
    for bloque in re.findall(r"(?is)<(?:item|entry)\b.*?</(?:item|entry)>", txt)[:80]:
        def campo(*nombres):
            for n in nombres:
                m = re.search(r"(?is)<%s\b[^>]*>(.*?)</%s>" % (n, n), bloque)
                if m:
                    v = m.group(1)
                    v = re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", r"\1", v)
                    return v.strip()
            return ""
        enlace = campo("link")
        if not enlace:
            m = re.search(r'(?is)<link\b[^>]*href=["\']([^"\']+)', bloque)
            enlace = m.group(1) if m else ""
        notas.append({"t": campo("title"), "u": urllib.parse.urljoin(base, html.unescape(enlace)),
                      "d": fecha_de(campo("pubDate", "dc:date", "published", "updated")),
                      "r": campo("description", "summary", "content:encoded", "content"),
                      "cats": [re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", r"\1", c) for c in
                               re.findall(r"(?is)<category\b[^>]*>(.*?)</category>", bloque)]})
    return notas


def descubrir(home):
    """Busca en la portada del medio los enlaces a sus canales RSS/Atom."""
    datos, final, _ = descargar(home)
    pagina = datos[:600_000].decode("utf-8", "replace")
    candidatos = []
    for m in re.finditer(r"(?is)<link\b[^>]*>", pagina):
        etiqueta = m.group(0)
        if re.search(r"(?i)rel\s*=\s*[\"']?[^\"'>]*alternate", etiqueta) and \
                re.search(r"(?i)type\s*=\s*[\"']?application/(rss|atom|rdf)\+xml", etiqueta):
            h = re.search(r"(?i)href\s*=\s*[\"']([^\"']+)", etiqueta)
            if h:
                candidatos.append(urllib.parse.urljoin(final, html.unescape(h.group(1))))
    for m in re.finditer(r"(?i)href\s*=\s*[\"']([^\"']*(?:/rss|/feed|\.rss|rss\.xml|feed\.xml|atom\.xml)[^\"']*)[\"']", pagina):
        candidatos.append(urllib.parse.urljoin(final, html.unescape(m.group(1))))
    ruta = urllib.parse.urlparse(final).path.rstrip("/")
    for sufijo in ("/feed/", "/rss/", "/rss.xml", "/feed.xml", "/index.xml"):
        candidatos.append(urllib.parse.urljoin(final, ruta + sufijo))
    vistos, buenos = set(), []
    for c in candidatos:
        if c in vistos or re.search(r"(?i)comment|oembed|wp-json|/tag/|/autor/|/author/", c):
            continue
        vistos.add(c)
        buenos.append(c)
    # primero los que pertenecen a la misma sección que la portada indicada
    seccion = [c for c in buenos if ruta and ruta.lower() in urllib.parse.urlparse(c).path.lower() + urllib.parse.urlparse(c).query.lower()]
    return seccion + [c for c in buenos if c not in seccion]


def cargar_fuente(f, muestras=None):
    estado = {"nombre": f["nombre"], "ok": False, "canal": None, "leidas": 0, "errores": [], "autodescubierto": False}
    if muestras is not None:
        ruta = os.path.join(muestras, re.sub(r"[^a-z0-9]+", "_", sin_tildes(f["nombre"])).strip("_") + ".xml")
        if not os.path.exists(ruta):
            estado["errores"].append("sin muestra " + os.path.basename(ruta))
            return f, [], estado
        notas = leer_canal(open(ruta, "rb").read(), f.get("home", ""))
        estado.update(ok=bool(notas), canal="muestra:" + os.path.basename(ruta), leidas=len(notas))
        return f, notas, estado
    intentos = list(f.get("feeds") or [])
    probados = set()

    def probar(url, nivel=0):
        probados.add(url)
        try:
            datos, final, tipo = descargar(url)
        except Exception as e:  # noqa: BLE001
            estado["errores"].append("%s → %s" % (url, str(e)[:120]))
            return None
        cabeza = datos[:4000].lstrip().lower()
        parece_web = cabeza.startswith(b"<!doctype html") or cabeza.startswith(b"<html")
        notas = [] if parece_web else [n for n in leer_canal(datos, final) if n["t"].strip() and n["u"].startswith("http")]
        if notas:
            titulo = titulo_canal(datos)
            exigido = f.get("titulo_canal")
            if exigido and not re.search(exigido, sin_tildes(titulo)):
                estado["errores"].append("%s → es otro canal («%s»)" % (url, titulo))
                return None
            estado.setdefault("titulos", []).append(titulo)
            estado.update(ok=True, canal=url, leidas=len(notas))
            return notas
        if parece_web:
            pista = re.sub(r"\s+", " ", limpiar_texto(re.sub(r"(?is)<head\b.*?</head>", " ", datos[:20000].decode("utf-8", "replace"))))[:60]
            estado["errores"].append("%s → es una página web, no un canal (%s · «%s»)" % (url, tipo, pista))
            # página que enumera los canales del medio (p. ej. «/RSS»): se prueban sus enlaces
            if nivel == 0 and re.search(r"(?i)rss|feed|sindica", url):
                pagina = datos[:600_000].decode("utf-8", "replace")
                enlaces = []
                for m in re.finditer(r"(?i)href\s*=\s*[\"']([^\"']+)[\"']", pagina):
                    h = urllib.parse.urljoin(final, html.unescape(m.group(1)))
                    if re.search(r"(?i)(rss|feed|atom|\.xml)", h) and h not in probados and h not in enlaces and \
                            not re.search(r"(?i)comment|feedly|feedburner\.google|/add\?|subscribe|netvibes|inoreader", h):
                        enlaces.append(h)
                estado["canales_en_pagina"] = enlaces[:30]
                for h in enlaces[:6]:
                    sub = probar(h, 1)
                    if sub:
                        return sub
            return None
        estado["errores"].append("%s → canal vacío o ilegible" % url)
        return None

    if f.get("unir"):
        # fuente con varios canales que se suman (p. ej. varias secciones de un mismo medio)
        todas, canales = [], []
        for url in intentos:
            notas = probar(url)
            if notas:
                todas += notas
                canales.append(url)
        if todas:
            estado.update(ok=True, canal=" + ".join(canales), leidas=len(todas))
            return f, todas, estado
    for url in intentos:
        notas = probar(url)
        if notas:
            return f, notas, estado
    if f.get("home"):
        try:
            candidatos = descubrir(f["home"])
        except Exception as e:  # noqa: BLE001
            estado["errores"].append("portada %s → %s" % (f["home"], str(e)[:120]))
            candidatos = []
        for url in candidatos[:6]:
            if url in probados:
                continue
            notas = probar(url)
            if notas:
                estado["autodescubierto"] = True
                return f, notas, estado
    return f, [], estado


# ----------------------------------------------------------------------------------------------
# Selección
# ----------------------------------------------------------------------------------------------
def motivo_descarte(n, filtro_opinion=True):
    t = sin_tildes(n["t"])
    if len(t) < 12:
        return "titular vacío o demasiado corto"
    for p in CEBO:
        if p.search(t):
            return "cebo"
    cats = [sin_tildes(limpiar_texto(c)) for c in n.get("cats") or []]
    ruta = urllib.parse.urlparse(n["u"]).path
    if filtro_opinion and (OPINION_URL.search(ruta) or any(OPINION_CAT.match(c) for c in cats)):
        return "opinión o publicidad"
    if DEPORTE_URL.search(ruta) or any(DEPORTE_CAT.match(c) for c in cats) or DEPORTE_TXT.search(t):
        return "deporte"
    if re.search(r"(?i)/(directo|en-directo|live)(/|-|$)|-directo-|-en-directo", ruta):
        return "cebo"
    if t.upper() == t and len(t) > 25 and re.search(r"[a-z]", sin_tildes(n["t"]).lower()) and n["t"] == n["t"].upper():
        return "cebo"
    return None


def palabras(t):
    return {w for w in re.findall(r"[a-zñ0-9]+", sin_tildes(t)) if len(w) >= 4 and w not in VACIAS}


def parecidas(a, b):
    if not a or not b:
        return False
    comun = len(a & b)
    return comun >= 4 and comun / len(a | b) >= 0.45 or comun >= 3 and comun / min(len(a), len(b)) >= 0.8


def clasificar_auto(n):
    """Reparte entre Historia y Ciencia mirando sobre todo el titular; si el tema no está claro, se descarta."""
    t, r = sin_tildes(n["t"]), sin_tildes(n["r"][:400])
    h = 3 * len(HISTORIA_KW.findall(t)) + len(HISTORIA_KW.findall(r))
    c = 3 * len(CIENCIA_KW.findall(t)) + len(CIENCIA_KW.findall(r))
    if max(h, c) < 3:
        return None
    return "historia" if h >= c else "ciencia"


def preparar(config, resultados):
    secciones = {s["id"]: dict(s, notas=[]) for s in config["secciones"]}
    descartes, todas = [], []
    for orden, (f, notas, estado) in enumerate(resultados):
        estado["descartadas"] = {}
        estado["validas"] = 0
        urls = set()
        for n in notas:
            n["t"] = limpiar_texto(n["t"], 220)
            n["r"] = limpiar_texto(n["r"], 1200)
            if n["u"] in urls:
                continue
            urls.add(n["u"])
            if sin_tildes(n["r"]).startswith(sin_tildes(n["t"])[:60]):
                n["r"] = n["r"][len(n["t"]):].lstrip(" .:-–—")
            n["r"] = limpiar_texto(n["r"], 300)
            n["f"], n["orden"] = f["nombre"], orden
            sec = f.get("seccion")
            if sec == "auto":
                sec = clasificar_auto(n)
                if not sec:
                    estado["descartadas"]["otros temas"] = estado["descartadas"].get("otros temas", 0) + 1
                    continue
            n["s"] = sec
            motivo = motivo_descarte(n, not f.get("sin_filtro_opinion"))
            if motivo:
                estado["descartadas"][motivo] = estado["descartadas"].get(motivo, 0) + 1
                descartes.append({"motivo": motivo, "fuente": f["nombre"], "titular": n["t"], "url": n["u"]})
                continue
            if sec not in secciones:
                continue
            n["max_fuente"] = f.get("max", 8)
            n["pal"] = palabras(n["t"])
            n["galdar"] = bool(GALDAR.search(sin_tildes(n["t"] + " " + n["r"])))
            todas.append((n, estado))
            estado["validas"] += 1
    # repetidas: se queda la primera según el orden de fuentes.json; las demás se citan como "también en"
    elegidas = []
    for n, estado in sorted(todas, key=lambda x: (x[0]["orden"], -(x[0]["d"] or AHORA).timestamp())):
        gemela = next((e for e in elegidas if e["u"] == n["u"] or parecidas(e["pal"], n["pal"])), None)
        if gemela:
            if n["f"] != gemela["f"] and all(x[0] != n["f"] for x in gemela["tambien"]):
                gemela["tambien"].append((n["f"], n["u"]))
            estado["descartadas"]["repetida"] = estado["descartadas"].get("repetida", 0) + 1
            estado["validas"] -= 1
            continue
        n["tambien"] = []
        elegidas.append(n)
    # reparto por secciones con ventana de tiempo, tope por fuente y por sección
    for sid, sec in secciones.items():
        candidatas = [n for n in elegidas if n["s"] == sid]
        ventana = sec.get("horas", 36)
        for factor in (1, 3, 10):
            limite = AHORA - dt.timedelta(hours=min(ventana * factor, max(ventana, 168)))
            dentro = [n for n in candidatas if (n["d"] or AHORA - dt.timedelta(hours=6)) >= limite]
            if len(dentro) >= min(8, len(candidatas)):
                break

        def puntos(n):
            p = (n["d"] or AHORA - dt.timedelta(hours=12)).timestamp()
            texto = sin_tildes(n["t"] + " " + n["r"])
            if n["galdar"]:
                p += 18 * 3600
            elif sid == "canarias" and GRAN_CANARIA.search(texto):
                p += 5 * 3600
            if sid == "ciencia" and ASTRO.search(texto):
                p += 30 * 3600
            return p
        dentro.sort(key=puntos, reverse=True)
        por_fuente, final = {}, []
        for n in dentro:
            if por_fuente.get(n["f"], 0) >= n["max_fuente"]:
                continue
            por_fuente[n["f"]] = por_fuente.get(n["f"], 0) + 1
            final.append(n)
            if len(final) >= sec.get("max", 20):
                break
        final.sort(key=lambda n: (n["d"] or AHORA - dt.timedelta(hours=12)), reverse=True)
        sec["notas"] = final
    return secciones, descartes


# ----------------------------------------------------------------------------------------------
# El tiempo (Open-Meteo, sin clave ni cookies). Si falla, simplemente no se muestra.
# ----------------------------------------------------------------------------------------------
CIELO = {0: "despejado", 1: "casi despejado", 2: "nubes y claros", 3: "nublado", 45: "niebla", 48: "niebla",
         51: "llovizna débil", 53: "llovizna", 55: "llovizna intensa", 56: "llovizna helada", 57: "llovizna helada",
         61: "lluvia débil", 63: "lluvia", 65: "lluvia fuerte", 66: "lluvia helada", 67: "lluvia helada",
         71: "nieve débil", 73: "nieve", 75: "nieve intensa", 77: "granizo fino", 80: "chubascos débiles",
         81: "chubascos", 82: "chubascos fuertes", 85: "chubascos de nieve", 86: "chubascos de nieve",
         95: "tormenta", 96: "tormenta con granizo", 99: "tormenta con granizo"}


def el_tiempo(lugar):
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&current=temperature_2m,weather_code"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=Atlantic%%2FCanary&forecast_days=2" % (lugar["lat"], lugar["lon"]))
    try:
        datos, _, _ = descargar(url, 15)
        j = json.loads(datos)
        d = j["daily"]
        return {"lugar": lugar["nombre"], "ahora": round(j["current"]["temperature_2m"]),
                "cielo": CIELO.get(j["current"]["weather_code"], ""),
                "dias": [{"min": round(d["temperature_2m_min"][i]), "max": round(d["temperature_2m_max"][i]),
                          "cielo": CIELO.get(d["weather_code"][i], ""),
                          "lluvia": d.get("precipitation_probability_max", [None, None])[i]} for i in range(2)]}
    except Exception as e:  # noqa: BLE001
        print("  (sin datos del tiempo: %s)" % e, file=sys.stderr)
        return None


# ----------------------------------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------------------------------
def esc(t):
    return html.escape(t or "", quote=True)


def local_dt(d):
    return d.astimezone(TZ)


def fecha_larga(d, con_anyo=True):
    d = local_dt(d)
    t = "%s, %d de %s" % (DIAS[d.weekday()], d.day, MESES[d.month - 1])
    return (t + " de %d" % d.year) if con_anyo else t


def cuando(d):
    """Texto de la hora relativo al momento en que se genera la página (diario.js lo corrige al abrirla)."""
    if not d:
        return ""
    l, hoy = local_dt(d), local_dt(AHORA).date()
    hora = "%d:%02d" % (l.hour, l.minute)
    dias = (hoy - l.date()).days
    if dias == 0:
        return "hoy, " + hora
    if dias == 1:
        return "ayer, " + hora
    if dias < 7:
        return "%s %d, %s" % (DIAS[l.weekday()], l.day, hora)
    return "%d de %s" % (l.day, MESES[l.month - 1])


def dominio(u):
    h = urllib.parse.urlparse(u).hostname or ""
    return h[4:] if h.startswith("www.") else h


def nota_html(n, resumen=True, mostrar_seccion=None):
    meta = ['<span class="medio">%s</span>' % esc(n["f"])]
    if n["d"]:
        meta.append('<time datetime="%s" data-ts="%d">%s</time>' % (n["d"].isoformat(), n["d"].timestamp(), cuando(n["d"])))
    if mostrar_seccion:
        meta.append('<span class="de">%s</span>' % esc(mostrar_seccion))
    sello = '<span class="sello">Gáldar</span>' if n["galdar"] else ""
    partes = ['<article class="nota">', '<div class="meta">%s%s</div>' % (" · ".join(meta), sello),
              '<h3><a href="%s" rel="noopener noreferrer">%s</a></h3>' % (esc(n["u"]), esc(n["t"]))]
    if resumen and n["r"]:
        partes.append("<p>%s</p>" % esc(n["r"]))
    if n["tambien"]:
        partes.append('<div class="tambien">También lo cuentan: %s</div>' % ", ".join(
            '<a href="%s" rel="noopener noreferrer">%s</a>' % (esc(u), esc(f)) for f, u in n["tambien"][:4]))
    partes.append("</article>")
    return "\n".join(partes)


def tiempo_html(t):
    if not t:
        return ""
    hoy, man = t["dias"]
    lluvia = lambda d: (", lluvia %d%%" % d["lluvia"]) if d.get("lluvia") and d["lluvia"] >= 30 else ""
    return ('<div class="tiempo"><b>%s</b> · ahora %d° y %s · hoy %d°–%d°%s · mañana %d°–%d°, %s%s</div>'
            % (esc(t["lugar"]), t["ahora"], esc(t["cielo"]), hoy["min"], hoy["max"], lluvia(hoy),
               man["min"], man["max"], esc(man["cielo"]), lluvia(man)))


def pagina(titulo, activo, cuerpo, config, extra_cab=""):
    hoy = local_dt(AHORA)
    nav = ['<a href="index.html"%s>Portada</a>' % (' aria-current="page"' if activo == "index" else "")]
    for s in config["secciones"]:
        nav.append('<a href="%s.html"%s>%s</a>' % (s["id"], ' aria-current="page"' if activo == s["id"] else "",
                                                   esc(s.get("corto", s["nombre"]))))
    cumple = ""
    if (hoy.month, hoy.day) == (11, 4):
        cumple = '<div class="cumple">¡Feliz cumpleaños, Paco! 🎂</div>'
    return """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="theme-color" content="#1f3a5f">
<title>%(titulo)s</title>
<link rel="icon" href="icono.png">
<link rel="stylesheet" href="estilo.css?v=%(v)s">
<script src="diario.js?v=%(v)s" defer></script>
</head>
<body data-gen="%(gen)d">
<header class="cab">
  <div class="fecha">%(fecha)s</div>
  <h1><a href="index.html">El Diario de Paco</a></h1>
  <div class="lema">Noticias sin titulares cebo, sin anuncios y sin cookies</div>
  %(cumple)s%(extra)s
</header>
<nav class="secciones" aria-label="Secciones">%(nav)s</nav>
<div id="aviso" class="aviso" hidden></div>
<main>
%(cuerpo)s
</main>
<footer class="pie">
  <p>Actualizado el %(act)s a las %(hora)s. Se actualiza solo cada dos horas.</p>
  <p><a href="fuentes.html">De dónde salen las noticias</a></p>
  <p class="firma">Un regalo de Abián · 4 de noviembre de 2026</p>
</footer>
</body>
</html>
""" % {"titulo": esc(titulo), "v": AHORA.strftime("%Y%m%d%H%M"), "gen": AHORA.timestamp(),
       "fecha": esc(fecha_larga(AHORA).capitalize()), "cumple": cumple, "extra": extra_cab, "nav": "".join(nav),
       "cuerpo": cuerpo, "act": esc(fecha_larga(AHORA, False)), "hora": local_dt(AHORA).strftime("%H:%M")}


def escribir(ruta, texto):
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


def generar_web(config, secciones, estados, descartes, tiempo, salida):
    if os.path.exists(salida):
        shutil.rmtree(salida)
    os.makedirs(salida)
    for nombre in ("estilo.css", "diario.js", "icono.png"):
        if os.path.exists(os.path.join(AQUI, "web", nombre)):
            shutil.copy(os.path.join(AQUI, "web", nombre), os.path.join(salida, nombre))
    if os.path.isdir(os.path.join(AQUI, "fonts")):
        shutil.copytree(os.path.join(AQUI, "fonts"), os.path.join(salida, "fonts"))
    # la app de la tablet (carpeta app/ del repositorio) se publica junto a la web: …/diario-paco/diario.apk
    carpeta_app = os.path.join(AQUI, "app")
    if os.path.isdir(carpeta_app):
        for nombre in os.listdir(carpeta_app):
            if nombre.endswith(".apk"):
                shutil.copy(os.path.join(carpeta_app, nombre), os.path.join(salida, nombre))
    escribir(os.path.join(salida, "robots.txt"), "User-agent: *\nDisallow: /\n")
    escribir(os.path.join(salida, ".nojekyll"), "")
    cab = tiempo_html(tiempo)

    # Portada
    cuerpo = []
    galdar = [n for s in secciones.values() for n in s["notas"] if n["galdar"]]
    if galdar:
        cuerpo.append('<section class="bloque galdar"><h2>Desde Gáldar</h2>')
        nombres = {s["id"]: s["nombre"] for s in config["secciones"]}
        cuerpo += [nota_html(n, True, nombres.get(n["s"]) if n["s"] != "canarias" else None) for n in galdar[:4]]
        cuerpo.append("</section>")
    vistos = {id(n) for n in galdar[:4]}
    for s in config["secciones"]:
        notas = [n for n in secciones[s["id"]]["notas"] if id(n) not in vistos]
        cuerpo.append('<section class="bloque"><h2><a href="%s.html">%s</a></h2>' % (s["id"], esc(s["nombre"])))
        if not notas:
            cuerpo.append('<p class="vacio">Ahora mismo no hay noticias nuevas en esta sección.</p>')
        for i, n in enumerate(notas[:s.get("portada", 5)]):
            cuerpo.append(nota_html(n, resumen=i < 3))
        total = len(secciones[s["id"]]["notas"])
        if total > s.get("portada", 5):
            cuerpo.append('<a class="mas" href="%s.html">Ver las %d noticias de %s</a>' % (s["id"], total, esc(s.get("corto", s["nombre"]))))
        cuerpo.append("</section>")
    escribir(os.path.join(salida, "index.html"), pagina("El Diario de Paco", "index", "\n".join(cuerpo), config, cab))

    # Secciones, agrupadas por día
    for s in config["secciones"]:
        cuerpo = ['<h2 class="titulo-seccion">%s</h2>' % esc(s["nombre"])]
        dia = None
        notas = secciones[s["id"]]["notas"]
        if not notas:
            cuerpo.append('<p class="vacio">Ahora mismo no hay noticias nuevas en esta sección.</p>')
        for n in notas:
            d = local_dt(n["d"]).date() if n["d"] else None
            if d != dia:
                dia = d
                cuerpo.append('<h4 class="dia">%s</h4>' % (esc(fecha_larga(n["d"], False).capitalize()) if d else "Sin fecha"))
            cuerpo.append(nota_html(n))
        escribir(os.path.join(salida, s["id"] + ".html"),
                 pagina(s["nombre"] + " · El Diario de Paco", s["id"], "\n".join(cuerpo), config, cab))

    # Fuentes
    est = {e["nombre"]: e for e in estados}
    cuerpo = ['<h2 class="titulo-seccion">De dónde salen las noticias</h2>',
              '<div class="texto">',
              "<p>Cada dos horas, un programa automático recoge los titulares que publican los medios de esta lista. "
              "Quita los titulares cebo, la publicidad, el deporte, los artículos de opinión y las noticias repetidas, "
              "y ordena el resto por secciones. Cuando varios medios cuentan lo mismo, se muestra una sola vez "
              "y debajo pone quién más lo cuenta.</p>",
              "<p>Al tocar una noticia se abre en la web del medio que la publicó. Esta página no tiene anuncios, "
              "no usa cookies y no guarda nada de quien la lee.</p>",
              "<p>Los medios se han elegido así: agencias de noticias, medios públicos, medios financiados por sus "
              "lectores, divulgación científica hecha por científicos y revistas especializadas.</p>", "</div>"]
    for s in config["secciones"]:
        lista = [f for f in config["fuentes"] if f.get("activa", True) and
                 (f.get("seccion") == s["id"] or (f.get("seccion") == "auto" and s["id"] in ("ciencia", "historia")))]
        if not lista:
            continue
        cuerpo.append('<h3 class="sub">%s</h3><ul class="fuentes">' % esc(s["nombre"]))
        for f in lista:
            e = est.get(f["nombre"], {})
            cuantas = sum(1 for n in secciones[s["id"]]["notas"] if n["f"] == f["nombre"])
            marca = "" if e.get("ok") else ' <span class="nofunciona">(hoy no responde)</span>'
            cuerpo.append('<li><b>%s</b>%s<br><span>%s · %s</span></li>' % (
                esc(f["nombre"]), marca, esc(f.get("tipo", "")),
                "%d noticia%s ahora" % (cuantas, "" if cuantas == 1 else "s")))
        cuerpo.append("</ul>")
    cuerpo.append('<p class="tecnico"><a href="estado.html">Informe técnico</a> · El tiempo: '
                  '<a href="https://open-meteo.com/" rel="noopener noreferrer">Open-Meteo</a></p>')
    escribir(os.path.join(salida, "fuentes.html"), pagina("Fuentes · El Diario de Paco", "fuentes", "\n".join(cuerpo), config, cab))

    # Informe técnico (para Abián)
    filas = []
    for e in estados:
        desc = ", ".join("%s: %d" % kv for kv in sorted(e.get("descartadas", {}).items()))
        filas.append("<tr class='%s'><td><b>%s</b>%s</td><td>%s</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (
            "ok" if e["ok"] else "mal", esc(e["nombre"]), " (autodescubierto)" if e.get("autodescubierto") else "",
            esc(e["canal"] or "—"), e["leidas"], e.get("validas", 0), esc(desc)) +
            ("<tr class='err'><td colspan=5>%s</td></tr>" % "<br>".join(esc(x) for x in e["errores"][-4:])
             if not e["ok"] and e["errores"] else ""))
    porm = {}
    for d in descartes:
        porm.setdefault(d["motivo"], []).append(d)
    det = "".join("<details><summary>%s (%d)</summary><ul>%s</ul></details>" % (
        esc(m), len(l), "".join("<li>%s — <i>%s</i></li>" % (esc(x["titular"]), esc(x["fuente"])) for x in l[:150]))
        for m, l in sorted(porm.items()))
    ok = sum(1 for e in estados if e["ok"])
    cuerpo = ('<h2 class="titulo-seccion">Informe técnico</h2><div class="texto"><p>Fuentes que funcionan: %d de %d. '
              'Total de noticias publicadas: %d.</p></div><div class="tabla"><table><tr><th>Fuente</th><th>Canal</th>'
              '<th>Leídas</th><th>Válidas</th><th>Descartadas</th></tr>%s</table></div><h3 class="sub">Titulares descartados</h3>%s'
              % (ok, len(estados), sum(len(s["notas"]) for s in secciones.values()), "".join(filas), det))
    escribir(os.path.join(salida, "estado.html"), pagina("Informe técnico · El Diario de Paco", "estado", cuerpo, config))
    json.dump({"generado": AHORA.isoformat(), "fuentes": estados,
               "secciones": {k: len(v["notas"]) for k, v in secciones.items()},
               "descartes": descartes}, open(os.path.join(salida, "estado.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    json.dump({"generado": AHORA.isoformat(), "tiempo": tiempo,
               "secciones": [{"id": s["id"], "nombre": s["nombre"], "notas": [
                   {"titular": n["t"], "url": n["u"], "fecha": n["d"].isoformat() if n["d"] else None,
                    "medio": n["f"], "resumen": n["r"], "tambien": [f for f, _ in n["tambien"]]}
                   for n in secciones[s["id"]]["notas"]]} for s in config["secciones"]]},
              open(os.path.join(salida, "noticias.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(AQUI, "_site"))
    ap.add_argument("--fuentes", default=os.path.join(AQUI, "fuentes.json"))
    ap.add_argument("--muestras", default=None, help="carpeta con canales de prueba (sin internet)")
    a = ap.parse_args()
    config = json.load(open(a.fuentes, encoding="utf-8"))
    fuentes = [f for f in config["fuentes"] if f.get("activa", True)]
    print("Leyendo %d fuentes…" % len(fuentes))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        resultados = list(ex.map(lambda f: cargar_fuente(f, a.muestras), fuentes))
    for f, notas, e in resultados:
        print("  %-38s %s %3d  %s%s" % (f["nombre"][:38], "OK " if e["ok"] else "MAL", e["leidas"],
                                      (e["canal"] or (e["errores"][-1] if e["errores"] else ""))[:90],
                                      ("  «%s»" % " / ".join(e.get("titulos", []))[:80]) if e["ok"] else ""))
        if not e["ok"]:
            for err in e["errores"]:
                print("      · " + err[:200])
        for c in e.get("canales_en_pagina", []):
            print("      canal visto: " + c)
    secciones, descartes = preparar(config, resultados)
    print("Titulares descartados:")
    for d in sorted(descartes, key=lambda d: (d["motivo"], d["fuente"])):
        print("  [%s] %s — %s" % (d["motivo"], d["titular"][:110], d["fuente"]))
    tiempo = None if a.muestras is not None or not config.get("tiempo") else el_tiempo(config["tiempo"])
    estados = [e for _, _, e in resultados]
    generar_web(config, secciones, estados, descartes, tiempo, a.out)
    print("Titulares publicados:")
    for s in config["secciones"]:
        print("  == " + s["nombre"])
        for n in secciones[s["id"]]["notas"]:
            print("   %s %s — %s%s" % ("*" if n["galdar"] else "-", n["t"][:120], n["f"], " (+%d)" % len(n["tambien"]) if n["tambien"] else ""))
    print("Secciones:", {k: len(v["notas"]) for k, v in secciones.items()}, "· descartadas:", len(descartes))
    print("Web creada en", a.out)
    if not any(e["ok"] for e in estados):
        sys.exit("Ninguna fuente ha funcionado.")


if __name__ == "__main__":
    main()
