#!/usr/bin/env python3
"""El Diario de Paco: genera una web de noticias limpia a partir de canales RSS/Atom.

Solo usa la biblioteca estándar de Python (3.9 o superior).
    python diario.py                    -> crea la web en la carpeta _site
    python diario.py --out carpeta      -> en otra carpeta
    python diario.py --muestras dir     -> sin internet: lee los canales de dir/<nombre>.xml (pruebas)

Qué hace en cada ejecución:
 1. Lee las fuentes de fuentes.json. Para cada una prueba sus canales RSS y, si ninguno funciona,
    busca el canal en la portada del medio (autodescubrimiento).
 2. Descarta titulares cebo, publicidad, opinión, directos, otros idiomas y repetidas; el fútbol va a su sección.
 3. Ordena por secciones y escribe páginas HTML estáticas (sin anuncios, sin cookies, sin rastreo)
    y un informe técnico (estado.html / estado.json) para ver qué fuentes fallan.
"""
import argparse, concurrent.futures, datetime as dt, email.utils, gzip, html, json, os, re, shutil
import ssl, sys, tempfile, unicodedata, urllib.error, urllib.parse, urllib.request, zlib
import xml.etree.ElementTree as ET

import lectura

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Atlantic/Canary")
except Exception:  # pragma: no cover - sin base de zonas horarias
    TZ = dt.timezone.utc

AQUI = os.path.dirname(os.path.abspath(__file__))
SITIO = "https://diariodepaco.github.io/"
UA = "Mozilla/5.0 (compatible; DiarioDePaco/1.0; lector RSS personal; +%s)" % SITIO
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
    r"jornada \d+ de|partidazo|derbi|aficion (del|de la ud|amarilla|blanquiazul)|tinerfenismo|heliodoro|"
    r"estadio de gran canaria|jesus de miguel)\b")
DEPORTE_CAT = re.compile(r"^(deportes?|futbol|baloncesto|motor|tenis|ciclismo|golf|atletismo|balonmano|"
                         r"lucha canaria|formula 1|motogp|polideportivo|ud las palmas|cd tenerife|mas deporte)$")
# Fútbol: sí entra, en su propia sección (con la UD Las Palmas arriba). El resto de deportes no.
FUTBOL = re.compile(r"\b(futbol\w*|laliga|la liga|liga f|segunda division|primera division|primera rfef|segunda rfef|"
                    r"tercera rfef|champions|europa league|conference league|ud las palmas|las palmas|cd tenerife|tenerife|"
                    r"real madrid|fc barcelona|barca|atletico de madrid|atletico|athletic|sevilla|valencia cf|real betis|betis|"
                    r"villarreal|real sociedad|osasuna|rayo vallecano|getafe|celta|espanyol|mallorca|girona|alaves|leganes|"
                    r"deportivo|racing|sporting|zaragoza|eibar|mirandes|huesca|elche|levante|granada|cadiz|almeria|malaga|"
                    r"gol|goles|golazo|fichaje\w*|delantero\w*|centrocampista\w*|portero\w*|defensa central|lateral|"
                    r"entrenador\w*|tecnico amarillo|amarillos|pio pio|estadio de gran canaria|heliodoro|bernabeu|"
                    r"camp nou|metropolitano|seleccion espanola|la roja|seleccionador|mundial\w*|eurocopa|copa del rey|"
                    r"supercopa|uefa|fifa|rfef|penalti\w*|var|arbitr\w*|jornada|clasificacion|ascenso|descenso|"
                    r"partido|partidos|once inicial|vestuario|cantera|jesus de miguel)\b")
OTROS_DEPORTES = re.compile(r"\b(baloncesto|basket|nba|acb|euroliga|eurobasket|dreamland|cb gran canaria|"
                            r"la laguna tenerife|tenis|tenista\w*|nadal|alcaraz|djokovic|roland garros|wimbledon|"
                            r"open de australia|us open|copa davis|formula 1|formula uno|f1|motogp|grand prix|"
                            r"gran premio|piloto\w*|ciclismo|ciclista\w*|tour de francia|vuelta a espana|giro de italia|"
                            r"atletismo|atleta\w*|maraton|balonmano|waterpolo|natacion|nadador\w*|golf|vela|regata\w*|"
                            r"lucha canaria|luchador\w*|boxeo|ufc|voleibol|voley|rugby|esqui|padel|hockey|"
                            r"juegos olimpicos|olimpiadas|paralimpic\w*|1500 m|100 metros)\b")
VINO_CANARIO = re.compile(r"\b(canari\w*|gran canaria|tenerife|lanzarote|la palma|el hierro|gomera|fuerteventura|"
                          r"malvasia|listan|queso de flor|flor de guia|majorero|palmero|herreno|platano de canarias|"
                          r"monte lentiscal|agaete|berrazales|galdar)\b")
UD = re.compile(r"\b(ud las palmas|la ud|amarillos|pio pio|estadio de gran canaria|las palmas)\b")
# Música: nada de reguetón (ni de su primo el trap latino)
REGUETON = re.compile(r"\b(reggaet\w*|reguet\w*|regaet\w*|perreo|dembow|trap latino|urbano latino|musica urbana|"
                      r"bad bunny|j balvin|maluma|karol g|ozuna|daddy yankee|anuel|rauw alejandro|feid|myke towers|"
                      r"nicky jam|sech|jhayco|jhay cortez|arcangel|young miko|peso pluma|bizarrap|bzrp|becky g|anitta|"
                      r"don omar|wisin|yandel|farruko|lunay|eladio carrion|natanael cano|tokischa|el alfa|bad gyal|"
                      r"daddy|nathy peluso|cazzu|tini|emilia mernes|duki|bresh|omar montes|rels b|morad|beny jr|"
                      r"saiko|myke|lola indigo|aitana ocana)\b|(?<!francisco de )\bquevedo\b")
# catalán, gallego, euskera…: con dos señales o más, el titular no está en castellano
OTRO_IDIOMA = re.compile(r"\b[ld][’'](?!hondt)\w|\b(amb|els|dels|diumenge|dilluns|dimarts|dimecres|dijous|divendres|"
                         r"dissabte|perque|aquesta|aquest|tambe|vinent|aixo|avui|ahir|dema|nova|nou|nous|feina|i)\b")
MARCADOR = re.compile(r"\(\s*\d{1,2}\s*-\s*\d{1,2}\s*\)")
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
CONTEXTOS = {}
POR_SITIO = {}  # como mucho dos descargas a la vez del mismo medio (si no, alguno corta: «demasiadas peticiones»)
CERROJO = __import__("threading").Lock()


def turno(host):
    with CERROJO:
        if host not in POR_SITIO:
            POR_SITIO[host] = __import__("threading").Semaphore(2)
        return POR_SITIO[host]


def contexto_con_intermedio(host):
    """Algunas webs no envían el certificado intermedio. Los navegadores lo descargan de la dirección que
    indica el propio certificado (AIA); aquí se hace lo mismo y se verifica la cadena completa con normalidad."""
    if host in CONTEXTOS:
        return CONTEXTOS[host]
    pem = ssl.get_server_certificate((host, 443), timeout=15)
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(pem)
    try:
        info = ssl._ssl._test_decode_cert(fh.name)  # noqa: SLF001 - lector de certificados de la propia biblioteca
    finally:
        os.unlink(fh.name)
    ctx = ssl.create_default_context()
    for u in info.get("caIssuers", ()):
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=15) as r:
            der = r.read(200_000)
        ctx.load_verify_locations(cadata=der.decode() if der.startswith(b"-----") else ssl.DER_cert_to_PEM_cert(der))
    CONTEXTOS[host] = ctx
    return ctx


def descargar(url, tiempo=25, reintento=True):
    host = urllib.parse.urlparse(url).hostname or ""
    with turno(host):
        try:
            return _descargar(url, tiempo)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or not reintento:
                raise
            espera = e.headers.get("Retry-After", "") if e.headers else ""
            espera = min(int(espera), 30) if espera.isdigit() else 8
    __import__("time").sleep(espera)
    return descargar(url, tiempo, False)


def _descargar(url, tiempo=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, application/json;q=0.9, text/html;q=0.8, */*;q=0.5",
        "Accept-Encoding": "gzip"})
    host = urllib.parse.urlparse(url).hostname
    try:
        r = urllib.request.urlopen(req, timeout=tiempo, context=CONTEXTOS.get(host))
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e) or "local issuer" not in str(e):
            raise
        r = urllib.request.urlopen(req, timeout=tiempo, context=contexto_con_intermedio(host))
    with r:
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


FOTO_MALA = re.compile(r"(?i)pixel|1x1|spacer|blank\.|gravatar|feedburner|/emoji/|logo|avatar|icon|\.svg(\?|$)|data:|"
                       r"doubleclick|/ads?/|banner|placeholder")


def foto_valida(u, base=""):
    u = html.unescape((u or "").strip())
    if not u:
        return ""
    u = urllib.parse.urljoin(base, u)
    if u.startswith("http://"):
        u = "https://" + u[7:]
    return u if u.startswith("https://") and not FOTO_MALA.search(u) else ""


def foto_en_html(t, base=""):
    """Primera imagen de verdad dentro de un trozo de HTML."""
    for m in re.finditer(r"(?is)<img\b[^>]*>", t or ""):
        etiqueta = m.group(0)
        anchura = re.search(r"(?i)\bwidth=[\"']?(\d+)", etiqueta)
        if anchura and int(anchura.group(1)) < 200:
            continue
        src = re.search(r"(?i)\b(?:data-src|src)=[\"']([^\"']+)", etiqueta)
        if src and foto_valida(src.group(1), base):
            return foto_valida(src.group(1), base)
    return ""


def foto_de_item(el, contenido, base=""):
    """Foto de un artículo de RSS/Atom: media:content, media:thumbnail, enclosure o la primera <img> del texto."""
    for c in el.iter():
        nombre = local(c.tag)
        if nombre in ("content", "thumbnail") and c.get("url") and \
                (c.get("medium") in (None, "image") and (c.get("type") or "image").startswith("image")):
            f = foto_valida(c.get("url"), base)
            if f:
                return f
        if nombre in ("enclosure", "link") and (c.get("type") or "").startswith("image") and (c.get("url") or c.get("href")):
            f = foto_valida(c.get("url") or c.get("href"), base)
            if f:
                return f
    return foto_en_html(contenido, base)


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
                          "r": resumen, "cats": cats, "x": texto_de(hijo(e, "content")),
                          "i": foto_de_item(e, texto_de(hijo(e, "content")) or resumen, enlace)})
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
            completo = texto_de(hijo(it, "encoded"))
            desc = texto_de(hijo(it, "description"))
            notas.append({"t": texto_de(hijo(it, "title")), "u": enlace, "d": fecha, "r": resumen, "cats": cats,
                          "x": completo if len(completo) > len(desc) else desc,
                          "i": foto_de_item(it, completo + " " + desc, enlace)})
    for n in notas:
        n["u"] = urllib.parse.urljoin(base, n["u"].strip()) if n["u"] else ""
    return notas[:80]


def leer_json(datos, base=""):
    """Noticias en JSON: la API de WordPress (/wp-json/wp/v2/posts) y otras con lista de artículos."""
    try:
        j = json.loads(datos.decode("utf-8", "replace"))
    except ValueError:
        return []

    def valor(d, *claves):
        for k in claves:
            v = d.get(k)
            if isinstance(v, dict):
                v = v.get("rendered") or v.get("text") or v.get("value")
            if isinstance(v, str) and v.strip():
                return v
        return ""

    def listas(x, prof=0):
        if prof > 4:
            return
        if isinstance(x, list) and x and all(isinstance(e, dict) for e in x[:5]):
            yield x
        if isinstance(x, dict):
            for v in x.values():
                yield from listas(v, prof + 1)
        elif isinstance(x, list):
            for v in x[:3]:
                yield from listas(v, prof + 1)

    for lista in listas(j):
        notas = []
        for d in lista[:80]:
            t = valor(d, "title", "titulo", "headline", "name", "longTitle")
            u = valor(d, "link", "url", "htmlUrl", "permalink", "uri", "href")
            if not t or not u:
                continue
            f = valor(d, "date_gmt", "publicationDate", "pubDate", "fecha", "published", "date", "datePublished")
            if f and re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", f) and d.get("date_gmt"):
                f += "Z"
            m = re.match(r"(\d{2})-(\d{2})-(\d{4}) (\d{2}:\d{2}(:\d{2})?)$", f or "")  # 04-11-2026 08:00:00 (RTVE)
            if m:
                f = "%s-%s-%sT%s" % (m.group(3), m.group(2), m.group(1), m.group(4))
            cats = []
            for k in ("mainTopic", "topic", "section", "seccion", "category", "categoria", "tematica", "language",
                      "idioma", "contentType", "type", "mainCategory"):
                v = d.get(k)
                if isinstance(v, dict):
                    v = v.get("name") or v.get("title") or v.get("titulo") or v.get("rendered")
                if isinstance(v, str) and v.strip():
                    cats.append(v.strip())
            notas.append({"t": t, "u": urllib.parse.urljoin(base, u), "d": fecha_de(f),
                          "r": valor(d, "excerpt", "summary", "description", "entradilla", "resumen", "subtitle"),
                          "x": valor(d, "content", "body", "text", "texto", "contenido", "cuerpo"),
                          "i": foto_valida(foto_json(d), base) or
                               foto_en_html(valor(d, "content", "body", "text"), base),
                          "cats": cats, "_crudo": {k: (str(v)[:60]) for k, v in list(d.items())[:25]}})
        if len(notas) >= 3:
            return notas
    return []


def foto_json(d):
    for k in ("jetpack_featured_media_url", "image", "imageSEO", "imagen", "thumbnail", "featured_image", "picture"):
        v = d.get(k)
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, dict):
            v = v.get("url") or v.get("src") or v.get("href")
        if isinstance(v, str) and v.startswith("http"):
            return v
    return ""


try:
    CATEGORIAS_WP = json.load(open(os.path.join(AQUI, ".cache", "categorias_wp.json"), encoding="utf-8"))
except (OSError, ValueError):
    CATEGORIAS_WP = {}


def url_wordpress(espec):
    """«wp:https://medio.com» o «wp:https://medio.com|categoria» → dirección de la API de WordPress."""
    sitio, _, categoria = espec[3:].partition("|")
    sitio = sitio.rstrip("/")
    campos = "&_fields=title,link,date_gmt,excerpt,content,jetpack_featured_media_url"
    if not categoria:
        return sitio + "/wp-json/wp/v2/posts?per_page=40" + campos
    clave_cat = sitio + "|" + categoria
    ids = CATEGORIAS_WP.get(clave_cat)
    if not ids:
        datos, _, _ = descargar(sitio + "/wp-json/wp/v2/categories?slug=" + urllib.parse.quote(categoria) + "&_fields=id")
        ids = [str(c["id"]) for c in json.loads(datos) if "id" in c]
        if ids:
            CATEGORIAS_WP[clave_cat] = ids
    if not ids:
        raise ValueError("no existe la categoría «%s»" % categoria)
    return sitio + "/wp-json/wp/v2/posts?per_page=40&categories=" + ",".join(ids) + campos


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
                      "x": campo("content:encoded", "content", "description"),
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
        crudo = open(ruta, "rb").read()
        notas = leer_json(crudo) if crudo.lstrip()[:1] in (b"[", b"{") else leer_canal(crudo, f.get("home", ""))
        estado.update(ok=bool(notas), canal="muestra:" + os.path.basename(ruta), leidas=len(notas))
        return f, notas, estado
    intentos = list(f.get("feeds") or [])
    probados = set()

    def probar(url, nivel=0):
        probados.add(url)
        try:
            real = url_wordpress(url) if url.startswith("wp:") else url
            datos, final, tipo = descargar(real)
        except Exception as e:  # noqa: BLE001
            estado["errores"].append("%s → %s" % (url, str(e)[:120]))
            return None
        cabeza = datos[:4000].lstrip().lower()
        parece_web = cabeza.startswith(b"<!doctype html") or cabeza.startswith(b"<html")
        if cabeza[:1] in (b"[", b"{"):
            notas = [n for n in leer_json(datos, final) if n["t"].strip() and n["u"].startswith("http")]
        else:
            notas = [] if parece_web else [n for n in leer_canal(datos, final) if n["t"].strip() and n["u"].startswith("http")]
        if notas:
            titulo = titulo_canal(datos)
            exigido = f.get("titulo_canal")
            if exigido and not re.search(exigido, sin_tildes(titulo)):
                estado["errores"].append("%s → es otro canal («%s»)" % (url, titulo))
                return None
            fechas = [n["d"] for n in notas if n["d"]]
            dias = f.get("_frescura", 60)
            if fechas and max(fechas) < AHORA - dt.timedelta(days=dias):
                estado["errores"].append("%s → canal sin noticias nuevas desde el %s" % (url, max(fechas).strftime("%d/%m/%Y")))
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
        estado["errores"].append("%s → canal vacío o ilegible (%s · «%s»)" % (
            url, tipo, re.sub(r"\s+", " ", datos[:90].decode("utf-8", "replace"))))
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
        estado["candidatos"] = candidatos[:12]
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
    if n.get("s") in ("musica", "cultura") and (REGUETON.search(t) or REGUETON.search(sin_tildes(n.get("r", "")[:300]))):
        return "reguetón"
    if re.search(r"(?i)/(directo|en-directo|live)(/|-|$)|-directo-|-en-directo", ruta):
        return "cebo"
    if len(OTRO_IDIOMA.findall(t)) >= 2:
        return "otro idioma"
    if MARCADOR.search(t):
        return "deporte"
    return None


def es_ud(n):
    return n["f"] == "UD Las Palmas" or bool(UD.search(sin_tildes(n["t"]))) or "ud las palmas" in sin_tildes(n["r"])


def en_minusculas(t):
    """Titulares escritos EN MAYÚSCULAS → normales (con los números romanos en mayúscula)."""
    letras = [c for c in t if c.isalpha()]
    if len(letras) < 15 or sum(c.isupper() for c in letras) < 0.8 * len(letras):
        return t
    t = t.lower()
    t = re.sub(r"(^|[.!?«\"“]\s*)([a-záéíóúñü])", lambda m: m.group(1) + m.group(2).upper(), t)
    return re.sub(r"\b(?=[ivxlc]+\b)(x{0,3})(ix|iv|v?i{0,3})\b", lambda m: m.group(0).upper(), t)


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
            n["t"] = en_minusculas(limpiar_texto(n["t"], 220))
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
            if not motivo and f.get("url_debe") and not re.search(f["url_debe"], n["u"]):
                motivo = "no es una noticia (programa, promoción…)"
            if not motivo and f.get("exigir") and not re.search(f["exigir"], sin_tildes(n["t"] + " " + n["r"])):
                motivo = "fuera de tema de la sección"
            if (motivo == "deporte" or sec == "futbol") and "futbol" in secciones:
                # el fútbol va a su sección; el resto de deportes, fuera
                texto = sin_tildes(n["t"] + " " + n["r"][:200])
                if len(FUTBOL.findall(texto)) + len(MARCADOR.findall(texto)) > len(OTROS_DEPORTES.findall(texto)) or \
                        (sec == "futbol" and not OTROS_DEPORTES.search(texto)):
                    n["s"] = sec = "futbol"
                    motivo = None if motivo in (None, "deporte") else motivo
                elif motivo == "deporte" or sec == "futbol":
                    motivo = "deporte (no fútbol)"
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
            if sid == "bodega":
                if VINO_CANARIO.search(texto):
                    p += 48 * 3600  # vinos, quesos y frutas de Canarias, arriba
                elif re.search(r"\b(vino|vinos|bodega\w*|vendimia|rioja|uva|uvas|queso\w*|miel)\b", texto):
                    p += 24 * 3600
            if sid == "futbol" and es_ud(n):
                p += 72 * 3600  # la UD Las Palmas, siempre arriba
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
        final.sort(key=lambda n: (sid == "futbol" and es_ud(n),
                                  n["d"] or AHORA - dt.timedelta(hours=12)), reverse=True)
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
              ('<h3><a href="leer.html#%s" data-leer="%s">%s</a></h3>' % (lectura.id_de(n["u"]), lectura.id_de(n["u"]), esc(n["t"]))
               if n.get("leer") else '<h3><a href="%s" rel="noopener noreferrer">%s</a></h3>' % (esc(n["u"]), esc(n["t"])))]
    if resumen and n["r"]:
        partes.append("<p>%s</p>" % esc(n["r"]))
    if n["tambien"]:
        partes.append('<div class="tambien">También lo cuentan: %s</div>' % esc(", ".join(f for f, _ in n["tambien"][:4])))
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


SAL_LECTURAS = [""]  # identifica la edición de lecturas.json (para no descargarla dos veces)


def pagina(titulo, activo, cuerpo, config, extra_cab="", script_extra=""):
    hoy = local_dt(AHORA)
    nav = ['<a href="index.html"%s>Portada</a>' % (' aria-current="page"' if activo == "index" else "")]
    recargar = '<a href="%s.html" class="recargar" id="actualizar" title="Actualizar">↻</a>' % ("index" if activo == "leer" else activo)
    for s in config["secciones"]:
        nav.append('<a href="%s.html"%s>%s</a>' % (s["id"], ' aria-current="page"' if activo == s["id"] else "",
                                                   esc(s.get("corto", s["nombre"]))))
    nav.append(recargar)
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
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data: https:; style-src 'self'; script-src 'self'; connect-src 'self' https://api.github.com; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="theme-color" content="#1f3a5f">
<title>%(titulo)s</title>
<link rel="icon" href="icono.png">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icono-192.png">
<link rel="stylesheet" href="estilo.css?v=%(v)s">
<script src="diario.js?v=%(v)s" defer></script>%(extra_js)s
</head>
<body data-gen="%(gen)d" data-lect="%(lect)s">
<header class="cab" id="arriba">
  <div class="fecha">%(fecha)s</div>
  <h1><a href="index.html">El Diario de Paco</a></h1>
  <div class="lema">Noticias sin titulares cebo, sin anuncios y sin cookies</div>
  %(cumple)s%(extra)s
</header>
<nav class="secciones" aria-label="Secciones">%(nav)s</nav>
<div id="instalar" class="instalar" hidden>
  <button type="button" id="btn-instalar">Instalar El Diario en esta tablet</button>
  <span>Quedará un icono en la pantalla de inicio, como una aplicación más.</span>
</div>
<div id="aviso" class="aviso" hidden></div>
<main>
%(cuerpo)s
</main>
<footer class="pie">
  <p>Actualizado el %(act)s a las %(hora)s. Se actualiza solo cada dos horas.</p>
  <p><a href="fuentes.html">De dónde salen las noticias</a></p>
  <p class="firma">Un regalo de Abián · 4 de noviembre de 2026</p>
</footer>
<a href="#arriba" id="subir" class="subir" aria-label="Volver arriba" title="Volver arriba"><svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><path d="M5 15l7-7 7 7" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></a>
</body>
</html>
""" % {"titulo": esc(titulo), "v": AHORA.strftime("%Y%m%d%H%M"), "gen": AHORA.timestamp(),
       "fecha": esc(fecha_larga(AHORA).capitalize()), "cumple": cumple, "extra": extra_cab, "nav": "".join(nav),
       "cuerpo": cuerpo, "act": esc(fecha_larga(AHORA, False)), "lect": esc(SAL_LECTURAS[0]),
       "extra_js": ('\n<script src="%s?v=%s" defer></script>' % (script_extra, AHORA.strftime("%Y%m%d%H%M"))) if script_extra else "", "hora": local_dt(AHORA).strftime("%H:%M")}


def escribir(ruta, texto):
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


def generar_web(config, secciones, estados, descartes, tiempo, salida, paquete=None):
    SAL_LECTURAS[0] = paquete["sal"] if paquete else ""
    if os.path.exists(salida):
        shutil.rmtree(salida)
    os.makedirs(salida)
    for nombre in sorted(os.listdir(os.path.join(AQUI, "web"))):
        shutil.copy(os.path.join(AQUI, "web", nombre), os.path.join(salida, nombre))
    if os.path.isdir(os.path.join(AQUI, "fonts")):
        shutil.copytree(os.path.join(AQUI, "fonts"), os.path.join(salida, "fonts"))
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
              "Quita los titulares cebo, la publicidad, los artículos de opinión, las noticias repetidas y el deporte (salvo el fútbol, que va en su sección), "
              "y ordena el resto por secciones. Cuando varios medios cuentan lo mismo, se muestra una sola vez "
              "y debajo pone quién más lo cuenta.</p>",
              "<p>Al tocar una noticia se lee aquí mismo, solo el texto: ninguna noticia se abre fuera del Diario, así que "
              "no hay anuncios ni avisos de cookies. Esta página no tiene anuncios, "
              "no usa cookies y no guarda nada de quien la lee.</p>",
              "<p><b>Para tenerlo como aplicación:</b> abre esta página en Chrome y toca «Instalar El Diario en esta "
              "tablet» (o, en el menú ⋮ de Chrome, «Instalar aplicación» o «Añadir a pantalla de inicio»). Queda un icono "
              "como el de cualquier otra aplicación, se abre a pantalla completa y guarda la última edición para leerla sin internet.</p>",
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
                  'datos de Open-Meteo (open-meteo.com)</p>')
    escribir(os.path.join(salida, "fuentes.html"), pagina("Fuentes · El Diario de Paco", "fuentes", "\n".join(cuerpo), config, cab))
    escribir(os.path.join(salida, "leer.html"), pagina(
        "Noticia · El Diario de Paco", "leer",
        '<article id="lectura" class="lectura"><p class="vacio">Abriendo la noticia…</p></article>', config, "", "leer.js"))
    if paquete:
        json.dump(paquete, open(os.path.join(salida, "lecturas.json"), "w"), separators=(",", ":"))

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


# ----------------------------------------------------------------------------------------------
# Lectura dentro del Diario (texto cifrado con la clave familiar; ver lectura.py)
# ----------------------------------------------------------------------------------------------
CACHE_TEXTOS = os.path.join(AQUI, ".cache", "textos.json")


def preparar_lecturas(config, secciones, sin_red=False):
    notas = [n for s in secciones.values() for n in s["notas"]]
    nombres = {s["id"]: s["nombre"] for s in config["secciones"]}
    try:
        cache = json.load(open(CACHE_TEXTOS, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    limite = AHORA.timestamp() - 12 * 86400
    cache = {u: v for u, v in cache.items() if v.get("t", 0) > limite}
    pendientes = []
    for n in notas:
        h, letras = lectura.limpiar_html(n.get("x") or "")
        if letras >= 600:
            n["leer"] = h
        guardado = cache.get(n["u"])
        if guardado:
            if not n.get("leer") and guardado["n"] >= 400:
                n["leer"] = lectura.limpiar_html(guardado["h"])[0]  # se vuelve a limpiar con las reglas actuales
            if not n.get("i") and guardado.get("i"):
                n["i"] = guardado["i"]
            if "i" not in guardado and not n.get("i") and not sin_red:
                pendientes.append(n)  # entrada antigua de la caché, sin mirar la foto
        elif not sin_red and (not n.get("leer") or not n.get("i")):
            pendientes.append(n)

    def de_la_pagina(n):
        try:
            datos, final, tipo = descargar(n["u"], 20)
            pagina = datos.decode("utf-8", "replace")
            h, letras = lectura.extraer_de_pagina(pagina)
            foto = foto_valida(lectura.foto_de_pagina(pagina), final)
        except Exception:  # noqa: BLE001
            h, letras, foto = "", 0, ""
        return n, h, letras, foto
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for n, h, letras, foto in ex.map(de_la_pagina, pendientes):
            cache[n["u"]] = {"h": h if letras >= 400 else "", "n": letras, "i": foto, "t": AHORA.timestamp()}
            if not n.get("leer") and letras >= 400:
                n["leer"] = h
            if not n.get("i") and foto:
                n["i"] = foto
    os.makedirs(os.path.dirname(CACHE_TEXTOS), exist_ok=True)
    json.dump(cache, open(CACHE_TEXTOS, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(CATEGORIAS_WP, open(os.path.join(os.path.dirname(CACHE_TEXTOS), "categorias_wp.json"), "w"))
    # el titular repetido como primer párrafo sobra
    for n in notas:
        if n.get("leer"):
            primero = re.match(r"<p>(.*?)</p>\n?", n["leer"], flags=re.S)
            if primero and sin_tildes(re.sub(r"<[^>]+>", "", primero.group(1))).strip(" .") == sin_tildes(n["t"]).strip(" ."):
                n["leer"] = n["leer"][primero.end():]
    for n in notas:
        if n.get("leer"):
            n["leer"] = re.sub(r"(?s)<a\b[^>]*>(.*?)</a>", r"\1", n["leer"])
    con_texto = [n for n in notas if n.get("leer")]
    por_fuente = {}
    for n in notas:
        a = por_fuente.setdefault(n["f"], [0, 0])
        a[0] += 1
        a[1] += 1 if n.get("leer") else 0
    print("Lectura dentro del Diario: %d de %d noticias (%d páginas consultadas) · con foto: %d" % (
        len(con_texto), len(notas), len(pendientes), sum(1 for n in con_texto if n.get("i"))))
    for f, (total, ok) in sorted(por_fuente.items()):
        if ok < total:
            print("  %-38s %d de %d" % (f[:38], ok, total))
    if os.environ.get("DIAGNOSTICO_LECTURA"):
        vistas = set()
        for n in con_texto:
            if n["f"] in vistas:
                continue
            vistas.add(n["f"])
            parrafos = [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"(?s)<(?:p|h3|li)>(.*?)</(?:p|h3|li)>", n["leer"])]
            print("  [%s] %d párrafos | 1º: %s | último: %s" % (n["f"], len(parrafos), parrafos[0][:90] if parrafos else "",
                                                            parrafos[-1][:90] if parrafos else ""))
    clave = os.environ.get("CLAVE_DIARIO", "").strip()
    if clave:
        quitadas = 0
        for sec in secciones.values():
            antes = len(sec["notas"])
            sec["notas"] = [n for n in sec["notas"] if n.get("leer")]
            quitadas += antes - len(sec["notas"])
        print("  Se quitan %d noticias que no se pueden leer dentro (nada se abre fuera del Diario)" % quitadas)
    if not clave:
        print("  (sin CLAVE_DIARIO: las noticias se abren en la web de cada medio)")
        for n in notas:
            n.pop("leer", None)
        return None
    datos = {lectura.id_de(n["u"]): {"t": n["t"], "f": n["f"], "u": n["u"], "s": nombres.get(n["s"], ""),
                                     "d": n["d"].isoformat() if n["d"] else None, "h": n["leer"], "i": n.get("i", ""),
                                     "o": [[f, u] for f, u in n["tambien"][:4]]} for n in con_texto}
    token = os.environ.get("ACTUALIZAR_TOKEN", "").strip()
    if token:
        # para el botón «Actualizar ahora» (solo lo pueden usar los aparatos con la llave)
        datos["_actualizar"] = {"t": token, "r": os.environ.get("GITHUB_REPOSITORY", "diariodepaco/diariodepaco.github.io"),
                                "w": "publicar.yml"}
        print("  Botón «Actualizar ahora»: activado")
    return lectura.cifrar(json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), clave)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(AQUI, "_site"))
    ap.add_argument("--fuentes", default=os.path.join(AQUI, "fuentes.json"))
    ap.add_argument("--muestras", default=None, help="carpeta con canales de prueba (sin internet)")
    a = ap.parse_args()
    config = json.load(open(a.fuentes, encoding="utf-8"))
    fuentes = [f for f in config["fuentes"] if f.get("activa", True)]
    horas = {s["id"]: s.get("horas", 36) for s in config["secciones"]}
    for f in fuentes:
        # un canal de noticias que lleva días sin publicar está abandonado: se busca otro
        f["_frescura"] = f.get("frescura_dias", 4 if horas.get(f.get("seccion"), 999) <= 48 else 60)
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
        if notas and "_crudo" in notas[0] and f.get("diagnostico"):
            print("      ejemplo: %s" % json.dumps(notas[0]["_crudo"], ensure_ascii=False)[:700])
        for c in e.get("canales_en_pagina", []) if not e["ok"] else []:
            print("      canal visto: " + c)
        for c in e.get("candidatos", []) if not e["ok"] else []:
            print("      candidato en portada: " + c)
    secciones, descartes = preparar(config, resultados)
    print("Titulares descartados:")
    for d in sorted(descartes, key=lambda d: (d["motivo"], d["fuente"])):
        print("  [%s] %s — %s" % (d["motivo"], d["titular"][:110], d["fuente"]))
    tiempo = None if a.muestras is not None or not config.get("tiempo") else el_tiempo(config["tiempo"])
    estados = [e for _, _, e in resultados]
    paquete = preparar_lecturas(config, secciones, a.muestras is not None)
    generar_web(config, secciones, estados, descartes, tiempo, a.out, paquete)
    print("Resumen por fuente (válidas tras filtros · publicadas · descartadas):")
    publicadas = {}
    for sec in secciones.values():
        for n in sec["notas"]:
            publicadas[n["f"]] = publicadas.get(n["f"], 0) + 1
    for f, notas, e in resultados:
        fechas = sorted(n["d"] for n in notas if n.get("d"))
        print("  %-38s %3d · %3d · %s · fechas %s → %s" % (f["nombre"][:38], e.get("validas", 0), publicadas.get(f["nombre"], 0),
              e.get("descartadas", {}), fechas[0].strftime("%d/%m %H:%M") if fechas else "-",
              fechas[-1].strftime("%d/%m %H:%M") if fechas else "-"))
    print("Texto completo en el canal (noticias con más de 800 letras / publicadas):")
    for f, notas, e in resultados:
        pub = [n for sec in secciones.values() for n in sec["notas"] if n["f"] == f["nombre"]]
        largos = [n for n in pub if len(limpiar_texto(n.get("x") or "")) >= 800]
        if pub:
            print("  %-38s %3d / %3d  (media %d letras)" % (f["nombre"][:38], len(largos), len(pub),
                  sum(len(limpiar_texto(n.get("x") or "")) for n in pub) // len(pub)))
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
