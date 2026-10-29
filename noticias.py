"""Al Día RD: busca noticias, hace resúmenes con Claude, arma la página en docs/,
escoge la noticia de Instagram de esta hora y prepara el consejo del día."""
import feedparser, json, os, re, html, hashlib, unicodedata, urllib.parse
from datetime import datetime, timezone, timedelta

# ================= Configuración =================
SITIO = "https://aldiard.com"
INSTAGRAM = "aldiardnews"
MODELO = os.environ.get("MODELO_IA", "claude-haiku-5-5")
HORA_RD = timezone(timedelta(hours=-4))   # República Dominicana (no cambia de hora)

def gnews(q):
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:1d")
            + "&hl=es-419&gl=US&ceid=US:es-419")

FUENTES_RD = [gnews("site:" + s) for s in (
    "listindiario.com", "diariolibre.com", "elnuevodiario.com.do", "hoy.com.do",
    "eldia.com.do", "noticiassin.com", "cdn.com.do", "deultimominuto.com", "deultimominuto.net",
    "elcaribe.com.do", "acento.com.do", "n.com.do", "eldinero.com.do")]
FUENTES_USA = [gnews(q) for q in (
    "dominicanos Nueva York", "dominicanos New Jersey", "dominicanos Florida",
    "dominicanos Massachusetts", "dominicanos Pensilvania", "dominicanos Rhode Island",
    "comunidad dominicana Estados Unidos")]
FUENTES_INTER = [
    "https://news.google.com/rss/headlines/section/topic/WORLD?hl=es-419&gl=US&ceid=US:es-419",
    gnews("site:bbc.com/mundo"), gnews("site:cnnespanol.cnn.com"), gnews("noticias internacionales hoy")]
FUENTES_FAMOSOS = [gnews(q) for q in (
    "Alofoke", "site:deultimominuto.com farándula", "farándula dominicana", "artistas dominicanos", "famosos Hollywood",
    "celebridades latinas Estados Unidos", "música urbana dominicana")]
FUENTES_PRECIOS = [gnews(q) for q in (
    "precios combustibles República Dominicana", "precio gasolina gasoil GLP semana MICM",
    "precio del dólar hoy República Dominicana", "precios canasta básica República Dominicana")]
FUENTES_JUEGOS = [gnews(q) for q in (
    "GTA 6", "videojuegos lanzamiento", "PlayStation 5 juegos", "Nintendo Switch 2", "Xbox juegos")]

SEC_RD, SEC_USA = "República Dominicana", "Dominicanos en EE.UU."
SEC_INTER, SEC_FAMOSOS = "Internacionales", "Famosos"
SEC_PRECIOS, SEC_JUEGOS = "Precios y combustibles", "Videojuegos"
# sección: (fuentes, máximo de noticias nuevas por corrida, clase, color)
# El programa corre cada hora: estos cupos dan como mucho 7 noticias nuevas por hora
# (ahora son más largas y cuestan más de IA, por eso son menos).
SECCIONES = {
    SEC_RD:      (FUENTES_RD,      2, "rd", (206, 17, 38)),
    SEC_USA:     (FUENTES_USA,     1, "us", (0, 45, 98)),
    SEC_INTER:   (FUENTES_INTER,   1, "in", (15, 118, 110)),
    SEC_FAMOSOS: (FUENTES_FAMOSOS, 1, "fa", (190, 24, 93)),
    SEC_PRECIOS: (FUENTES_PRECIOS, 1, "pr", (180, 83, 9)),
    SEC_JUEGOS:  (FUENTES_JUEGOS,  1, "vj", (109, 40, 217)),
}
POR_FUENTE = 3          # noticias que mira de cada fuente

# Solo se publican noticias de estos medios (y de Alofoke). Lo demás se descarta.
CONFIABLES = """
listindiario.com diariolibre.com elnuevodiario.com.do hoy.com.do eldia.com.do noticiassin.com
cdn.com.do deultimominuto.com deultimominuto.net elcaribe.com.do acento.com.do n.com.do eldinero.com.do
elnacional.com.do almomento.net z101digital.com ensegundos.do telemicro.com.do
eldiariony.com ny1.com elnuevoherald.com univision.com telemundo.com telemundo47.com
telemundoboston.com telemundonuevainglaterra.com telemundo51.com nbcnews.com apnews.com
laopinion.com elmundo.es elpais.com efe.com swissinfo.ch bbc.com cnn.com cnnespanol.cnn.com
reuters.com france24.com dw.com infobae.com rtve.es europapress.es lavanguardia.com abc.es
euronews.com elespanol.com clarin.com eltiempo.com eluniversal.com.mx
peopleenespanol.com hola.com billboard.com quien.com
ign.com latam.ign.com 3djuegos.com vandal.elespanol.com vandal.net hobbyconsolas.com xataka.com
as.com levelup.com eurogamer.es gamespot.com nintendo.com playstation.com xbox.com
""".split()
MAX_GUARDADAS = 400
HORAS_IG = 12           # una noticia más vieja que esto ya no se sube a Instagram
HORA_CONSEJO = 9        # a partir de las 9 a. m. (hora RD) se prepara el consejo del día
TENDENCIA_HISTORIA = 3  # si 3 medios o más hablan de la noticia, también va a historias
MAX_HISTORIAS_DIA = 8   # tope de historias de noticias por día

ARCHIVO = "docs/noticias.json"
ARCHIVO_CONSEJOS = "docs/consejos.json"

# Títulos que no son noticias de verdad (se saltan)
BASURA = (r"^en vivo\b|\ben vivo -|gu[ií]a deportiva|resultados de (las )?loter|"
          r"loter[ií]as? (de|del) hoy|^hor[oó]scopo|^portada|\(opini[oó]n\)")

# ---- Noticias que van DIRECTO a tus páginas (en vez del periódico) ----
DIVISAS = ("https://divisasrd.com", "divisasrd.com")
KILOCLARO = ("https://kiloclarord.com", "kiloclarord.com")
DIRECTOS = [
    # tasa del dólar del día
    (r"(tasa|precio|cotizaci[oó]n) del d[oó]lar|d[oó]lar (hoy|cierra|abre|amanece|se cotiza|se vende|se compra)"
     r"|tasa de cambio (hoy|del d[ií]a)|a c[oó]mo est[aá] el d[oó]lar",
     None, "Mira la tasa del dólar en vivo", DIVISAS),
    # precios de combustibles de la semana
    (r"precios? de (los )?combustibles|combustibles? (se mantienen|seguir[aá]n|suben|bajan|congelad|sin cambio)"
     r"|precios? de la gasolina|(gasolina|gasoil|glp).{0,40}(se mantiene|sube|baja|congela|semana|rd\$)",
     r"protest|huelga|\bparo\b|marcha|\bley\b|proyecto|congreso|diputad|senad|tribunal|brent|barril|petr[oó]leo"
     r"|bolivia|venezuela|m[eé]xico|cuestiona|critica|denuncia|reclama|partido|oposici|\bfp\b|\bpld\b|\bprm\b|marbete",
     "Mira los precios de combustibles", DIVISAS),
    # tarifa de la luz
    (r"tarifas? (el[eé]ctricas?|de (la )?(luz|energ[ií]a))|precio del kwh|aumento de (la )?luz|facturas? de (la )?luz",
     r"protest|huelga|\bparo\b",
     "Calcula tu factura de luz", KILOCLARO),
]
# ---- Botón extra (la noticia sigue yendo al periódico) ----
ENLACES = [
    (r"combustible|gasolina|gasoil|\bglp\b|gas licuado", "Precios de combustibles", DIVISAS),
    (r"d[oó]lar|divisa|tasa de cambio|remesa|peso dominicano|\busd\b|\beuro\b", "Tasa del dólar hoy", DIVISAS),
    (r"\bluz\b|apag[oó]n|apagones|el[eé]ctric|edenorte|edesur|edeeste|\bkwh\b|kilovat", "Calcula tu factura de luz", KILOCLARO),
]
# ---- Temas para el consejo del día ----
TEMA_DIVISAS = r"d[oó]lar|divisa|remesa|tasa de cambio|\beuro\b|bolsa de valores|inflaci[oó]n|combustible|gasolina|gasoil|\bglp\b"
TEMA_LUZ = r"\bluz\b|apag[oó]n|apagones|el[eé]ctric|edenorte|edesur|edeeste|\bkwh\b|energ[ií]a"

AZUL, ROJO, BLANCO = (0, 45, 98), (206, 17, 38), (255, 255, 255)
FUENTE_NEGRA = "fuentes/Inter-Black.otf"
FUENTE_FUERTE = "fuentes/Inter-ExtraBold.otf"
FUENTE_MEDIA = "fuentes/Inter-SemiBold.otf"

# ================= Utilidades =================
_cliente = None
def cliente():
    global _cliente
    if _cliente is None:
        import anthropic
        _cliente = anthropic.Anthropic()  # usa la variable ANTHROPIC_API_KEY
    return _cliente

def limpiar(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()

def titulo_sin_fuente(titulo, fuente):
    fin = " - " + fuente
    return titulo[: -len(fin)] if fuente and titulo.endswith(fin) else titulo

def texto_de(n):
    return (n.get("titulo", "") + " " + n.get("resumen", "")).lower()

def destino(n):
    """Si es la tasa del día, los combustibles de la semana o la tarifa de luz: a tu página."""
    t = texto_de(n)
    for patron, excluir, texto, (url, sitio) in DIRECTOS:
        if re.search(patron, t) and not (excluir and re.search(excluir, t)):
            return {"texto": texto, "url": url, "sitio": sitio}
    return None

def extras(n):
    """Botones a tus páginas para las demás noticias del tema (sin repetir página)."""
    if destino(n):
        return []
    vistos, salida = set(), []
    for patron, texto, (url, sitio) in ENLACES:
        if sitio not in vistos and re.search(patron, texto_de(n)):
            vistos.add(sitio)
            salida.append({"texto": texto, "url": url, "sitio": sitio})
    return salida

def sitio_propio(n):
    d = destino(n) or (extras(n) or [None])[0]
    return d["sitio"] if d else "aldiard.com"

def clase(seccion):
    return SECCIONES.get(seccion, (None, 0, "rd", ROJO))[2]

def color(seccion):
    return SECCIONES.get(seccion, (None, 0, "rd", ROJO))[3]

def fecha(n):
    return datetime.fromisoformat(n["fecha"])

def ahora():
    return datetime.now(timezone.utc)

def cargar(ruta):
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)

RELLENO = (r"t[ií]tulo|texto disponible|informaci[oó]n disponible|m[aá]s detalles|no se (ofrecen|detallan|incluyen|especifican|conocen|dan)"
           r"|no (ofrece|incluye|informa|detalla|especifica|da)|sin (dar )?m[aá]s (detalles|contexto)|seg[uú]n (informa|indica) (la noticia|la nota)")

def quitar_relleno(resumen):
    """Quita las frases tipo 'el título no da más detalles' de los resúmenes viejos."""
    resumen = re.sub(r"\s*\((sin|no hay) [^)]*\)", "", resumen)
    coletilla = r",? seg[uú]n (informa|indica|se[nñ]ala) (la noticia|la nota|el t[ií]tulo|el titular)"
    frases = [re.sub(coletilla, "", f, flags=re.I)
              for f in re.split(r"(?<=[.!?])\s+", resumen.strip())]
    frases = [re.sub(r"^seg[uú]n el t[ií]tulo,\s*(\w)", lambda m: m.group(1).upper(), f, flags=re.I) for f in frases]
    buenas = [f for f in frases if not re.search(RELLENO, f, re.I)]
    return " ".join(buenas or frases[:1])

# ================= Buscar noticias =================
def rotar(lista):
    """Cada hora empieza por un medio distinto, para que no salga siempre el mismo."""
    k = ahora().hour % len(lista)
    return lista[k:] + lista[:k]

def dominio(e):
    d = urllib.parse.urlparse((e.get("source") or {}).get("href", "")).netloc.lower()
    return d[4:] if d.startswith("www.") else d

def es_confiable(dom):
    return bool(dom) and ("alofoke" in dom or any(dom == c or dom.endswith("." + c) for c in CONFIABLES))

NAVEGADOR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
}
OPINION = r"/opini[oó]n|/opiniones|/editorial|/columnas?/|/blogs?/"

def bajar_pagina(url):
    """Baja la página como si fuera un navegador normal (muchos periódicos bloquean a los programas)."""
    import urllib.request
    pedido = urllib.request.Request(url, headers=NAVEGADOR)
    with urllib.request.urlopen(pedido, timeout=20) as r:
        crudo = r.read(3_000_000)
        juego = r.headers.get_content_charset() or "utf-8"
    return crudo.decode(juego, errors="replace")

def parrafos_simples(pagina):
    """Plan B: junta los párrafos <p> largos de la página."""
    pagina = re.sub(r"(?is)<(script|style|nav|footer|header|aside|form)[^>]*>.*?</\1>", " ", pagina)
    ps = [limpiar(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", pagina)]
    ps = [p for p in ps if len(p) > 80 and not re.search(r"cookies|suscr[ií]bete|derechos reservados|newsletter", p, re.I)]
    return "\n".join(ps)

def leer_articulo(link):
    """Saca la dirección real de la noticia (Google News la esconde) y el texto del artículo."""
    url = link
    if "news.google.com" in link:
        try:
            from googlenewsdecoder import gnewsdecoder
            r = gnewsdecoder(link, interval=1)
            url = r.get("decoded_url") if r.get("success") else None
        except Exception as err:
            print("No se pudo sacar el enlace real:", err)
            url = None
    if not url:
        return None, ""
    texto, pagina = "", ""
    try:
        pagina = bajar_pagina(url)
    except Exception as err:
        print("No se pudo bajar la página:", repr(err)[:150])
    if not pagina:
        try:  # segundo intento con el bajador propio de trafilatura
            import trafilatura
            pagina = trafilatura.fetch_url(url) or ""
        except Exception:
            pagina = ""
    if pagina:
        try:
            import trafilatura
            texto = trafilatura.extract(pagina, include_comments=False, include_tables=False) or ""
        except Exception as err:
            print("trafilatura no pudo:", repr(err)[:150])
        if len(texto) < 500:
            texto = max(texto, parrafos_simples(pagina), key=len)
    return url, texto[:7000]

def resumir(titulo, texto):
    msg = cliente().messages.create(
        model=MODELO, max_tokens=300,
        messages=[{"role": "user", "content":
            "Escribe un resumen corto (1-2 oraciones) en español, con tus propias palabras, neutral y sin "
            "inventar datos, de esta noticia. Nunca menciones que falta información ni digas 'según el título'. "
            "Responde solo con el resumen.\n\n" f"Título: {titulo}\nTexto: {texto}"}])
    return msg.content[0].text.strip()

INSTRUCCIONES = """Eres redactor de Al Día RD, un medio digital dominicano. Te paso una noticia publicada por otro medio.
Escríbela de nuevo para nuestros lectores siguiendo estas reglas:
- Usa tus propias palabras y tu propia estructura. No sigas el orden del original ni cambies palabras frase por frase:
  cuéntala como se la contarías a alguien, primero lo esencial (qué pasó, quién, cuándo, dónde) y después el contexto.
- Solo hechos que estén en el texto. No inventes, no supongas, no opines, no exageres.
  Copia exactos los nombres, cifras y fechas.
- Español claro y neutral, frases cortas, para público dominicano en RD y en EE.UU.
- No menciones al medio original ni digas "según el artículo", "el texto" o "la nota".
- Marca "confiable": false si es publicidad o contenido patrocinado, un rumor sin fuente, una columna de opinión
  o algo sin hechos claros.
Devuelve SOLO este JSON:
{"confiable": true,
 "titulo": "titular propio, distinto del original, máximo 14 palabras",
 "resumen": "2 oraciones, máximo 260 caracteres",
 "parrafos": ["PARRAFOS"]}"""

def redactar(titulo, descripcion, articulo):
    largo = len(articulo) >= 500
    if largo:
        parrafos = "3 o 4 párrafos que sumen entre 150 y 230 palabras"
        datos = f"Titular original: {titulo}\nDescripción: {descripcion}\n\nTexto del artículo:\n{articulo}"
    else:
        parrafos = ("deja esta lista vacía: [], porque solo tienes el titular. En 'resumen' escribe 1 o 2 "
                    "oraciones con lo que dice el titular, sin agregar nada, y nunca digas que falta información")
        datos = f"Titular original: {titulo}\nDescripción: {descripcion}"
    msg = cliente().messages.create(
        model=MODELO, max_tokens=900,
        messages=[{"role": "user", "content": INSTRUCCIONES.replace('"PARRAFOS"', parrafos) + "\n\n" + datos}])
    t = msg.content[0].text
    bruto = t[t.find("{"): t.rfind("}") + 1]
    try:
        r = json.loads(bruto)
    except json.JSONDecodeError:
        r = json.loads(re.sub(r"[\x00-\x1f]", " ", bruto))  # saltos de línea dentro del texto
    r["parrafos"] = [p.strip() for p in (r.get("parrafos") or []) if p.strip()] if largo else []
    return r

CUENTA = {"ya vistas": 0, "no confiables": 0, "sin enlace real": 0, "sin texto del artículo": 0,
          "error IA (larga)": 0, "error IA (corta)": 0, "descartadas por la IA": 0, "largas": 0, "cortas": 0}

def buscar(guardadas):
    vistos = ({n["link"] for n in guardadas} | {n["titulo"] for n in guardadas}
              | {n.get("titulo_original", "") for n in guardadas})
    nuevas = []
    for seccion, (fuentes, cupo, _, _) in SECCIONES.items():
        de_esta, intentos = 0, 0
        for url in rotar(fuentes):
            for e in feedparser.parse(url).entries[:POR_FUENTE]:
                if de_esta >= cupo or intentos >= cupo * 2:
                    break
                fuente = e.get("source", {}).get("title", "Fuente")
                titulo = titulo_sin_fuente(limpiar(e.get("title", "")), fuente)
                link = e.get("link", "")
                if not titulo or not link or link in vistos or titulo in vistos:
                    CUENTA["ya vistas"] += 1
                    continue
                if re.search(BASURA, titulo, re.I) or len(titulo.split()) < 4:
                    continue
                dom = dominio(e)
                if not es_confiable(dom):
                    CUENTA["no confiables"] += 1
                    print("Fuente no confiable, se salta:", dom or fuente)
                    continue
                vistos.update((link, titulo))
                intentos += 1
                url_real, articulo = leer_articulo(link)
                if not url_real:
                    CUENTA["sin enlace real"] += 1
                elif len(articulo) < 500:
                    CUENTA["sin texto del artículo"] += 1
                print(f"[{seccion}] {fuente}: texto leído {len(articulo)} letras -> {url_real or 'sin enlace'}")
                if url_real and re.search(OPINION, url_real, re.I):
                    CUENTA["descartadas por la IA"] += 1
                    print("Es opinión o editorial, se salta:", url_real)
                    continue
                try:
                    r = redactar(titulo, limpiar(e.get("summary", "")), articulo)
                except Exception as err:
                    CUENTA["error IA (larga)"] += 1
                    print("Error IA al escribir la versión larga:", repr(err)[:300])
                    try:  # plan B: la noticia sale corta, como antes, para no perderla
                        r = {"confiable": True, "titulo": titulo, "parrafos": [],
                             "resumen": resumir(titulo, limpiar(e.get("summary", "")))}
                    except Exception as err2:
                        CUENTA["error IA (corta)"] += 1
                        print("Error IA también en la corta:", repr(err2)[:300])
                        continue
                if not r.get("confiable", True):
                    CUENTA["descartadas por la IA"] += 1
                    print("La IA la descartó (rumor, opinión o publicidad):", titulo)
                    continue
                CUENTA["largas" if r["parrafos"] else "cortas"] += 1
                nuevas.append({"id": hashlib.md5(link.encode()).hexdigest()[:10],
                               "titulo": (r.get("titulo") or titulo).strip(), "titulo_original": titulo,
                               "resumen": (r.get("resumen") or "").strip() or titulo,
                               "parrafos": r["parrafos"], "link": link, "url": url_real,
                               "fuente": fuente, "dominio": dom, "seccion": seccion,
                               "fecha": ahora().isoformat()})
                de_esta += 1
    return nuevas

def enlace_fuente(n):
    return n.get("url") or n["link"]

# ================= Tendencia =================
VACIAS = set("""sobre entre desde hasta tras para por con sin los las del una unos unas este esta estos
estas ese esa como mas pero porque cuando donde quien tiene tienen sera seran fue fueron hace hacia
ante bajo segun durante mientras dominicana dominicano dominicanos republica estados unidos nuevo nueva
hoy dice dicen anuncia afirma asegura""".split())

def _palabras(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {w for w in re.findall(r"[a-z0-9ñ]+", t) if len(w) >= 5 and w not in VACIAS}

def calcular_tendencia(todas):
    """Cuántos medios distintos están hablando del mismo tema en las últimas 36 horas."""
    recientes = [n for n in todas if fecha(n) > ahora() - timedelta(hours=36)]
    pal = {id(n): _palabras(n.get("titulo_original") or n["titulo"]) for n in recientes}
    for n in recientes:
        medios = {n["fuente"]}
        for m in recientes:
            if m is not n and len(pal[id(n)] & pal[id(m)]) >= 2:
                medios.add(m["fuente"])
        n["tendencia"] = len(medios)

# ================= Imágenes para Instagram =================
def _envolver(d, texto, fuente, ancho):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if d.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas

def _redes(d, x, y, tam, color, fuente):
    """Dibuja los íconos de Instagram y X y el usuario @aldiardnews."""
    g = max(3, tam // 11)
    d.rounded_rectangle((x, y, x + tam, y + tam), radius=int(tam * 0.3), outline=color, width=g)
    c, r = tam / 2, tam * 0.22
    d.ellipse((x + c - r, y + c - r, x + c + r, y + c + r), outline=color, width=g)
    d.ellipse((x + tam * 0.70, y + tam * 0.16, x + tam * 0.84, y + tam * 0.30), fill=color)
    x2 = x + tam + 18
    d.line((x2 + 2, y + 2, x2 + tam - 2, y + tam - 2), fill=color, width=max(4, tam // 7))
    d.line((x2 + tam - 4, y + 2, x2 + 4, y + tam - 2), fill=color, width=max(2, tam // 16))
    d.text((x2 + tam + 18, y + tam / 2), "@" + INSTAGRAM, font=fuente, fill=color, anchor="lm")

def _cabecera(img, d, etiqueta, color_etiqueta):
    from PIL import ImageFont
    from logo import marca
    W = img.width
    d.rectangle((0, 0, W, 230), fill=AZUL)
    lg = marca(150, fondo=False)
    img.paste(lg, (50, 40), lg)
    f_sec = ImageFont.truetype(FUENTE_FUERTE, 34)
    sw = d.textlength(etiqueta, font=f_sec)
    d.rounded_rectangle((W - 60 - sw - 48, 88, W - 60, 146), radius=29, fill=color_etiqueta)
    d.text((W - 60 - sw - 24, 98), etiqueta, font=f_sec, fill=BLANCO)
    d.rectangle((0, 230, W, 242), fill=ROJO)

def imagen_instagram(n, ruta):
    """Tarjeta 1080x1350 con el titular."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), BLANCO)
    d = ImageDraw.Draw(img)
    c = color(n["seccion"])
    _cabecera(img, d, n["seccion"].upper(), ROJO if c == AZUL else c)
    margen, top, fondo = 70, 290, 1090
    for tam in range(104, 40, -4):
        f_tit = ImageFont.truetype(FUENTE_NEGRA, tam)
        lineas = _envolver(d, n["titulo"], f_tit, W - 2 * margen)
        alto = int(tam * 1.18)
        if len(lineas) * alto + 60 <= fondo - top:
            break
    y = top + (fondo - top - (len(lineas) * alto + 60)) // 2
    for ln in lineas:
        d.text((margen, y), ln, font=f_tit, fill=(20, 24, 33))
        y += alto
    d.rectangle((margen, y + 24, margen + 120, y + 36), fill=ROJO)
    f_pie = ImageFont.truetype(FUENTE_MEDIA, 32)
    d.line((margen, 1140, W - margen, 1140), fill=(220, 224, 232), width=3)
    d.text((margen, 1166), "Fuente: " + n["fuente"], font=f_pie, fill=(90, 98, 112))
    f_web = ImageFont.truetype(FUENTE_FUERTE, 34)
    web = sitio_propio(n)
    d.text((W - margen - d.textlength(web, font=f_web), 1164), web, font=f_web, fill=AZUL)
    d.rectangle((0, 1240, W, H), fill=AZUL)  # franja de redes
    _redes(d, margen, 1272, 46, BLANCO, ImageFont.truetype(FUENTE_FUERTE, 34))
    f_seg = ImageFont.truetype(FUENTE_MEDIA, 30)
    seg = "Síguenos"
    d.text((W - margen - d.textlength(seg, font=f_seg), 1279), seg, font=f_seg, fill=(190, 205, 225))
    img.save(ruta, "JPEG", quality=88)

def imagen_consejo(c, ruta):
    """Tarjeta del consejo del día, con el color de la página a la que lleva."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1080, 1350
    fondo_c = (20, 110, 60) if c["tema"] == "kiloclaro" else (12, 74, 110)
    img = Image.new("RGB", (W, H), fondo_c)
    d = ImageDraw.Draw(img)
    _cabecera(img, d, "CONSEJO DEL DÍA", ROJO)
    margen = 70
    f_tit = ImageFont.truetype(FUENTE_NEGRA, 84)
    for tam in range(88, 50, -4):
        f_tit = ImageFont.truetype(FUENTE_NEGRA, tam)
        lt = _envolver(d, c["titulo"], f_tit, W - 2 * margen)
        if len(lt) <= 3:
            break
    f_txt = ImageFont.truetype(FUENTE_MEDIA, 44)
    lx = _envolver(d, c["texto"], f_txt, W - 2 * margen)[:7]
    alto_t, alto_x = int(tam * 1.15), 62
    bloque = len(lt) * alto_t + 50 + len(lx) * alto_x
    y = 300 + (1080 - 300 - bloque) // 2
    for ln in lt:
        d.text((margen, y), ln, font=f_tit, fill=BLANCO)
        y += alto_t
    d.rectangle((margen, y + 14, margen + 120, y + 26), fill=(250, 204, 21))
    y += 50
    for ln in lx:
        d.text((margen, y), ln, font=f_txt, fill=(230, 240, 236))
        y += alto_x
    f_bot = ImageFont.truetype(FUENTE_FUERTE, 40)
    txt = c["boton"] + " → " + c["sitio"]
    tw = d.textlength(txt, font=f_bot)
    if tw > W - 2 * margen - 60:
        txt = c["sitio"]
        tw = d.textlength(txt, font=f_bot)
    d.rounded_rectangle((margen, 1110, margen + tw + 60, 1206), radius=48, fill=BLANCO)
    d.text((margen + 30, 1134), txt, font=f_bot, fill=fondo_c)
    _redes(d, margen, 1258, 42, BLANCO, ImageFont.truetype(FUENTE_FUERTE, 32))
    img.save(ruta, "JPEG", quality=88)

def imagen_historia(origen, ruta, etiqueta, pie):
    """Versión vertical 1080x1920 para historias: la tarjeta en el medio, etiqueta arriba y aviso abajo."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (0, 22, 50))  # azul más oscuro para que resalte la tarjeta
    d = ImageDraw.Draw(img)
    tarjeta = Image.open(origen).convert("RGB").resize((960, 1200), Image.LANCZOS)
    m = Image.new("L", tarjeta.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, 960, 1200), radius=36, fill=255)
    img.paste(tarjeta, (60, 330), m)
    f_et = ImageFont.truetype(FUENTE_NEGRA, 52)
    ew = d.textlength(etiqueta, font=f_et)
    d.rounded_rectangle(((W - ew) / 2 - 36, 170, (W + ew) / 2 + 36, 262), radius=46, fill=ROJO)
    d.text(((W - ew) / 2, 186), etiqueta, font=f_et, fill=BLANCO)
    f_pie = ImageFont.truetype(FUENTE_FUERTE, 50)
    pw = d.textlength(pie, font=f_pie)
    d.text(((W - pw) / 2, 1640), pie, font=f_pie, fill=BLANCO)
    f_sub = ImageFont.truetype(FUENTE_MEDIA, 38)
    sub = "Enlace en nuestro perfil"
    d.text(((W - d.textlength(sub, font=f_sub)) / 2, 1720), sub, font=f_sub, fill=(190, 205, 225))
    img.save(ruta, "JPEG", quality=88)

def historias_de_hoy(todas, consejos):
    hoy = ahora().astimezone(HORA_RD).date()
    return sum(1 for n in todas if n.get("historia_fecha")
               and datetime.fromisoformat(n["historia_fecha"]).astimezone(HORA_RD).date() == hoy)

# ================= Instagram: qué se sube esta hora =================
def elegir_para_instagram(todas):
    """Una sola noticia por corrida: la que más medios están publicando,
    sin repetir la sección de la última publicación si hay otra casi igual de fuerte."""
    for n in todas:  # lo que quedó pendiente vuelve a competir
        if n.get("ig") == "pendiente":
            n["ig"] = None
    limite = ahora() - timedelta(hours=HORAS_IG)
    pool = [n for n in todas if n.get("ig") in (None, "") and n.get("id")
            and fecha(n) > limite and n.get("ig_intentos", 0) < 3
            and not re.search(BASURA, n["titulo"], re.I)]
    if not pool:
        return None
    pool.sort(key=lambda n: (n.get("tendencia", 1), n["fecha"]), reverse=True)
    publicadas = sorted((n for n in todas if n.get("ig_fecha")), key=lambda n: n["ig_fecha"])
    ultima_sec = publicadas[-1]["seccion"] if publicadas else None
    mejor = pool[0]
    if mejor["seccion"] == ultima_sec:
        otra = next((n for n in pool if n["seccion"] != ultima_sec), None)
        if otra and otra.get("tendencia", 1) >= mejor.get("tendencia", 1) - 1:
            mejor = otra
    os.makedirs("docs/ig", exist_ok=True)
    ruta = f"docs/ig/{mejor['id']}.jpg"
    try:
        imagen_instagram(mejor, ruta)
    except Exception as err:
        print("Error imagen:", err)
        return None
    mejor["ig"], mejor["ig_img"] = "pendiente", f"ig/{mejor['id']}.jpg"
    # si está en tendencia, también va a historias (con tope diario)
    if (mejor.get("tendencia", 1) >= TENDENCIA_HISTORIA and not mejor.get("historia")
            and historias_de_hoy(todas, []) < MAX_HISTORIAS_DIA):
        try:
            imagen_historia(ruta, f"docs/ig/{mejor['id']}-h.jpg", "EN TENDENCIA", "Lee más en aldiard.com")
            mejor["historia"], mejor["historia_img"] = "pendiente", f"ig/{mejor['id']}-h.jpg"
        except Exception as err:
            print("Error imagen historia:", err)
    return mejor

def limpiar_imagenes(todas, consejos):
    """Borra las imágenes de más de 2 días (Instagram ya guardó su copia)."""
    limite = ahora() - timedelta(days=2)
    se_quedan = {n.get("ig_img") for n in todas
                 if n.get("ig_img") and (fecha(n) > limite or n.get("ig") == "pendiente")}
    se_quedan |= {n.get("historia_img") for n in todas
                  if n.get("historia_img") and (fecha(n) > limite or n.get("historia") == "pendiente")}
    se_quedan |= {c.get("ig_img") for c in consejos[-3:]} | {c.get("historia_img") for c in consejos[-3:]}
    for archivo in os.listdir("docs/ig"):
        if "ig/" + archivo not in se_quedan:
            os.remove(os.path.join("docs/ig", archivo))

# ================= Consejo del día =================
CONSEJOS_RESPALDO = {
    "kiloclaro": [
        ("Desconecta lo que no usas", "Los cargadores, la TV y el microondas gastan luz aunque estén apagados. Desconéctalos o usa una regleta con interruptor."),
        ("El aire a 24 grados", "Cada grado menos en el aire acondicionado sube la factura. A 24 °C con las puertas cerradas enfría bien y gastas menos."),
        ("La nevera bien cerrada", "Revisa que la goma de la puerta selle bien y no la abras sin necesidad. Es de los aparatos que más consume en la casa."),
    ],
    "divisas": [
        ("Compara antes de cambiar", "La tasa del dólar no es igual en todos los bancos y casas de cambio. Compara antes de cambiar y te puedes ahorrar unos pesos."),
        ("Remesas: mira el total", "Al mandar dinero, fíjate en la comisión y en la tasa que te dan, no solo en una de las dos. Lo que importa es cuánto llega."),
        ("Pendiente al combustible", "Los precios de los combustibles se anuncian cada semana. Revísalos antes de llenar el tanque o de planificar un viaje."),
    ],
}

def tema_del_dia(todas, consejos, hoy):
    del_dia = [n for n in todas if fecha(n).astimezone(HORA_RD).date().isoformat() == hoy]
    div = sum(1 for n in del_dia if re.search(TEMA_DIVISAS, texto_de(n)))
    luz = sum(1 for n in del_dia if re.search(TEMA_LUZ, texto_de(n)))
    if div != luz:
        return ("divisas" if div > luz else "kiloclaro"), del_dia
    anterior = consejos[-1]["tema"] if consejos else "kiloclaro"
    return ("divisas" if anterior == "kiloclaro" else "kiloclaro"), del_dia  # empate: intercala

def escribir_consejo(tema, titulares):
    sobre = ("cómo cuidar el dinero: cambiar dólares, mandar o recibir remesas pagando menos, "
             "seguir la tasa del dólar, los precios de los combustibles o la bolsa"
             if tema == "divisas" else "cómo ahorrar luz y bajar la factura eléctrica en la casa")
    msg = cliente().messages.create(
        model=MODELO, max_tokens=300,
        messages=[{"role": "user", "content":
            f"Escribe UN consejo práctico para la gente de República Dominicana y los dominicanos en EE.UU. sobre {sobre}. "
            "Puedes inspirarte en los temas de estos titulares de hoy, sin repetirlos:\n- " + "\n- ".join(titulares[:6]) +
            "\n\nNo inventes cifras, tasas ni precios. Tono cercano y claro. "
            "Título de máximo 6 palabras. Texto de 2 oraciones, máximo 220 caracteres. "
            'Responde solo con JSON: {"titulo": "...", "texto": "..."}'}])
    t = msg.content[0].text
    datos = json.loads(t[t.find("{"): t.rfind("}") + 1])
    return datos["titulo"].strip(), datos["texto"].strip()

def consejo_del_dia(todas, consejos):
    ahora_rd = ahora().astimezone(HORA_RD)
    hoy = ahora_rd.date().isoformat()
    if any(c["fecha"] == hoy for c in consejos) or ahora_rd.hour < HORA_CONSEJO:
        return None
    tema, del_dia = tema_del_dia(todas, consejos, hoy)
    patron = TEMA_DIVISAS if tema == "divisas" else TEMA_LUZ
    titulares = [n["titulo"] for n in del_dia if re.search(patron, texto_de(n))] or [n["titulo"] for n in del_dia]
    try:
        titulo, texto = escribir_consejo(tema, titulares)
    except Exception as err:
        print("Consejo de respaldo:", err)
        lista = CONSEJOS_RESPALDO[tema]
        titulo, texto = lista[ahora_rd.toordinal() % len(lista)]
    url, sitio = DIVISAS if tema == "divisas" else KILOCLARO
    c = {"fecha": hoy, "tema": tema, "titulo": titulo, "texto": texto, "url": url, "sitio": sitio,
         "boton": "Mira la tasa en vivo" if tema == "divisas" else "Calcula tu factura"}
    os.makedirs("docs/ig", exist_ok=True)
    try:
        imagen_consejo(c, f"docs/ig/consejo-{hoy}.jpg")
        c["ig"], c["ig_img"] = "pendiente", f"ig/consejo-{hoy}.jpg"
        imagen_historia(f"docs/ig/consejo-{hoy}.jpg", f"docs/ig/consejo-{hoy}-h.jpg",
                        "CONSEJO DEL DÍA", "Visita " + c["sitio"])
        c["historia"], c["historia_img"] = "pendiente", f"ig/consejo-{hoy}-h.jpg"
    except Exception as err:
        print("Error imagen consejo:", err)
    consejos.append(c)
    print(f"Consejo del día ({tema}): {titulo}")
    return c

# ================= Página web =================
CSS = r""":root{--azul:#002d62;--rojo:#ce1126;--ambar:#b45309;--morado:#6d28d9;--rosa:#be185d;--verdeazul:#0f766e;--tinta:#141821;--gris:#5a6270;--linea:#e3e6ec;--fondo:#f5f6f8;--blanco:#fff;
 --enlace:#002d62;--texto2:#353b47;--extra-t:#0f5132;--extra-f:#e8f5ee;--extra-b:#cde9d9;--pie:#002d62;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--rojo:#ff5c6c;--ambar:#f59e0b;--morado:#a78bfa;--rosa:#f472b6;--verdeazul:#2dd4bf;--tinta:#e7eaf0;--gris:#9aa3b2;--linea:#2a3142;--fondo:#0e1117;--blanco:#171c26;
 --enlace:#8ab4f8;--texto2:#c3c9d4;--extra-t:#86efac;--extra-f:#12301f;--extra-b:#1f4d33;--pie:#0a0f1a;color-scheme:dark}}
:root[data-theme=dark]{--rojo:#ff5c6c;--ambar:#f59e0b;--morado:#a78bfa;--rosa:#f472b6;--verdeazul:#2dd4bf;--tinta:#e7eaf0;--gris:#9aa3b2;--linea:#2a3142;--fondo:#0e1117;--blanco:#171c26;
 --enlace:#8ab4f8;--texto2:#c3c9d4;--extra-t:#86efac;--extra-f:#12301f;--extra-b:#1f4d33;--pie:#0a0f1a;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--fondo);color:var(--tinta);-webkit-font-smoothing:antialiased}
a{color:inherit}
.franja{height:5px;background:linear-gradient(90deg,var(--azul) 0 50%,var(--rojo) 50% 100%)}
header{background:var(--blanco);border-bottom:1px solid var(--linea);position:sticky;top:0;z-index:10}
.barra{max-width:1100px;margin:auto;padding:12px 16px;display:flex;align-items:center;gap:12px}
.barra img{width:44px;height:44px;border-radius:10px}
.marca{font-weight:900;font-size:22px;letter-spacing:-.02em;color:var(--enlace);text-decoration:none}
.marca span{color:var(--rojo)}
.hoy{margin-left:auto;color:var(--gris);font-size:14px}
.redes{display:flex;gap:8px;margin-left:12px}
.red{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;border:1px solid var(--linea);background:var(--blanco);color:var(--tinta);cursor:pointer;padding:0;text-decoration:none}
.red:hover{border-color:var(--enlace);color:var(--enlace)}
.red svg{width:18px;height:18px}
nav{max-width:1100px;margin:auto;padding:0 16px 10px;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}
nav button{font:600 14px Inter,system-ui,sans-serif;border:1px solid var(--linea);background:var(--blanco);color:var(--tinta);padding:8px 14px;border-radius:999px;cursor:pointer;white-space:nowrap}
nav button[aria-pressed=true]{background:var(--azul);border-color:var(--enlace);color:#fff}
main{max-width:1100px;margin:auto;padding:20px 16px 40px}
.nota{background:var(--blanco);border:1px solid var(--linea);border-radius:14px;padding:18px 20px;display:flex;flex-direction:column;gap:8px;border-top:4px solid var(--rojo)}
.meta{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--gris)}
.chip{font-weight:800;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--rojo)}
.nota.us{border-top-color:var(--enlace)} .us .chip{color:var(--enlace)}
.nota.pr{border-top-color:var(--ambar)} .pr .chip{color:var(--ambar)}
.nota.vj{border-top-color:var(--morado)} .vj .chip{color:var(--morado)}
.nota.fa{border-top-color:var(--rosa)} .fa .chip{color:var(--rosa)}
.nota.in{border-top-color:var(--verdeazul)} .in .chip{color:var(--verdeazul)}
.nota h2{margin:0;font-size:19px;line-height:1.3;font-weight:800;letter-spacing:-.01em}
.nota h2 a{text-decoration:none} .nota h2 a:hover{text-decoration:underline}
.nota p{margin:0;color:var(--texto2);line-height:1.55;font-size:15.5px}
.fuente{margin-top:auto;padding-top:6px;font-weight:600;font-size:14px;color:var(--enlace);text-decoration:none}
.fuente:hover{text-decoration:underline}
.fuente.chica{font-weight:500;font-size:12.5px;color:var(--gris);padding-top:2px}
.extra{align-self:flex-start;font-size:13.5px;font-weight:600;text-decoration:none;color:var(--extra-t);background:var(--extra-f);border:1px solid var(--extra-b);padding:6px 10px;border-radius:8px}
.directo{margin-top:auto;align-self:flex-start;font-size:15px;font-weight:800;text-decoration:none;color:#fff;background:#157347;padding:10px 14px;border-radius:10px}
.extra:hover,.directo:hover{text-decoration:underline}
.destacada{padding:26px 28px;margin-bottom:18px}
.destacada h2{font-size:clamp(24px,3.4vw,34px);font-weight:900;line-height:1.15}
.destacada p{font-size:17px;max-width:760px}
.consejo{border-radius:14px;padding:20px 24px;margin:0 0 18px;color:#fff;background:#0c4a6e}
.consejo.kiloclaro{background:#146e3c}
.cetq{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#fde68a}
.consejo h2{margin:6px 0 4px;font-size:22px;font-weight:900}
.consejo p{margin:0 0 12px;line-height:1.5;color:#e6f0ec;max-width:760px}
.consejo a{display:inline-block;background:#fff;color:#0f2b20;font-weight:800;text-decoration:none;padding:9px 14px;border-radius:999px;font-size:14px}
.rejilla{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.oculta{display:none}
.vacio{text-align:center;color:var(--gris);padding:60px 0}
footer{background:var(--pie);color:#cfd8e6;font-size:14px}
.pie{max-width:1100px;margin:auto;padding:28px 16px;display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between}
.pie img{width:48px;height:48px;border-radius:10px}
.pie a{color:#fff;font-weight:600}
.legal{width:100%;border-top:1px solid #ffffff22;padding-top:14px;font-size:13px}
@media (max-width:600px){.hoy{display:none}.redes{margin-left:auto}.destacada{padding:20px}}
.leer{margin-top:auto;padding-top:6px;font-weight:700;font-size:14px;color:var(--enlace);text-decoration:none}
.leer:hover{text-decoration:underline}
.articulo{max-width:760px;margin:auto;background:var(--blanco);border:1px solid var(--linea);border-radius:16px;padding:28px 30px;border-top:5px solid var(--rojo)}
.articulo.us{border-top-color:var(--enlace)} .articulo.pr{border-top-color:var(--ambar)} .articulo.vj{border-top-color:var(--morado)}
.articulo.fa{border-top-color:var(--rosa)} .articulo.in{border-top-color:var(--verdeazul)}
.articulo .us .chip,.articulo.us .chip{color:var(--enlace)} .articulo.pr .chip{color:var(--ambar)} .articulo.vj .chip{color:var(--morado)}
.articulo.fa .chip{color:var(--rosa)} .articulo.in .chip{color:var(--verdeazul)}
.articulo h1{font-size:clamp(26px,4vw,36px);line-height:1.15;font-weight:900;letter-spacing:-.02em;margin:10px 0 16px}
.articulo .cuerpo p{font-size:18px;line-height:1.7;color:var(--texto2);margin:0 0 16px}
.credito{margin-top:22px;padding-top:16px;border-top:1px solid var(--linea);font-size:14.5px;color:var(--gris)}
.credito a{color:var(--enlace);font-weight:700}
.compartir{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.compartir a{font-size:13.5px;font-weight:700;text-decoration:none;padding:8px 12px;border-radius:999px;border:1px solid var(--linea);color:var(--tinta)}
.volver{display:inline-block;margin:0 0 14px;font-weight:600;color:var(--enlace);text-decoration:none}
.relacionadas{max-width:760px;margin:26px auto 0}
.relacionadas h3{font-size:16px;text-transform:uppercase;letter-spacing:.06em;color:var(--gris)}
.relacionadas a{display:block;padding:12px 0;border-bottom:1px solid var(--linea);text-decoration:none;font-weight:700}
.relacionadas a:hover{color:var(--enlace)}
"""

REDES_HTML = """      <a class="red" href="https://instagram.com/§IG§" target="_blank" rel="noopener" aria-label="Instagram"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor"/></svg></a>
      <a class="red" href="https://x.com/§IG§" target="_blank" rel="noopener" aria-label="X"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.8 3h3.1l-6.8 7.7L22 21h-6.2l-4.9-6.3L5.3 21H2.2l7.2-8.3L2 3h6.4l4.4 5.8L17.8 3zm-1.1 16.2h1.7L7.4 4.7H5.6l11.1 14.5z"/></svg></a>
      <button class="red" id="tema" aria-label="Cambiar entre modo claro y oscuro"></button>
""".replace("§IG§", INSTAGRAM)

JS_TEMA = r"""var raiz=document.documentElement,btn=document.getElementById('tema');
function oscuro(){return raiz.dataset.theme?raiz.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches}
function icono(){btn.innerHTML=oscuro()?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>':'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'}
icono(); matchMedia('(prefers-color-scheme: dark)').addEventListener('change',icono);
btn.onclick=function(){var t=oscuro()?'light':'dark';raiz.dataset.theme=t;try{localStorage.setItem('tema',t)}catch(e){}icono()};
"""

JS_PORTADA = r"""var hoy=new Date().toLocaleDateString('es-DO',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
document.getElementById('hoy').textContent=hoy.charAt(0).toUpperCase()+hoy.slice(1);
function hace(iso){var m=Math.round((Date.now()-new Date(iso))/60000);
 if(m<1)return'ahora';if(m<60)return'hace '+m+' min';var h=Math.round(m/60);
 if(h<24)return'hace '+h+(h==1?' hora':' horas');var d=Math.round(h/24);return'hace '+d+(d==1?' día':' días');}
document.querySelectorAll('.hora').forEach(function(e){e.textContent='· '+hace(e.dataset.fecha)});
document.querySelectorAll('nav button').forEach(function(b){b.onclick=function(){
 document.querySelectorAll('nav button').forEach(function(x){x.setAttribute('aria-pressed',x===b)});
 document.querySelectorAll('.nota').forEach(function(n){n.classList.toggle('oculta',b.dataset.f!=='todas'&&n.dataset.sec!==b.dataset.f)});
 var c=document.querySelector('.consejo'); if(c)c.classList.toggle('oculta',b.dataset.f!=='todas');
}});
"""

def cabeza(titulo, descripcion, url, imagen, extra=""):
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<meta name="description" content="{html.escape(descripcion)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{html.escape(titulo)}">
<meta property="og:description" content="{html.escape(descripcion)}">
<meta property="og:image" content="{imagen}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#002d62">
<script>try{{var t=localStorage.getItem("tema");if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<link rel="icon" type="image/png" href="/img/favicon.png">
<link rel="apple-touch-icon" href="/img/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>{CSS}</style>{extra}</head>
<body>
<div class="franja"></div>"""

def encabezado(nav=""):
    return f"""
<header>
  <div class="barra">
    <img src="/img/logo-512.png" alt="">
    <a class="marca" href="/">Al Día <span>RD</span></a>
    <div class="hoy" id="hoy"></div>
    <div class="redes">
{REDES_HTML}    </div>
  </div>{nav}
</header>"""

def pie():
    return f"""
<footer><div class="pie">
  <div style="display:flex;gap:12px;align-items:center"><img src="/img/logo-512.png" alt="">
    <div>Noticias contadas con nuestras propias palabras a partir de medios confiables.<br>Cada noticia lleva el crédito y el enlace a su fuente original.</div></div>
  <div>Síguenos: <a href="https://instagram.com/{INSTAGRAM}" target="_blank" rel="noopener">Instagram</a> · <a href="https://x.com/{INSTAGRAM}" target="_blank" rel="noopener">X</a> @{INSTAGRAM}<br>
    También: <a href="https://divisasrd.com" target="_blank" rel="noopener">DivisasRD.com</a> ·
    <a href="https://kiloclarord.com" target="_blank" rel="noopener">KiloClaroRD.com</a></div>
  <div class="legal"><a href="/quienes-somos.html">Quiénes somos</a> · <a href="/contacto.html">Contacto</a> ·
    <a href="/privacidad.html">Política de privacidad</a> · aldiardnoticias@gmail.com</div>
</div></footer>"""

def pagina_nota(n):
    return f"/n/{n['id']}.html"

def botones_propios(n):
    dst = destino(n)
    if dst:
        return (f'<a class="directo" href="{dst["url"]}" target="_blank" rel="noopener">'
                f'{html.escape(dst["texto"])} en {dst["sitio"]} →</a>')
    return "".join(f'<a class="extra" href="{e["url"]}" target="_blank" rel="noopener">'
                   f'{html.escape(e["texto"])} en {e["sitio"]} →</a>' for e in extras(n))

def tarjeta(n, grande=False):
    c = clase(n["seccion"])
    dst = destino(n)
    fuente = html.escape(enlace_fuente(n))
    if n.get("parrafos"):  # tiene su propia página en aldiard.com
        enlace, nueva = pagina_nota(n), ""
        cierre = (f'<a class="leer" href="{enlace}">Leer la noticia completa →</a>'
                  f'<a class="fuente chica" href="{fuente}" target="_blank" rel="noopener">Fuente: {html.escape(n["fuente"])}</a>')
    elif dst:
        enlace, nueva = dst["url"], ' target="_blank" rel="noopener"'
        cierre = f'<a class="fuente chica" href="{fuente}" target="_blank" rel="noopener">Fuente: {html.escape(n["fuente"])}</a>'
    else:
        enlace, nueva = enlace_fuente(n), ' target="_blank" rel="noopener"'
        cierre = (f'<a class="fuente" href="{fuente}" target="_blank" rel="noopener">'
                  f'Leer en {html.escape(n["fuente"])} <span aria-hidden="true">→</span></a>')
    return f"""
<article class="nota {c}{' destacada' if grande else ''}" data-sec="{c}">
  <div class="meta"><span class="chip">{html.escape(n['seccion'])}</span>
    <span class="hora" data-fecha="{n['fecha']}"></span></div>
  <h2><a href="{html.escape(enlace)}"{nueva}>{html.escape(n['titulo'])}</a></h2>
  <p>{html.escape(n['resumen'])}</p>
  {botones_propios(n)}{cierre}
</article>"""

def generar_portada(todas, consejos):
    hoy = ahora().astimezone(HORA_RD).date().isoformat()
    con = next((c for c in reversed(consejos) if c["fecha"] == hoy), None)
    bloque_consejo = ""
    if con:
        bloque_consejo = f"""
<aside class="consejo {con['tema']}">
  <div class="cetq">💡 Consejo del día</div>
  <h2>{html.escape(con['titulo'])}</h2>
  <p>{html.escape(con['texto'])}</p>
  <a href="{con['url']}" target="_blank" rel="noopener">{html.escape(con['boton'])} en {con['sitio']} →</a>
</aside>"""
    lista = todas[:120]
    if lista:
        cuerpo = (tarjeta(lista[0], True) + bloque_consejo + '<div class="rejilla">'
                  + "".join(tarjeta(n) for n in lista[1:]) + "</div>")
    else:
        cuerpo = bloque_consejo + "<p class='vacio'>Pronto tendremos noticias aquí.</p>"
    nav = ('\n  <nav><button data-f="todas" aria-pressed="true">Todas</button>' + "".join(
        f'<button data-f="{cl}" aria-pressed="false">{html.escape(nombre)}</button>'
        for nombre, (_, _, cl, _) in SECCIONES.items()) + "</nav>")
    pagina = (cabeza("Al Día RD · Noticias de RD, de los dominicanos en EE.UU. y del mundo",
                     "Noticias de República Dominicana, de los dominicanos en Estados Unidos, internacionales, "
                     "famosos, precios y videojuegos, contadas de forma clara y con su fuente.",
                     SITIO + "/", SITIO + "/img/logo-512.png")
              + encabezado(nav) + f"\n<main>{cuerpo}</main>" + pie()
              + f"\n<script>\n{JS_TEMA}{JS_PORTADA}</script>\n</body></html>")
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)

def generar_notas(todas):
    """Una página propia para cada noticia larga: docs/n/<id>.html"""
    os.makedirs("docs/n", exist_ok=True)
    con_pagina = [n for n in todas if n.get("parrafos")]
    for n in con_pagina:
        c = clase(n["seccion"])
        url = SITIO + pagina_nota(n)
        img = SITIO + "/" + n["ig_img"] if n.get("ig_img") else SITIO + "/img/logo-512.png"
        cuerpo = "".join(f"<p>{html.escape(p)}</p>" for p in n["parrafos"])
        relacionadas = [m for m in con_pagina if m is not n and m["seccion"] == n["seccion"]][:5]
        rel = "".join(f'<a href="{pagina_nota(m)}">{html.escape(m["titulo"])}</a>' for m in relacionadas)
        q = urllib.parse.quote
        ld = json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "headline": n["titulo"][:110],
                         "datePublished": n["fecha"], "image": [img], "mainEntityOfPage": url,
                         "publisher": {"@type": "Organization", "name": "Al Día RD",
                                       "logo": {"@type": "ImageObject", "url": SITIO + "/img/logo-512.png"}}},
                        ensure_ascii=False)
        pagina = (cabeza(n["titulo"] + " · Al Día RD", n["resumen"], url, img,
                         f'\n<script type="application/ld+json">{ld}</script>')
                  + encabezado() + f"""
<main>
<a class="volver" href="/">← Todas las noticias</a>
<article class="articulo {c}">
  <div class="meta"><span class="chip">{html.escape(n['seccion'])}</span>
    <span class="hora" data-fecha="{n['fecha']}"></span></div>
  <h1>{html.escape(n['titulo'])}</h1>
  <div class="cuerpo">{cuerpo}</div>
  {botones_propios(n)}
  <div class="credito">Fuente: {html.escape(n['fuente'])} ·
    <a href="{html.escape(enlace_fuente(n))}" target="_blank" rel="noopener">Lee la noticia original →</a></div>
  <div class="compartir">
    <a href="https://wa.me/?text={q(n['titulo'] + ' ' + url)}" target="_blank" rel="noopener">Compartir en WhatsApp</a>
    <a href="https://x.com/intent/post?text={q(n['titulo'])}&url={q(url)}" target="_blank" rel="noopener">Compartir en X</a>
    <a href="https://www.facebook.com/sharer/sharer.php?u={q(url)}" target="_blank" rel="noopener">Compartir en Facebook</a>
  </div>
</article>
{('<section class="relacionadas"><h3>Más de ' + html.escape(n['seccion']) + '</h3>' + rel + '</section>') if rel else ''}
</main>""" + pie() + f"\n<script>\n{JS_TEMA}{JS_PORTADA}</script>\n</body></html>")
        with open(f"docs/n/{n['id']}.html", "w", encoding="utf-8") as f:
            f.write(pagina)
    vigentes = {f"{n['id']}.html" for n in con_pagina}
    for archivo in os.listdir("docs/n"):
        if archivo not in vigentes:
            os.remove(os.path.join("docs/n", archivo))

def generar_sitemap(todas):
    urls = [SITIO + "/"] + [SITIO + "/" + p for p in ("quienes-somos.html", "contacto.html", "privacidad.html")]
    urls += [SITIO + pagina_nota(n) for n in todas if n.get("parrafos")]
    with open("docs/sitemap.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.write("".join(f"  <url><loc>{u}</loc></url>\n" for u in urls))
        f.write("</urlset>\n")

def generar_html(todas, consejos):
    generar_portada(todas, consejos)
    generar_notas(todas)
    generar_sitemap(todas)

# ================= Principal =================
def main():
    os.makedirs("docs/ig", exist_ok=True)
    guardadas = cargar(ARCHIVO)
    consejos = cargar(ARCHIVO_CONSEJOS)
    nuevas = buscar(guardadas)
    todas = (nuevas + guardadas)[:MAX_GUARDADAS]
    todas = [n for n in todas if not re.search(BASURA, n["titulo"], re.I)]  # saca las viejas tipo "En Vivo"
    for n in todas:
        n["resumen"] = quitar_relleno(n["resumen"])
    calcular_tendencia(todas)
    elegida = elegir_para_instagram(todas)
    consejo_del_dia(todas, consejos)
    consejos = consejos[-30:]
    limpiar_imagenes(todas, consejos)
    guardar(ARCHIVO, todas)
    guardar(ARCHIVO_CONSEJOS, consejos)
    generar_html(todas, consejos)
    print(f"{len(nuevas)} noticias nuevas, {len(todas)} en total")
    print("RESUMEN DE LA CORRIDA:", " · ".join(f"{k}: {v}" for k, v in CUENTA.items()))
    if elegida:
        print(f"Para Instagram (tendencia {elegida.get('tendencia', 1)}): {elegida['titulo']}")

if __name__ == "__main__":
    main()
