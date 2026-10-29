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
# Internacionales: primero Estados Unidos y después los países que hablan español
PRIORIDAD_INTER = [gnews("Estados Unidos noticias hoy en español"), gnews("inmigración Estados Unidos latinos"),
                   gnews("site:univision.com noticias Estados Unidos"), gnews("site:telemundo.com noticias")]
FUENTES_INTER = [gnews(q) for q in (
    "Puerto Rico noticias hoy", "México noticias hoy", "Colombia noticias hoy", "Venezuela noticias hoy",
    "Cuba noticias hoy", "Haití noticias hoy", "Centroamérica noticias hoy", "Panamá noticias hoy",
    "España noticias hoy", "Argentina noticias hoy", "Chile Perú noticias hoy", "Ecuador Bolivia noticias hoy",
    "noticias América Latina hoy")] + [
    "https://news.google.com/rss/headlines/section/topic/WORLD?hl=es&gl=ES&ceid=ES:es"]  # portada de España
PRIORIDAD_FAMOSOS = [gnews(q) for q in (
    "farándula dominicana", "artistas dominicanos", "Alofoke", "site:deultimominuto.com farándula",
    "música urbana dominicana", "Premios Soberano")]
FUENTES_FAMOSOS = [gnews(q) for q in (
    "famosos Hollywood", "celebridades latinas Estados Unidos", "farándula hoy", "famosos noticias hoy",
    "cantante reguetón", "actriz telenovela", "estreno película Hollywood", "Latin Grammy",
    "site:hola.com famosos", "site:peopleenespanol.com", "site:infobae.com teleshow", "site:billboard.com/espanol",
    "site:univision.com famosos", "site:telemundo.com entretenimiento")]
FUENTES_PRECIOS = [gnews(q) for q in (
    "precios combustibles República Dominicana", "precio gasolina gasoil GLP semana MICM",
    "precio del dólar hoy República Dominicana", "precios canasta básica República Dominicana")]
FUENTES_JUEGOS = [gnews(q) for q in (
    "GTA 6", "videojuegos lanzamiento", "PlayStation 5 juegos", "Nintendo Switch 2", "Xbox juegos")]

# Se revisan primero en cada corrida, antes que los demás (De Último Minuto, directo y por Google News)
PRIORIDAD_RD = ["https://deultimominuto.com/feed/", gnews("site:deultimominuto.com")]
NOMBRES_MEDIOS = {"deultimominuto.com": "De Último Minuto", "deultimominuto.net": "De Último Minuto"}

SEC_RD, SEC_USA = "República Dominicana", "Dominicanos en EE.UU."
SEC_INTER, SEC_FAMOSOS = "Internacionales", "Famosos"
SEC_PRECIOS, SEC_JUEGOS = "Precios y combustibles", "Videojuegos"
# sección: (fuentes, máximo de noticias nuevas por corrida, clase, color)
# El programa corre cada hora: estos cupos dan como mucho 7 noticias nuevas por hora
# (ahora son más largas y cuestan más de IA, por eso son menos).
SECCIONES = {
    SEC_RD:      (FUENTES_RD,      3, "rd", (206, 17, 38)),   # primero RD
    SEC_USA:     (FUENTES_USA,     2, "us", (0, 45, 98)),     # después EE.UU.
    SEC_INTER:   (FUENTES_INTER,   1, "in", (15, 118, 110)),
    SEC_FAMOSOS: (FUENTES_FAMOSOS, 2, "fa", (190, 24, 93)),
    SEC_PRECIOS: (FUENTES_PRECIOS, 1, "pr", (180, 83, 9)),
    SEC_JUEGOS:  (FUENTES_JUEGOS,  1, "vj", (109, 40, 217)),
}
POR_FUENTE = 10         # noticias que mira de cada fuente (mirar no cuesta IA; solo las escogidas)

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
peopleenespanol.com hola.com billboard.com quien.com nytimes.com presidencia.gob.do
eltiempo.com semana.com elespectador.com milenio.com excelsior.com.mx elfinanciero.com.mx proceso.com.mx
lanacion.com.ar pagina12.com.ar latercera.com emol.com biobiochile.cl elcomercio.pe larepublica.pe
elnacional.com efectococuyo.com talcualdigital.com elnuevodia.com primerahora.com telemundopr.com
elsalvador.com prensalibre.com laprensa.hn elheraldo.hn nacion.com prensa.com laestrella.com.pa
confidencial.digital 14ymedio.com eluniverso.com primicias.ec elpais.com.uy elobservador.com.uy
eldeber.com.bo abc.com.py
20minutos.es elconfidencial.com eldiario.es lasexta.com antena3.com elperiodico.com cadenaser.com cope.es
tvnotas.com.mx eonline.com rollingstone.com lecturas.com
sportingnews.com laprensagrafica.com es.gizmodo.com gizmodo.com fayerwayer.com pokemon.com 3djuegos.com.mx
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
          r"loter[ií]as? (de|del) hoy|^hor[oó]scopo|^portada|\(opini[oó]n\)|\|\s*noticias\b|^noticias de |"
          r"^agenda del d[ií]a|^[uú]ltimas noticias|^lo m[aá]s le[ií]do|^titulares (de|del)|^resumen (de noticias|semanal)")
MAX_MEDIOS = 3          # una noticia junta hasta 3 medios que cuentan lo mismo
MIN_PARRAFOS = 3        # solo se publican las noticias con al menos 3 párrafos (las cortas se ocultan)
MIN_PALABRAS = 100        # palabras en total en la página (la de "El Guachi" pasa)
LLENAR_HASTA = 15       # mientras haya menos noticias largas que esto, se busca el doble por hora

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
           r"|no (ofrece|incluye|informa|detalla|especifica|da)|^nota:|respuesta anterior|tus instrucciones|no precisa|no permite|contenido disponible|sin (dar )?m[aá]s (detalles|contexto)|seg[uú]n (informa|indica) (la noticia|la nota)")

def quitar_relleno(resumen):
    """Quita las frases tipo 'el título no da más detalles' de los resúmenes viejos."""
    resumen = re.sub(r"\s*\((sin|no hay) [^)]*\)", "", resumen)
    coletilla = r",? seg[uú]n (informa|indica|se[nñ]ala|se desprende de) (la noticia|la nota|el t[ií]tulo|el titular)"
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
    """El periódico de la noticia: lo dice Google News, o el propio enlace si es el feed directo del medio."""
    href = (e.get("source") or {}).get("href", "")
    if not href and "news.google.com" not in e.get("link", ""):
        href = e.get("link", "")
    d = urllib.parse.urlparse(href).netloc.lower()
    return d[4:] if d.startswith("www.") else d

def nombre_medio(e, dom):
    return (e.get("source") or {}).get("title") or NOMBRES_MEDIOS.get(dom) or dom

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

def texto_respuesta(msg):
    """Junta todo el texto que devolvió la IA (puede venir en varios bloques)."""
    return "".join(getattr(b, "text", "") or "" for b in msg.content
                   if getattr(b, "type", "text") == "text").strip()

def pedir_ia(pedido, max_tokens):
    """Le pide algo a la IA sin el modo de 'pensar' (que se comía todo el espacio y dejaba la respuesta vacía)."""
    args = dict(model=MODELO, max_tokens=max_tokens, messages=[{"role": "user", "content": pedido}])
    try:
        msg = cliente().messages.create(thinking={"type": "disabled"}, **args)
    except Exception as err:
        if "thinking" not in str(err).lower():
            raise
        msg = cliente().messages.create(**args)  # este modelo no acepta esa opción: se pide normal
    t = texto_respuesta(msg)
    if not t:
        tipos = ",".join(getattr(b, "type", "?") for b in msg.content)
        raise ValueError(f"la IA no devolvió texto (motivo: {getattr(msg, 'stop_reason', '?')}, bloques: {tipos or 'ninguno'})")
    return t

INSTRUCCIONES = """Eres redactor de Al Día RD, un medio digital dominicano. Te paso VERSIONES de una misma noticia
publicadas por medios distintos. Escribe UNA sola noticia nuestra con estas reglas:
- Usa tus propias palabras y tu propia estructura. No sigas el orden de ningún original ni cambies palabras
  frase por frase. Primero lo esencial (qué pasó, quién, cuándo, dónde), después el contexto y los detalles,
  y al final lo que viene, si los textos lo dicen.
- Si hay varios medios, junta lo que aporta cada uno. Si se contradicen en un dato, dilo claramente
  (por ejemplo: "Diario Libre informa X, mientras que Listín Diario indica Y"). Si coinciden, no hace falta nombrarlos.
- Solo hechos que estén en los textos. No inventes, no supongas, no opines, no exageres.
  Copia exactos los nombres, cifras y fechas.
- LARGO: LARGO_AQUI
- El GANCHO es lo que se ve en la portada y en Instagram: dice qué pasó, pero se guarda los detalles, las cifras,
  las reacciones y el desenlace para el TEXTO, de forma que den ganas de entrar a leer. Debe ser verdadero:
  nada de exageraciones ni frases como "no lo vas a creer". El TEXTO no empieza repitiendo el GANCHO: lo amplía.
- CLAVES son 3 o 4 datos concretos de la noticia, uno por línea, empezando con "- ".
- IMPORTA explica en 1 o 2 oraciones qué significa esto para un dominicano en RD o en EE.UU. (su bolsillo, su
  seguridad, su comunidad, su país). Solo si se desprende de los hechos; si no tiene relación, escribe solo "-".
- Español claro y neutral, frases cortas, para dominicanos en RD y en EE.UU.
- No digas "el artículo", "el texto", "la nota" ni "según el título". Nunca escribas notas o comentarios para mí.
- Di a qué SECCION pertenece, escogiendo una de estas:
  República Dominicana (lo que pasa en el país) ·
  Dominicanos en EE.UU. (SOLO si la noticia trata de dominicanos o de la comunidad dominicana que vive en Estados
  Unidos; una noticia de la política o la vida de EE.UU. donde no salen dominicanos va en Internacionales) ·
  Internacionales (Estados Unidos y los países que hablan español; de otros países solo lo muy importante,
  como guerras, catástrofes o grandes noticias mundiales) · Precios y combustibles (precios, combustibles, dólar, canasta básica) ·
  Videojuegos (juegos, consolas, estudios de videojuegos) ·
  Famosos (SOLO personas famosas: artistas, cantantes, actores, cine, series, Hollywood, farándula, influencers y
  personalidades conocidas, por su vida, su carrera o sus polémicas; si una persona famosa, como el dueño de una gran
  empresa, sale por algo personal, sí es Famosos; pero si la noticia trata de una empresa, un producto, la política
  o los negocios, NO es Famosos) · Ninguna (si no encaja en ninguna).
- Responde CONFIABLE: no si no es una noticia concreta (por ejemplo la portada de un sitio), si es publicidad,
  un rumor sin fuente o una columna de opinión.

Responde EXACTAMENTE en este formato, sin nada antes ni después:
CONFIABLE: sí
SECCION: (una de la lista)
TITULO: (titular propio, distinto de los originales, máximo 14 palabras)
GANCHO: (1 o 2 frases cortas, máximo 170 caracteres)
CLAVES:
- (dato clave)
- (dato clave)
- (dato clave)
IMPORTA: (1 o 2 oraciones, o "-")
TEXTO:
(los párrafos, separados por una línea en blanco)

Después escribe la MISMA noticia en inglés para lectores en EE.UU.: traducción natural y fluida, no palabra
por palabra, con los mismos hechos, cifras y nombres (las instituciones dominicanas pueden quedar en español):
TITLE_EN: (headline)
HOOK_EN: (1 o 2 frases)
KEYS_EN:
- (key fact)
- (key fact)
- (key fact)
WHY_EN: (1 o 2 oraciones, o "-")
TEXT_EN:
(los mismos párrafos en inglés, separados por una línea en blanco)"""

def partir_parrafos(cuerpo):
    """Separa el texto en párrafos aunque la IA no deje una línea en blanco entre ellos."""
    limpio = lambda ps: [p for p in (re.sub(r"\s+", " ", x).strip() for x in ps)
                         if len(p) > 25 and not re.match(r"(nota|aclaraci[oó]n)\s*:", p, re.I)]
    ps = limpio(re.split(r"\n\s*\n", cuerpo))
    if len(ps) < 3:
        ps = limpio(cuerpo.splitlines())  # párrafos separados con un solo salto de línea
    if len(ps) < 3 and sum(len(p.split()) for p in ps) >= 110:
        # un solo bloque largo: se reparte por oraciones en 3 o 4 párrafos
        oraciones = re.split(r"(?<=[.!?»”])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«“])", " ".join(ps))
        k = 4 if len(oraciones) >= 8 else 3
        if len(oraciones) >= k:
            tam = -(-len(oraciones) // k)
            ps = [" ".join(oraciones[i:i + tam]) for i in range(0, len(oraciones), tam)]
    return ps

ETIQUETAS = ["CONFIABLE", "SECCION", "TITULO", "GANCHO", "RESUMEN", "CLAVES", "IMPORTA", "TEXTO",
             "TITLE_EN", "HOOK_EN", "KEYS_EN", "WHY_EN", "TEXT_EN"]

def bloques(t):
    """Parte la respuesta por etiquetas (TITULO:, TEXTO:, TITLE_EN:...). Tolera ** y espacios."""
    t = t.replace("**", "").replace("__", "")
    patron = re.compile(r"^[ \t#>*-]*(" + "|".join(ETIQUETAS) + r")[ \t]*:", re.I | re.M)
    ms = list(patron.finditer(t))
    salida = {}
    for k, m in enumerate(ms):
        fin = ms[k + 1].start() if k + 1 < len(ms) else len(t)
        salida.setdefault(m.group(1).upper(), t[m.end():fin].strip())
    return salida

def _linea(b, nombre):
    return (b.get(nombre, "").splitlines() or [""])[0].strip().strip('"“” ')

def _lista(b, nombre):
    items = [re.sub(r"^[-•*\d.)\s]+", "", c).strip() for c in b.get(nombre, "").splitlines()]
    return [c for c in items if len(c) > 8][:4]

def _importa(texto):
    texto = " ".join(texto.split())
    return "" if texto.strip(" -–—.") == "" or len(texto) < 25 else texto

def leer_formato(t):
    """Lee la respuesta de la IA (español y, si viene, inglés)."""
    b = bloques(t)
    titulo, parrafos = _linea(b, "TITULO"), partir_parrafos(b.get("TEXTO", ""))
    gancho = " ".join((b.get("GANCHO") or b.get("RESUMEN") or "").split()).strip('"“” ')
    if not titulo or not (gancho or parrafos):
        raise ValueError("respuesta sin el formato esperado: " + t[:200])
    gancho = gancho or parrafos[0][:170]
    r = {"confiable": not _linea(b, "CONFIABLE").lower().startswith("no"), "seccion": _linea(b, "SECCION"),
         "titulo": titulo, "resumen": gancho, "gancho": gancho, "claves": _lista(b, "CLAVES"),
         "importa": _importa(b.get("IMPORTA", "")), "parrafos": parrafos, "en": None}
    en_parrafos = partir_parrafos(b.get("TEXT_EN", ""))
    if _linea(b, "TITLE_EN") and len(en_parrafos) >= 2:
        r["en"] = {"titulo": _linea(b, "TITLE_EN"),
                   "gancho": " ".join(b.get("HOOK_EN", "").split()).strip('"“” ') or en_parrafos[0][:170],
                   "claves": _lista(b, "KEYS_EN"), "importa": _importa(b.get("WHY_EN", "")),
                   "parrafos": en_parrafos}
    return r

def redactar(versiones):
    """versiones: lista de {fuente, titulo, descripcion, texto}. Devuelve la noticia nuestra."""
    total = sum(len(v["texto"]) for v in versiones)
    if total >= 500:
        largo = "entre 4 y 6 párrafos (de 200 a 350 palabras en total) si hay información suficiente; si no alcanza, escribe menos, pero nunca rellenes ni inventes"
    else:
        largo = "solo tienes titulares y descripciones cortas: escribe 1 o 2 párrafos cortos con lo que dicen, sin agregar nada"
    datos = "\n\n".join(
        f"=== VERSIÓN {i + 1} — {v['fuente']} ===\nTitular: {v['titulo']}\nDescripción: {v['descripcion']}\n"
        + (f"Texto:\n{v['texto'][:3500]}" if v["texto"] else "")
        for i, v in enumerate(versiones))
    pedido = INSTRUCCIONES.replace("LARGO_AQUI", largo) + "\n\n" + datos
    ultimo = None
    for _ in range(2):  # si la primera respuesta viene mal, se intenta una vez más
        try:
            return leer_formato(pedir_ia(pedido, 4000))
        except ValueError as err:
            ultimo = err
    raise ultimo

def seccion_de_ia(texto):
    """Pasa lo que dijo la IA ('famosos', 'Precios...') al nombre exacto de la sección. '' si no se entiende."""
    t = _palabras(texto) | {w.lower() for w in re.findall(r"\w+", texto)}
    if "ninguna" in t:
        return "Ninguna"
    for nombre in SECCIONES:
        if _palabras(nombre) & t or nombre.lower() == texto.lower().strip():
            return nombre
    return ""

def verificar_seccion(seccion, texto):
    """Revisión final, sin IA: en 'Dominicanos en EE.UU.' tiene que hablarse de dominicanos."""
    dominicano = (r"dominican|quisqueyan|\brd\b|rep[uú]blica dominicana|fuerza del pueblo|\bfp\b|\bprm\b|\bpld\b"
                  r"|\bjce\b|junta central electoral|c[eé]dula|cedulaci[oó]n|consulado|di[aá]spora|abinader|banreservas")
    if seccion == SEC_USA and not re.search(dominicano, texto, re.I):
        return SEC_INTER
    return seccion

def similares(a, b, minimo=2):
    return len(_palabras(a) & _palabras(b)) >= minimo

def otras_versiones(titulo, dom_principal, vistos):
    """Busca la misma noticia en otros medios confiables (Google News por el titular)."""
    claves = sorted(_palabras(titulo), key=len, reverse=True)[:6]
    if len(claves) < 2:
        return []
    salida, doms = [], {dom_principal}
    for e in feedparser.parse(gnews(" ".join(claves))).entries[:12]:
        dom = dominio(e)
        fuente = e.get("source", {}).get("title", "Fuente")
        t = titulo_sin_fuente(limpiar(e.get("title", "")), fuente)
        if dom in doms or not es_confiable(dom) or e.get("link") in vistos or not similares(titulo, t, 3):
            continue
        doms.add(dom)
        salida.append((e, dom, fuente, t))
        if len(salida) >= MAX_MEDIOS - 1:
            break
    return salida

CUENTA = {"tasa/combustibles (usamos datos propios)": 0, "ya vistas": 0, "ya cubiertas": 0, "no confiables": 0, "opinión": 0, "con texto leído": 0,
          "sin texto": 0, "medios juntados": 0, "error IA": 0, "descartadas por la IA": 0, "cambiadas de sección": 0, "largas": 0, "ocultas (cortas)": 0}

def buscar(guardadas):
    vistos = ({n["link"] for n in guardadas} | {n["titulo"] for n in guardadas}
              | {n.get("titulo_original", "") for n in guardadas})
    # noticias ya publicadas (no cuentan las ocultas: si un periódico no dejó leerla, se intenta con otro)
    recientes = [n.get("titulo_original") or n["titulo"] for n in guardadas
                 if fecha(n) > ahora() - timedelta(hours=30) and not n.get("oculta")]
    nuevas = []
    llenar = len(visibles(guardadas)) < LLENAR_HASTA
    if llenar:
        print(f"Modo llenado: hay menos de {LLENAR_HASTA} noticias largas, se busca el doble esta hora.")
    for seccion, (fuentes, cupo, _, _) in SECCIONES.items():
        cupo = cupo * 2 if llenar else cupo
        de_esta, intentos = 0, 0
        prioridad = {SEC_RD: PRIORIDAD_RD, SEC_INTER: PRIORIDAD_INTER, SEC_FAMOSOS: PRIORIDAD_FAMOSOS}.get(seccion, [])
        orden = prioridad + rotar(fuentes)
        for url in orden:
            for e in feedparser.parse(url).entries[:POR_FUENTE]:
                if de_esta >= cupo or intentos >= cupo * 3:
                    break
                fuente = nombre_medio(e, dominio(e))
                titulo = titulo_sin_fuente(limpiar(e.get("title", "")), fuente)
                link = e.get("link", "")
                if not titulo or not link or link in vistos or titulo in vistos:
                    CUENTA["ya vistas"] += 1
                    continue
                if re.search(BASURA, titulo, re.I) or len(titulo.split()) < 4:
                    continue
                if es_tasa_o_precios_de_periodico(titulo):
                    CUENTA["tasa/combustibles (usamos datos propios)"] += 1
                    vistos.update((link, titulo))
                    continue
                if any(similares(titulo, r, 3) for r in recientes):
                    CUENTA["ya cubiertas"] += 1  # ya publicamos esa misma noticia
                    vistos.update((link, titulo))
                    continue
                dom = dominio(e)
                if not es_confiable(dom):
                    CUENTA["no confiables"] += 1
                    print("Fuente no confiable, se salta:", dom or fuente)
                    continue
                intentos += 1
                grupo = [(e, dom, fuente, titulo)] + otras_versiones(titulo, dom, vistos)
                versiones = []
                for ent, d, f, t in grupo:
                    vistos.update((ent.get("link", ""), t))
                    url_real, texto = leer_articulo(ent.get("link", ""))
                    if url_real and re.search(OPINION, url_real, re.I):
                        continue
                    print(f"[{seccion}] {f}: texto leído {len(texto)} letras -> {url_real or 'sin enlace'}")
                    CUENTA["con texto leído" if len(texto) >= 500 else "sin texto"] += 1
                    versiones.append({"fuente": f, "dominio": d, "titulo": t, "url": url_real or ent.get("link", ""),
                                      "descripcion": limpiar(ent.get("summary", "")), "texto": texto})
                if not versiones:
                    CUENTA["opinión"] += 1
                    print("Es opinión o editorial, se salta:", titulo)
                    continue
                def oculta(motivo):  # se guarda escondida para no volver a gastar IA en ella
                    nuevas.append({"id": hashlib.md5(link.encode()).hexdigest()[:10], "titulo": titulo,
                                   "titulo_original": titulo, "resumen": "", "parrafos": [], "link": link,
                                   "fuente": fuente, "dominio": dom, "seccion": seccion, "oculta": motivo, "v": 2,
                                   "fecha": ahora().isoformat()})
                if sum(len(v["texto"]) for v in versiones) < 500:
                    CUENTA["ocultas (cortas)"] += 1
                    print("No se pudo leer el artículo; no se publica para no salir corta:", titulo)
                    oculta("sin texto")
                    continue
                try:
                    r = redactar(versiones)
                except Exception as err:
                    CUENTA["error IA"] += 1
                    print("Error IA:", repr(err)[:400])
                    continue
                if not r["confiable"]:
                    CUENTA["descartadas por la IA"] += 1
                    print("La IA la descartó (no es noticia, rumor, opinión o publicidad):", titulo)
                    continue
                sec_final = seccion
                sec_ia = seccion_de_ia(r.get("seccion", ""))
                if sec_ia == "Ninguna":
                    CUENTA["descartadas por la IA"] += 1
                    print("No encaja en ninguna sección, se salta:", titulo)
                    continue
                if sec_ia and sec_ia != seccion:
                    CUENTA["cambiadas de sección"] += 1
                    print(f"Cambiada de sección: {seccion} -> {sec_ia}: {titulo}")
                    sec_final = sec_ia
                sec_final = verificar_seccion(sec_final, r["titulo"] + " " + " ".join(r["parrafos"]))
                CUENTA["medios juntados"] += len(versiones) - 1
                if not es_larga(r):
                    CUENTA["ocultas (cortas)"] += 1
                    palabras = sum(len(p.split()) for p in r["parrafos"])
                    print(f"Salió corta ({len(r['parrafos'])} párrafos, {palabras} palabras, "
                          f"{sum(len(v['texto']) for v in versiones)} letras leídas); se oculta:", titulo)
                    oculta("corta")
                    continue
                CUENTA["largas"] += 1
                principal = max(versiones, key=lambda v: len(v["texto"]))  # la más completa va de primera
                versiones.sort(key=lambda v: v is not principal)
                nuevas.append({"id": hashlib.md5(link.encode()).hexdigest()[:10],
                               "titulo": r["titulo"], "titulo_original": titulo,
                               "resumen": r["resumen"], "gancho": r["gancho"], "parrafos": r["parrafos"],
                               "claves": r["claves"], "importa": r["importa"], "en": r["en"],
                               "link": link, "url": principal["url"],
                               "fuente": principal["fuente"], "dominio": principal["dominio"],
                               "fuentes": [{"nombre": v["fuente"], "url": v["url"]} for v in versiones],
                               "seccion": sec_final, "fecha": ahora().isoformat()})
                recientes.append(titulo)
                if sec_final == seccion:  # si se fue a otra sección, no gasta el cupo de esta
                    de_esta += 1
    return nuevas

def es_larga(n):
    """Una noticia con contenido de verdad: la única que se muestra en la página y en Instagram."""
    ps = n.get("parrafos") or []
    # cuenta todo lo que se lee en la página: párrafos + "En pocas palabras" + "¿Por qué te importa?"
    total = sum(len(x.split()) for x in ps + (n.get("claves") or []) + [n.get("importa") or ""])
    return not n.get("oculta") and len(ps) >= MIN_PARRAFOS and total >= MIN_PALABRAS

def visibles(todas):
    return [n for n in todas if es_larga(n)]

def enlace_fuente(n):
    return n.get("url") or n["link"]

def lista_fuentes(n):
    return n.get("fuentes") or [{"nombre": n["fuente"], "url": enlace_fuente(n)}]

def nombres_fuentes(n):
    nombres = [f["nombre"] for f in lista_fuentes(n)]
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]

# ================= Noticias con datos propios (tasa del dólar y combustibles) =================
# Estas noticias NO salen de periódicos: se escriben con los datos del servidor de Divisas RD,
# que toma las tasas de cada banco o agente y los combustibles oficiales del MICM.
DATOS_URL = "https://divisas-rd.juanbatista88.workers.dev"
ARCHIVO_DATOS = "docs/datos.json"
HORA_TASA = 9   # a partir de las 9 a. m. (hora RD) se publica la tasa del día

# Titulares de periódicos sobre la tasa del día o los precios de la semana: esos ya no se usan
TASA_O_PRECIOS_DE_PERIODICO = (
    r"(tasa|precio|cotizaci[oó]n) del d[oó]lar|d[oó]lar (hoy|cierra|abre|amanece|se cotiza|se vende|se compra)"
    r"|tasa de cambio (hoy|del d[ií]a)|a c[oó]mo est[aá] el d[oó]lar"
    r"|precios? de (los )?combustibles|combustibles? (se mantienen|seguir[aá]n|suben|bajan|congelad|sin cambio)"
    r"|precios? de la gasolina|(gasolina|gasoil|glp).{0,40}(se mantiene|sube|baja|congela|semana)")
NO_ES_SOLO_PRECIO = (r"protest|huelga|\bparo\b|marcha|\bley\b|proyecto|congreso|diputad|senad|tribunal|"
                     r"destitu|renunci|cancelad|arrest|denuncia|cuestiona|critica|reclama|partido")

def es_tasa_o_precios_de_periodico(titulo):
    t = titulo.lower()
    return bool(re.search(TASA_O_PRECIOS_DE_PERIODICO, t)) and not re.search(NO_ES_SOLO_PRECIO, t)

def bajar_json(ruta):
    import urllib.request
    pedido = urllib.request.Request(DATOS_URL + ruta, headers={"User-Agent": "AlDiaRD/1.0"})
    with urllib.request.urlopen(pedido, timeout=25) as r:
        return json.load(r)

INSTRUCCIONES_DATOS = """Eres redactor de Al Día RD, un medio digital dominicano. Te paso DATOS (no una noticia de otro medio).
Escribe una noticia propia, útil y clara para dominicanos en RD y en EE.UU., usando SOLO estos números, exactos.
- QUE_ES
- No inventes cifras, causas ni pronósticos. Si un dato no viene, no lo menciones.
- Explica qué subió, qué bajó y qué se mantuvo (si hay comparación), y qué significa para el bolsillo.
- El GANCHO dice de qué va sin dar todos los números, para que den ganas de entrar.
- LARGO: entre 3 y 5 párrafos (de 150 a 300 palabras).
- No digas "según los datos que me pasaste" ni hables de ti.

Responde EXACTAMENTE en este formato:
CONFIABLE: sí
SECCION: Precios y combustibles
TITULO: (titular, máximo 14 palabras)
GANCHO: (1 o 2 frases cortas)
CLAVES:
- (dato clave)
- (dato clave)
- (dato clave)
IMPORTA: (1 o 2 oraciones)
TEXTO:
(los párrafos, separados por una línea en blanco)

Después la MISMA noticia en inglés natural para lectores en EE.UU.:
TITLE_EN: (headline)
HOOK_EN: (1 o 2 frases)
KEYS_EN:
- (key fact)
- (key fact)
- (key fact)
WHY_EN: (1 o 2 oraciones)
TEXT_EN:
(los párrafos en inglés, separados por una línea en blanco)"""

def redactar_datos(que_es, datos):
    pedido = (INSTRUCCIONES_DATOS.replace("QUE_ES", que_es) + "\n\nDATOS (JSON):\n"
              + json.dumps(datos, ensure_ascii=False, indent=1))
    ultimo = None
    for _ in range(2):
        try:
            return leer_formato(pedir_ia(pedido, 4000))
        except ValueError as err:
            ultimo = err
    raise ultimo

def nota_de_datos(clave, r, fuente_nombre, fuente_url, link):
    return {"id": hashlib.md5(clave.encode()).hexdigest()[:10], "titulo": r["titulo"], "titulo_original": clave,
            "resumen": r["resumen"], "gancho": r["gancho"], "parrafos": r["parrafos"], "claves": r["claves"],
            "importa": r["importa"], "en": r["en"], "link": link, "url": fuente_url, "fuente": fuente_nombre,
            "dominio": urllib.parse.urlparse(fuente_url).netloc, "seccion": SEC_PRECIOS, "oficial": True,
            "fuentes": [{"nombre": fuente_nombre, "url": fuente_url}], "fecha": ahora().isoformat()}

def _promedio(valores):
    v = [x for x in valores if isinstance(x, (int, float))]
    return round(sum(v) / len(v), 2) if v else None

def nota_tasa(datos_previos):
    """Una vez al día: la tasa del dólar con los datos de Divisas RD, comparada con ayer."""
    ahora_rd = ahora().astimezone(HORA_RD)
    hoy = ahora_rd.date().isoformat()
    if ahora_rd.hour < HORA_TASA or datos_previos.get("tasa", {}).get("fecha") == hoy:
        return None
    t = bajar_json("/tasas")
    ents = [e for e in t.get("entidades", []) if e.get("compra") or e.get("venta")]
    bancos = [e for e in ents if e.get("tipo") == "banco"]
    if len(ents) < 3:
        return None
    resumen = {
        "fecha": hoy,
        "promedio_bancos": {"compra": _promedio(e.get("compra") for e in bancos),
                            "venta": _promedio(e.get("venta") for e in bancos)},
        "quien_paga_mas_por_tus_dolares": max((e for e in ents if e.get("compra")), key=lambda e: e["compra"]),
        "quien_vende_mas_barato": min((e for e in ents if e.get("venta")), key=lambda e: e["venta"]),
        "entidades": [{k: e.get(k) for k in ("nombre", "tipo", "compra", "venta")} for e in ents],
    }
    anterior = datos_previos.get("tasa")
    if anterior:
        resumen["ayer_promedio_bancos"] = anterior.get("promedio_bancos")
    r = redactar_datos("Es la tasa del dólar de hoy en República Dominicana: compra (lo que te pagan por cada "
                       "dólar) y venta (lo que cuesta comprar un dólar) en bancos, agentes de cambio y remesadoras. "
                       "Di dónde conviene cambiar.", resumen)
    datos_previos["tasa"] = {"fecha": hoy, "promedio_bancos": resumen["promedio_bancos"]}
    return nota_de_datos("tasa-" + hoy, r, "DivisasRD.com (tasas de cada banco y agente)",
                         "https://divisasrd.com", "https://divisasrd.com/#bancos?d=" + hoy)

def nota_combustibles(datos_previos):
    """Cada semana, cuando el MICM publica los precios nuevos: comparación con la semana anterior."""
    c = bajar_json("/combustibles").get("rd") or {}
    semana, precios = c.get("semana"), c.get("precios") or []
    if not semana or not precios or datos_previos.get("combustibles", {}).get("semana") == semana:
        return None
    antes = datos_previos.get("combustibles", {}).get("precios", {})
    tabla = []
    for p in precios:
        fila = {"producto": p["nombre"], "unidad": p.get("unidad"), "precio_RD$": p.get("precio")}
        if p["clave"] in antes and isinstance(p.get("precio"), (int, float)):
            fila["semana_anterior_RD$"] = antes[p["clave"]]
            fila["cambio_RD$"] = round(p["precio"] - antes[p["clave"]], 2)
        tabla.append(fila)
    r = redactar_datos("Son los precios oficiales de los combustibles en República Dominicana para la semana "
                       f"del {semana}, fijados por el Ministerio de Industria, Comercio y Mipymes (MICM). "
                       "Si viene la semana anterior, compara.", {"semana": semana, "precios": tabla})
    datos_previos["combustibles"] = {"semana": semana, "precios": {p["clave"]: p.get("precio") for p in precios}}
    return nota_de_datos("combustibles-" + semana, r, "Ministerio de Industria, Comercio y Mipymes (MICM)",
                         "https://micm.gob.do", "https://divisasrd.com/#combustibles?s=" + urllib.parse.quote(semana))

def noticias_de_datos(guardadas):
    """Las noticias propias con datos. Si el servidor no responde, se salta sin problema."""
    datos = cargar(ARCHIVO_DATOS) or {}
    if isinstance(datos, list):
        datos = {}
    vistos = {n["link"] for n in guardadas}
    nuevas = []
    for hacer in (nota_tasa, nota_combustibles):
        try:
            n = hacer(datos)
            if n and n["link"] not in vistos and es_larga(n):
                nuevas.append(n)
                print("Noticia con datos propios:", n["titulo"])
        except Exception as err:
            print(f"No se pudo hacer la noticia de {hacer.__name__}:", repr(err)[:300])
    guardar(ARCHIVO_DATOS, datos)
    return nuevas

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
    recientes = [n for n in todas if fecha(n) > ahora() - timedelta(hours=36) and not n.get("oculta")]
    pal = {id(n): _palabras(n.get("titulo_original") or n["titulo"]) for n in recientes}
    for n in recientes:
        medios = {n["fuente"]}
        for m in recientes:
            if m is not n and len(pal[id(n)] & pal[id(m)]) >= 2:
                medios.add(m["fuente"])
        n["tendencia"] = max(len(medios), len(n.get("fuentes") or []))

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
    pie_f = ("Fuentes: " if len(lista_fuentes(n)) > 1 else "Fuente: ") + nombres_fuentes(n)
    while d.textlength(pie_f, font=f_pie) > 640 and len(pie_f) > 20:
        pie_f = pie_f[:-5].rstrip(" ,y") + "…"
    d.text((margen, 1166), pie_f, font=f_pie, fill=(90, 98, 112))
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
    pool = [n for n in visibles(todas) if n.get("ig") in (None, "") and n.get("id")
            and fecha(n) > limite and n.get("ig_intentos", 0) < 3
            and not re.search(BASURA, n["titulo"], re.I)]
    if not pool:
        return None
    peso = {SEC_RD: 2, SEC_USA: 1}  # RD primero, después EE.UU., después lo demás
    pool.sort(key=lambda n: (n.get("tendencia", 1) + peso.get(n["seccion"], 0) + (4 if n.get("oficial") else 0),
                             n["fecha"]), reverse=True)
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
    t = pedir_ia(
            f"Escribe UN consejo práctico para la gente de República Dominicana y los dominicanos en EE.UU. sobre {sobre}. "
            "Puedes inspirarte en los temas de estos titulares de hoy, sin repetirlos:\n- " + "\n- ".join(titulares[:6]) +
            "\n\nNo inventes cifras, tasas ni precios. Tono cercano y claro. "
            "Título de máximo 6 palabras. Texto de 2 oraciones, máximo 220 caracteres. "
            'Agrega también la traducción natural al inglés. '
            'Responde solo con JSON: {"titulo": "...", "texto": "...", "titulo_en": "...", "texto_en": "..."}', 1000)
    datos = json.loads(t[t.find("{"): t.rfind("}") + 1])
    return (datos["titulo"].strip(), datos["texto"].strip(),
            (datos.get("titulo_en") or "").strip(), (datos.get("texto_en") or "").strip())

def consejo_del_dia(todas, consejos):
    ahora_rd = ahora().astimezone(HORA_RD)
    hoy = ahora_rd.date().isoformat()
    if any(c["fecha"] == hoy for c in consejos) or ahora_rd.hour < HORA_CONSEJO:
        return None
    tema, del_dia = tema_del_dia(todas, consejos, hoy)
    patron = TEMA_DIVISAS if tema == "divisas" else TEMA_LUZ
    titulares = [n["titulo"] for n in del_dia if re.search(patron, texto_de(n))] or [n["titulo"] for n in del_dia]
    try:
        titulo, texto, titulo_en, texto_en = escribir_consejo(tema, titulares)
    except Exception as err:
        print("Consejo de respaldo:", err)
        lista = CONSEJOS_RESPALDO[tema]
        titulo, texto = lista[ahora_rd.toordinal() % len(lista)]
        titulo_en = texto_en = ""
    url, sitio = DIVISAS if tema == "divisas" else KILOCLARO
    c = {"fecha": hoy, "tema": tema, "titulo": titulo, "texto": texto, "url": url, "sitio": sitio,
         "titulo_en": titulo_en, "texto_en": texto_en,
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
.articulo .cuerpo p.entrada{font-size:20px;line-height:1.55;font-weight:600;color:var(--tinta)}
.claves,.importa{border-radius:12px;padding:16px 20px;margin:4px 0 20px}
.claves{background:var(--fondo);border:1px solid var(--linea)}
.claves h2,.importa h2{margin:0 0 8px;font-size:13px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--enlace)}
.claves ul{margin:0;padding-left:20px}
.claves li{margin:6px 0;line-height:1.5;color:var(--texto2);font-size:16px}
.importa{background:var(--extra-f);border:1px solid var(--extra-b)}
.importa h2{color:var(--extra-t)}
.articulo .cuerpo .importa p{margin:0;font-size:16.5px}
.idioma{font:800 13px Inter,system-ui,sans-serif;letter-spacing:.02em}
.solo-es{font-size:11px;font-weight:700;color:var(--gris);border:1px solid var(--linea);border-radius:999px;padding:1px 8px}
"""

REDES_HTML = """      <a class="red" href="https://instagram.com/§IG§" target="_blank" rel="noopener" aria-label="Instagram"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor"/></svg></a>
      <a class="red" href="https://x.com/§IG§" target="_blank" rel="noopener" aria-label="X"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.8 3h3.1l-6.8 7.7L22 21h-6.2l-4.9-6.3L5.3 21H2.2l7.2-8.3L2 3h6.4l4.4 5.8L17.8 3zm-1.1 16.2h1.7L7.4 4.7H5.6l11.1 14.5z"/></svg></a>
""".replace("§IG§", INSTAGRAM)

JS_TEMA = r"""var raiz=document.documentElement,btn=document.getElementById('tema');
function oscuro(){return raiz.dataset.theme?raiz.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches}
function icono(){btn.innerHTML=oscuro()?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>':'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'}
icono(); matchMedia('(prefers-color-scheme: dark)').addEventListener('change',icono);
btn.onclick=function(){var t=oscuro()?'light':'dark';raiz.dataset.theme=t;try{localStorage.setItem('tema',t)}catch(e){}icono()};
document.querySelectorAll('.idioma').forEach(function(a){a.onclick=function(){try{localStorage.setItem('idioma',a.dataset.lang)}catch(e){}}});
"""

JS_PORTADA = r"""var EN=document.documentElement.lang==='en';
var hoy=new Date().toLocaleDateString(EN?'en-US':'es-DO',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
document.getElementById('hoy').textContent=hoy.charAt(0).toUpperCase()+hoy.slice(1);
function hace(iso){var m=Math.round((Date.now()-new Date(iso))/60000);
 if(EN){if(m<1)return'just now';if(m<60)return m+' min ago';var h=Math.round(m/60);
  if(h<24)return h+(h==1?' hour ago':' hours ago');var d=Math.round(h/24);return d+(d==1?' day ago':' days ago');}
 if(m<1)return'ahora';if(m<60)return'hace '+m+' min';var h=Math.round(m/60);
 if(h<24)return'hace '+h+(h==1?' hora':' horas');var d=Math.round(h/24);return'hace '+d+(d==1?' día':' días');}
document.querySelectorAll('.hora').forEach(function(e){e.textContent='· '+hace(e.dataset.fecha)});
document.querySelectorAll('nav button').forEach(function(b){b.onclick=function(){
 document.querySelectorAll('nav button').forEach(function(x){x.setAttribute('aria-pressed',x===b)});
 document.querySelectorAll('.nota').forEach(function(n){n.classList.toggle('oculta',b.dataset.f!=='todas'&&n.dataset.sec!==b.dataset.f)});
 var c=document.querySelector('.consejo'); if(c)c.classList.toggle('oculta',b.dataset.f!=='todas');
}});
"""

# ---- Textos de la página en los dos idiomas ----
SECCIONES_EN = {SEC_RD: "Dominican Republic", SEC_USA: "Dominicans in the U.S.", SEC_INTER: "International",
                SEC_FAMOSOS: "Celebrities", SEC_PRECIOS: "Prices & Fuel", SEC_JUEGOS: "Video Games"}
BOTONES_EN = {"Mira la tasa del dólar en vivo": "See the live dollar rate",
              "Mira los precios de combustibles": "See today's fuel prices",
              "Calcula tu factura de luz": "Calculate your power bill",
              "Precios de combustibles": "Fuel prices", "Tasa del dólar hoy": "Today's dollar rate",
              "Mira la tasa en vivo": "See the live rate", "Calcula tu factura": "Calculate your bill"}
T = {
    "es": {"todas": "Todas", "leer": "Leer la noticia completa", "fuente": "Fuente", "fuentes": "Fuentes",
           "en": "en", "consejo": "💡 Consejo del día", "vacio": "Pronto tendremos noticias aquí.",
           "volver": "← Todas las noticias", "claves": "En pocas palabras", "importa": "¿Por qué te importa?",
           "credito1": "Redactada por Al Día RD a partir de lo publicado por",
           "credito_datos": "Redactada por Al Día RD con datos de",
           "credito2": "Redactada por Al Día RD a partir de lo publicado por estos medios",
           "wa": "Compartir en WhatsApp", "x": "Compartir en X", "fb": "Compartir en Facebook", "mas": "Más de",
           "titulo": "Al Día RD · Noticias de RD, de los dominicanos en EE.UU. y del mundo",
           "desc": "Noticias de República Dominicana, de los dominicanos en Estados Unidos, internacionales, "
                   "famosos, precios y videojuegos, contadas de forma clara y con su fuente.",
           "pie1": "Noticias contadas con nuestras propias palabras a partir de medios confiables.",
           "pie2": "Cada noticia lleva el crédito y el enlace a su fuente original.",
           "siguenos": "Síguenos", "tambien": "También", "quienes": "Quiénes somos", "contacto": "Contacto",
           "privacidad": "Política de privacidad", "cambiar": "Read in English", "otro": "EN",
           "tema": "Cambiar entre modo claro y oscuro", "solo_es": ""},
    "en": {"todas": "All", "leer": "Read the full story", "fuente": "Source", "fuentes": "Sources",
           "en": "at", "consejo": "💡 Tip of the day", "vacio": "English news coming soon.",
           "volver": "← All news", "claves": "Key points", "importa": "Why it matters",
           "credito1": "Written by Al Día RD based on reporting by",
           "credito_datos": "Written by Al Día RD using data from",
           "credito2": "Written by Al Día RD based on reporting by these outlets",
           "wa": "Share on WhatsApp", "x": "Share on X", "fb": "Share on Facebook", "mas": "More from",
           "titulo": "Al Día RD · News from the Dominican Republic, Dominicans in the U.S. and the world",
           "desc": "News from the Dominican Republic, Dominicans in the United States, Latin America, celebrities, "
                   "prices and video games, told clearly and with their sources.",
           "pie1": "News written in our own words from trusted outlets.",
           "pie2": "Every story credits and links to its original sources.",
           "siguenos": "Follow us", "tambien": "Also", "quienes": "About us", "contacto": "Contact",
           "privacidad": "Privacy policy", "cambiar": "Leer en español", "otro": "ES",
           "tema": "Switch between light and dark mode", "solo_es": "In Spanish"},
}

def tiene_en(n):
    return bool((n.get("en") or {}).get("parrafos"))

def dato(n, clave, lang):
    """El texto de la noticia en el idioma pedido (si no hay versión en inglés, queda el español)."""
    if lang == "en" and tiene_en(n):
        return n["en"].get(clave) or n.get(clave)
    return n.get(clave)

def nombre_seccion(seccion, lang):
    return SECCIONES_EN.get(seccion, seccion) if lang == "en" else seccion

def pagina_nota(n, lang="es"):
    return ("/en" if lang == "en" else "") + f"/n/{n['id']}.html"

def cabeza(titulo, descripcion, url, imagen, lang="es", alterna=None, extra=""):
    """alterna = dirección de la misma página en el otro idioma (o None si no existe)."""
    otra_es, otra_en = (alterna, url) if lang == "en" else (url, alterna)
    hreflang = ""
    if alterna:
        hreflang = (f'\n<link rel="alternate" hreflang="es" href="{otra_es}">'
                    f'\n<link rel="alternate" hreflang="en" href="{otra_en}">')
    # idioma automático: si el teléfono está en inglés abre la versión en inglés (y respeta lo que escoja la persona)
    auto = ""
    if alterna:
        destino_auto = alterna.replace(SITIO, "")
        if lang == "es":
            auto = ("<script>try{var p=localStorage.getItem('idioma'),bot=/bot|crawl|spider|slurp|google|bing/i.test(navigator.userAgent);"
                    f"if(p==='en'||(!p&&!bot&&(navigator.language||'').toLowerCase().indexOf('en')===0))location.replace('{destino_auto}')}}catch(e){{}}</script>")
        else:
            auto = f"<script>try{{if(localStorage.getItem('idioma')==='es')location.replace('{destino_auto}')}}catch(e){{}}</script>"
    return f"""<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{auto}
<title>{html.escape(titulo)}</title>
<meta name="description" content="{html.escape(descripcion)}">
<link rel="canonical" href="{url}">{hreflang}
<meta property="og:title" content="{html.escape(titulo)}">
<meta property="og:description" content="{html.escape(descripcion)}">
<meta property="og:image" content="{imagen}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="{'en_US' if lang == 'en' else 'es_DO'}">
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

def encabezado(lang="es", alterna=None, nav=""):
    t = T[lang]
    otro = "en" if lang == "es" else "es"
    destino_idioma = (alterna or (SITIO + ("/en/" if lang == "es" else "/"))).replace(SITIO, "")
    boton_idioma = (f'<a class="red idioma" href="{destino_idioma}" data-lang="{otro}" hreflang="{otro}" '
                    f'aria-label="{t["cambiar"]}" title="{t["cambiar"]}">{t["otro"]}</a>')
    return f"""
<header>
  <div class="barra">
    <img src="/img/logo-512.png" alt="">
    <a class="marca" href="{'/en/' if lang == 'en' else '/'}">Al Día <span>RD</span></a>
    <div class="hoy" id="hoy"></div>
    <div class="redes">
{REDES_HTML}      {boton_idioma}
      <button class="red" id="tema" aria-label="{t['tema']}"></button>
    </div>
  </div>{nav}
</header>"""

def pie(lang="es"):
    t = T[lang]
    return f"""
<footer><div class="pie">
  <div style="display:flex;gap:12px;align-items:center"><img src="/img/logo-512.png" alt="">
    <div>{t['pie1']}<br>{t['pie2']}</div></div>
  <div>{t['siguenos']}: <a href="https://instagram.com/{INSTAGRAM}" target="_blank" rel="noopener">Instagram</a> · <a href="https://x.com/{INSTAGRAM}" target="_blank" rel="noopener">X</a> @{INSTAGRAM}<br>
    {t['tambien']}: <a href="https://divisasrd.com" target="_blank" rel="noopener">DivisasRD.com</a> ·
    <a href="https://kiloclarord.com" target="_blank" rel="noopener">KiloClaroRD.com</a></div>
  <div class="legal"><a href="/quienes-somos.html">{t['quienes']}</a> · <a href="/contacto.html">{t['contacto']}</a> ·
    <a href="/privacidad.html">{t['privacidad']}</a> · aldiardnoticias@gmail.com</div>
</div></footer>"""

def _boton(texto, lang):
    return BOTONES_EN.get(texto, texto) if lang == "en" else texto

def botones_propios(n, lang="es"):
    en = T[lang]["en"]
    dst = destino(n)
    if dst:
        return (f'<a class="directo" href="{dst["url"]}" target="_blank" rel="noopener">'
                f'{html.escape(_boton(dst["texto"], lang))} {en} {dst["sitio"]} →</a>')
    return "".join(f'<a class="extra" href="{e["url"]}" target="_blank" rel="noopener">'
                   f'{html.escape(_boton(e["texto"], lang))} {en} {e["sitio"]} →</a>' for e in extras(n))

def texto_tarjeta(n, lang="es"):
    """Lo que se ve en la portada: el gancho, o el comienzo del resumen viejo cortado con '…'."""
    g = dato(n, "gancho", lang)
    if g:
        return g
    t = re.split(r"(?<=[.!?])\s+", n["resumen"].strip())[0]
    return t if len(t) <= 130 else t[:125].rsplit(" ", 1)[0] + "…"

def tarjeta(n, lang="es", grande=False):
    """Todas las tarjetas abren nuestra propia página de la noticia."""
    t = T[lang]
    propio = lang == "es" or tiene_en(n)          # ¿existe la noticia en este idioma?
    lang_n = lang if propio else "es"
    c = clase(n["seccion"])
    enlace = pagina_nota(n, lang_n)
    etiqueta = t["fuentes"] if len(lista_fuentes(n)) > 1 else t["fuente"]
    aviso = "" if propio else f' <span class="solo-es">{t["solo_es"]}</span>'
    return f"""
<article class="nota {c}{' destacada' if grande else ''}" data-sec="{c}">
  <div class="meta"><span class="chip">{html.escape(nombre_seccion(n['seccion'], lang))}</span>
    <span class="hora" data-fecha="{n['fecha']}"></span>{aviso}</div>
  <h2><a href="{enlace}"{'' if propio else ' hreflang="es"'}>{html.escape(dato(n, 'titulo', lang_n))}</a></h2>
  <p>{html.escape(texto_tarjeta(n, lang_n))}</p>
  {botones_propios(n, lang)}<a class="leer" href="{enlace}">{t['leer']} →</a>
  <span class="fuente chica">{etiqueta}: {html.escape(nombres_fuentes(n))}</span>
</article>"""

def generar_portada(todas, consejos, lang="es"):
    t = T[lang]
    hoy = ahora().astimezone(HORA_RD).date().isoformat()
    con = next((c for c in reversed(consejos) if c["fecha"] == hoy), None)
    bloque_consejo = ""
    if con and (lang == "es" or con.get("titulo_en")):
        ct = con.get("titulo_en") if lang == "en" else con["titulo"]
        cx = con.get("texto_en") if lang == "en" else con["texto"]
        bloque_consejo = f"""
<aside class="consejo {con['tema']}">
  <div class="cetq">{t['consejo']}</div>
  <h2>{html.escape(ct)}</h2>
  <p>{html.escape(cx)}</p>
  <a href="{con['url']}" target="_blank" rel="noopener">{html.escape(_boton(con['boton'], lang))} {t['en']} {con['sitio']} →</a>
</aside>"""
    lista = visibles(todas)
    if lang == "en":
        # primero las que ya están en inglés; si son pocas, se completan con las de español (marcadas)
        en_ingles = [n for n in lista if tiene_en(n)]
        lista = en_ingles if len(en_ingles) >= 12 else en_ingles + [n for n in lista if not tiene_en(n)]
    lista = lista[:120]
    if lista:
        # arriba, grande: la noticia de RD más reciente (si hay); después todas por orden de llegada
        top = next((n for n in lista[:15] if n["seccion"] == SEC_RD), lista[0])
        resto = [n for n in lista if n is not top]
        cuerpo = (tarjeta(top, lang, True) + bloque_consejo + '<div class="rejilla">'
                  + "".join(tarjeta(n, lang) for n in resto) + "</div>")
    else:
        cuerpo = bloque_consejo + f"<p class='vacio'>{t['vacio']}</p>"
    nav = (f'\n  <nav><button data-f="todas" aria-pressed="true">{t["todas"]}</button>' + "".join(
        f'<button data-f="{cl}" aria-pressed="false">{html.escape(nombre_seccion(nombre, lang))}</button>'
        for nombre, (_, _, cl, _) in SECCIONES.items()) + "</nav>")
    url = SITIO + ("/en/" if lang == "en" else "/")
    alterna = SITIO + ("/" if lang == "en" else "/en/")
    pagina = (cabeza(t["titulo"], t["desc"], url, SITIO + "/img/logo-512.png", lang, alterna)
              + encabezado(lang, alterna, nav) + f"\n<main>{cuerpo}</main>" + pie(lang)
              + f"\n<script>\n{JS_TEMA}{JS_PORTADA}</script>\n</body></html>")
    carpeta = "docs/en" if lang == "en" else "docs"
    os.makedirs(carpeta, exist_ok=True)
    with open(f"{carpeta}/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)

def generar_notas(todas, lang="es"):
    """Una página propia para cada noticia larga: docs/n/<id>.html y, en inglés, docs/en/n/<id>.html"""
    t = T[lang]
    carpeta = "docs/en/n" if lang == "en" else "docs/n"
    os.makedirs(carpeta, exist_ok=True)
    con_pagina = [n for n in visibles(todas) if lang == "es" or tiene_en(n)]
    for n in con_pagina:
        c = clase(n["seccion"])
        url = SITIO + pagina_nota(n, lang)
        otro = "en" if lang == "es" else "es"
        alterna = SITIO + pagina_nota(n, otro) if (otro == "es" or tiene_en(n)) else None
        img = SITIO + "/" + n["ig_img"] if n.get("ig_img") else SITIO + "/img/logo-512.png"
        titulo, gancho = dato(n, "titulo", lang), dato(n, "gancho", lang)
        claves, importa = dato(n, "claves", lang), dato(n, "importa", lang)
        cuerpo = ""
        if gancho:
            cuerpo += f'<p class="entrada">{html.escape(gancho)}</p>'
        if claves:
            cuerpo += (f'<div class="claves"><h2>{t["claves"]}</h2><ul>'
                       + "".join(f"<li>{html.escape(x)}</li>" for x in claves) + "</ul></div>")
        cuerpo += "".join(f"<p>{html.escape(p)}</p>" for p in (dato(n, "parrafos", lang) or [n["resumen"]]))
        if importa:
            cuerpo += f'<div class="importa"><h2>{t["importa"]}</h2><p>{html.escape(importa)}</p></div>'
        fuentes_html = " · ".join(
            f'<a href="{html.escape(f["url"])}" target="_blank" rel="noopener nofollow">{html.escape(f["nombre"])}</a>'
            for f in lista_fuentes(n))
        varias = len(lista_fuentes(n)) > 1
        relacionadas = [m for m in con_pagina if m is not n and m["seccion"] == n["seccion"]][:5]
        rel = "".join(f'<a href="{pagina_nota(m, lang)}">{html.escape(dato(m, "titulo", lang))}</a>'
                      for m in relacionadas)
        q = urllib.parse.quote
        ld = json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "headline": titulo[:110],
                         "inLanguage": lang, "datePublished": n["fecha"], "image": [img], "mainEntityOfPage": url,
                         "publisher": {"@type": "Organization", "name": "Al Día RD",
                                       "logo": {"@type": "ImageObject", "url": SITIO + "/img/logo-512.png"}}},
                        ensure_ascii=False)
        pagina = (cabeza(titulo + " · Al Día RD", gancho or n["resumen"], url, img, lang, alterna,
                         f'\n<script type="application/ld+json">{ld}</script>')
                  + encabezado(lang, alterna) + f"""
<main>
<a class="volver" href="{'/en/' if lang == 'en' else '/'}">{t['volver']}</a>
<article class="articulo {c}">
  <div class="meta"><span class="chip">{html.escape(nombre_seccion(n['seccion'], lang))}</span>
    <span class="hora" data-fecha="{n['fecha']}"></span></div>
  <h1>{html.escape(titulo)}</h1>
  <div class="cuerpo">{cuerpo}</div>
  {botones_propios(n, lang)}
  <div class="credito">{t['credito_datos'] if n.get('oficial') else (t['credito2'] if varias else t['credito1'])}:
    {fuentes_html}</div>
  <div class="compartir">
    <a href="https://wa.me/?text={q(titulo + ' ' + url)}" target="_blank" rel="noopener">{t['wa']}</a>
    <a href="https://x.com/intent/post?text={q(titulo)}&url={q(url)}" target="_blank" rel="noopener">{t['x']}</a>
    <a href="https://www.facebook.com/sharer/sharer.php?u={q(url)}" target="_blank" rel="noopener">{t['fb']}</a>
  </div>
</article>
{('<section class="relacionadas"><h3>' + t['mas'] + ' ' + html.escape(nombre_seccion(n['seccion'], lang)) + '</h3>' + rel + '</section>') if rel else ''}
</main>""" + pie(lang) + f"\n<script>\n{JS_TEMA}{JS_PORTADA}</script>\n</body></html>")
        with open(f"{carpeta}/{n['id']}.html", "w", encoding="utf-8") as f:
            f.write(pagina)
    vigentes = {f"{n['id']}.html" for n in con_pagina}
    for archivo in os.listdir(carpeta):
        if archivo not in vigentes:
            os.remove(os.path.join(carpeta, archivo))

def generar_sitemap(todas):
    urls = [SITIO + "/", SITIO + "/en/"] + [SITIO + "/" + p for p in ("quienes-somos.html", "contacto.html", "privacidad.html")]
    urls += [SITIO + pagina_nota(n) for n in visibles(todas)]
    urls += [SITIO + pagina_nota(n, "en") for n in visibles(todas) if tiene_en(n)]
    with open("docs/sitemap.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.write("".join(f"  <url><loc>{u}</loc></url>\n" for u in urls))
        f.write("</urlset>\n")

def generar_html(todas, consejos):
    for lang in ("es", "en"):
        generar_portada(todas, consejos, lang)
        generar_notas(todas, lang)
    generar_sitemap(todas)

# ================= Principal =================
class Registro:
    """Copia todo lo que el programa escribe en pantalla a docs/registro.txt, para revisarlo después."""
    def __init__(self, pantalla):
        self.pantalla, self.lineas = pantalla, []
    def write(self, t):
        self.pantalla.write(t)
        self.lineas.append(t)
    def flush(self):
        self.pantalla.flush()

def main():
    import sys
    reg = Registro(sys.stdout)
    sys.stdout = reg
    try:
        print("Corrida:", ahora().astimezone(HORA_RD).strftime("%Y-%m-%d %I:%M %p"), "(hora RD)")
        principal()
    finally:
        sys.stdout = reg.pantalla
        os.makedirs("docs", exist_ok=True)
        with open("docs/registro.txt", "w", encoding="utf-8") as f:
            f.write("".join(reg.lineas)[-60000:])

def principal():
    os.makedirs("docs/ig", exist_ok=True)
    guardadas = cargar(ARCHIVO)
    # las que se ocultaron por "cortas" con el error de los párrafos pegados se vuelven a intentar una vez
    guardadas = [n for n in guardadas if not (n.get("oculta") == "corta" and not n.get("v"))]
    consejos = cargar(ARCHIVO_CONSEJOS)
    nuevas = noticias_de_datos(guardadas) + buscar(guardadas)
    todas = (nuevas + guardadas)[:MAX_GUARDADAS]
    todas = [n for n in todas if not re.search(BASURA, n["titulo"], re.I)]  # saca las viejas tipo "En Vivo"
    for n in todas:
        n["resumen"] = quitar_relleno(n["resumen"])
        antes = n["seccion"]
        if n.get("parrafos"):  # solo las largas: las viejas cortas no tienen texto para decidir
            n["seccion"] = verificar_seccion(antes, n["titulo"] + " " + " ".join(n["parrafos"]))
        if n["seccion"] != antes:
            print(f"Corregida de sección: {antes} -> {n['seccion']}: {n['titulo']}")
        if (not n.get("oficial") and not n.get("oculta")
                and es_tasa_o_precios_de_periodico(n.get("titulo_original") or n["titulo"])):
            n["oculta"] = "datos propios"  # la tasa y los combustibles ahora salen con nuestros datos
            print("Se oculta (ahora usamos datos propios):", n["titulo"])
        if not n.get("id"):  # las más viejas no tenían número; lo necesitan para su página
            n["id"] = hashlib.md5(n["link"].encode()).hexdigest()[:10]
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
