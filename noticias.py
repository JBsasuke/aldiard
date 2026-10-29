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
    "eldia.com.do", "noticiassin.com", "cdn.com.do")]
FUENTES_USA = [gnews(q) for q in (
    "dominicanos Nueva York", "dominicanos New Jersey", "dominicanos Florida",
    "dominicanos Massachusetts", "dominicanos Pensilvania", "dominicanos Rhode Island",
    "comunidad dominicana Estados Unidos")]
FUENTES_INTER = [
    "https://news.google.com/rss/headlines/section/topic/WORLD?hl=es-419&gl=US&ceid=US:es-419",
    gnews("site:bbc.com/mundo"), gnews("site:cnnespanol.cnn.com"), gnews("noticias internacionales hoy")]
FUENTES_FAMOSOS = [gnews(q) for q in (
    "farándula dominicana", "artistas dominicanos", "famosos Hollywood",
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
# El programa corre cada hora: estos cupos dan como mucho 10 resúmenes por hora.
SECCIONES = {
    SEC_RD:      (FUENTES_RD,      3, "rd", (206, 17, 38)),
    SEC_USA:     (FUENTES_USA,     2, "us", (0, 45, 98)),
    SEC_INTER:   (FUENTES_INTER,   2, "in", (15, 118, 110)),
    SEC_FAMOSOS: (FUENTES_FAMOSOS, 1, "fa", (190, 24, 93)),
    SEC_PRECIOS: (FUENTES_PRECIOS, 1, "pr", (180, 83, 9)),
    SEC_JUEGOS:  (FUENTES_JUEGOS,  1, "vj", (109, 40, 217)),
}
POR_FUENTE = 3          # noticias que mira de cada fuente
MAX_GUARDADAS = 400
HORAS_IG = 12           # una noticia más vieja que esto ya no se sube a Instagram
HORA_CONSEJO = 9        # a partir de las 9 a. m. (hora RD) se prepara el consejo del día

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

# ================= Buscar noticias =================
def resumir(titulo, texto):
    msg = cliente().messages.create(
        model=MODELO, max_tokens=300,
        messages=[{"role": "user", "content":
            "Escribe un resumen corto (2-3 oraciones) en español, con tus propias palabras, "
            "neutral y sin inventar datos, de esta noticia. Si solo tienes el título, "
            "escribe una o dos oraciones con lo que dice el título, sin agregar detalles. "
            "Nunca menciones que falta información, que solo tienes el título o 'según el título'. "
            "No copies frases textuales. Responde solo con el resumen.\n\n"
            f"Título: {titulo}\nTexto: {texto}"}])
    return msg.content[0].text.strip()

def buscar(guardadas):
    vistos = {n["link"] for n in guardadas} | {n["titulo"] for n in guardadas}
    nuevas = []
    for seccion, (fuentes, cupo, _, _) in SECCIONES.items():
        de_esta = 0
        for url in fuentes:
            for e in feedparser.parse(url).entries[:POR_FUENTE]:
                if de_esta >= cupo:
                    break
                fuente = e.get("source", {}).get("title", "Fuente")
                titulo = titulo_sin_fuente(limpiar(e.get("title", "")), fuente)
                link = e.get("link", "")
                if not titulo or not link or link in vistos or titulo in vistos:
                    continue
                if re.search(BASURA, titulo, re.I) or len(titulo.split()) < 4:
                    continue
                try:
                    resumen = resumir(titulo, limpiar(e.get("summary", "")))
                except Exception as err:
                    print("Error IA:", err)
                    continue
                nuevas.append({"id": hashlib.md5(link.encode()).hexdigest()[:10],
                               "titulo": titulo, "resumen": resumen, "link": link,
                               "fuente": fuente, "seccion": seccion,
                               "fecha": ahora().isoformat()})
                vistos.update((link, titulo))
                de_esta += 1
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
    recientes = [n for n in todas if fecha(n) > ahora() - timedelta(hours=36)]
    pal = {id(n): _palabras(n["titulo"]) for n in recientes}
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
    margen, top, fondo = 70, 300, 1120
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
    f_pie = ImageFont.truetype(FUENTE_MEDIA, 34)
    d.line((margen, 1180, W - margen, 1180), fill=(220, 224, 232), width=3)
    d.text((margen, 1215), "Fuente: " + n["fuente"], font=f_pie, fill=(90, 98, 112))
    f_web = ImageFont.truetype(FUENTE_FUERTE, 34)
    web = sitio_propio(n)
    d.text((W - margen - d.textlength(web, font=f_web), 1215), web, font=f_web, fill=AZUL)
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
    d.rounded_rectangle((margen, 1150, margen + tw + 60, 1250), radius=50, fill=BLANCO)
    d.text((margen + 30, 1176), txt, font=f_bot, fill=fondo_c)
    img.save(ruta, "JPEG", quality=88)

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
    return mejor

def limpiar_imagenes(todas, consejos):
    """Borra las imágenes de más de 2 días (Instagram ya guardó su copia)."""
    limite = ahora() - timedelta(days=2)
    se_quedan = {n.get("ig_img") for n in todas
                 if n.get("ig_img") and (fecha(n) > limite or n.get("ig") == "pendiente")}
    se_quedan |= {c.get("ig_img") for c in consejos[-3:]}
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
    except Exception as err:
        print("Error imagen consejo:", err)
    consejos.append(c)
    print(f"Consejo del día ({tema}): {titulo}")
    return c

# ================= Página web =================
def generar_html(todas, consejos):
    def tarjeta(n, grande=False):
        c = clase(n["seccion"])
        dst = destino(n)
        enlace = dst["url"] if dst else n["link"]
        if dst:
            botones = (f'<a class="directo" href="{dst["url"]}" target="_blank" rel="noopener">'
                       f'{html.escape(dst["texto"])} en {dst["sitio"]} →</a>'
                       f'<a class="fuente chica" href="{html.escape(n["link"])}" target="_blank" rel="noopener">'
                       f'Fuente: {html.escape(n["fuente"])}</a>')
        else:
            botones = "".join(f'<a class="extra" href="{e["url"]}" target="_blank" rel="noopener">'
                              f'{html.escape(e["texto"])} en {e["sitio"]} →</a>' for e in extras(n))
            botones += (f'<a class="fuente" href="{html.escape(n["link"])}" target="_blank" rel="noopener">'
                        f'Leer en {html.escape(n["fuente"])} <span aria-hidden="true">→</span></a>')
        return f"""
<article class="nota {c}{' destacada' if grande else ''}" data-sec="{c}">
  <div class="meta"><span class="chip">{html.escape(n['seccion'])}</span>
    <span class="hora" data-fecha="{n['fecha']}"></span></div>
  <h2><a href="{html.escape(enlace)}" target="_blank" rel="noopener">{html.escape(n['titulo'])}</a></h2>
  <p>{html.escape(n['resumen'])}</p>
  {botones}
</article>"""
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
    botones_nav = "".join(
        f'<button data-f="{cl}" aria-pressed="false">{html.escape(nombre)}</button>'
        for nombre, (_, _, cl, _) in SECCIONES.items())
    pagina = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Al Día RD · Noticias de RD y de los dominicanos en EE.UU.</title>
<meta name="description" content="Resúmenes de noticias de República Dominicana, de los dominicanos en Estados Unidos y del mundo, con enlace a la fuente original.">
<meta property="og:title" content="Al Día RD">
<meta property="og:description" content="Noticias de República Dominicana y de los dominicanos en EE.UU.">
<meta property="og:image" content="{SITIO}/img/logo-512.png">
<meta property="og:url" content="{SITIO}">
<meta name="theme-color" content="#002d62">
<link rel="icon" type="image/png" href="img/favicon.png">
<link rel="apple-touch-icon" href="img/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800;900&display=swap" rel="stylesheet">
<style>
:root{{--azul:#002d62;--rojo:#ce1126;--ambar:#b45309;--morado:#6d28d9;--rosa:#be185d;--verdeazul:#0f766e;--tinta:#141821;--gris:#5a6270;--linea:#e3e6ec;--fondo:#f5f6f8;--blanco:#fff}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--fondo);color:var(--tinta);-webkit-font-smoothing:antialiased}}
a{{color:inherit}}
.franja{{height:5px;background:linear-gradient(90deg,var(--azul) 0 50%,var(--rojo) 50% 100%)}}
header{{background:var(--blanco);border-bottom:1px solid var(--linea);position:sticky;top:0;z-index:10}}
.barra{{max-width:1100px;margin:auto;padding:12px 16px;display:flex;align-items:center;gap:12px}}
.barra img{{width:44px;height:44px;border-radius:10px}}
.marca{{font-weight:900;font-size:22px;letter-spacing:-.02em;color:var(--azul);text-decoration:none}}
.marca span{{color:var(--rojo)}}
.hoy{{margin-left:auto;color:var(--gris);font-size:14px}}
nav{{max-width:1100px;margin:auto;padding:0 16px 10px;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}}
nav button{{font:600 14px Inter,system-ui,sans-serif;border:1px solid var(--linea);background:var(--blanco);color:var(--tinta);padding:8px 14px;border-radius:999px;cursor:pointer;white-space:nowrap}}
nav button[aria-pressed=true]{{background:var(--azul);border-color:var(--azul);color:#fff}}
main{{max-width:1100px;margin:auto;padding:20px 16px 40px}}
.nota{{background:var(--blanco);border:1px solid var(--linea);border-radius:14px;padding:18px 20px;display:flex;flex-direction:column;gap:8px;border-top:4px solid var(--rojo)}}
.meta{{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--gris)}}
.chip{{font-weight:800;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--rojo)}}
.nota.us{{border-top-color:var(--azul)}} .us .chip{{color:var(--azul)}}
.nota.pr{{border-top-color:var(--ambar)}} .pr .chip{{color:var(--ambar)}}
.nota.vj{{border-top-color:var(--morado)}} .vj .chip{{color:var(--morado)}}
.nota.fa{{border-top-color:var(--rosa)}} .fa .chip{{color:var(--rosa)}}
.nota.in{{border-top-color:var(--verdeazul)}} .in .chip{{color:var(--verdeazul)}}
.nota h2{{margin:0;font-size:19px;line-height:1.3;font-weight:800;letter-spacing:-.01em}}
.nota h2 a{{text-decoration:none}} .nota h2 a:hover{{text-decoration:underline}}
.nota p{{margin:0;color:#353b47;line-height:1.55;font-size:15.5px}}
.fuente{{margin-top:auto;padding-top:6px;font-weight:600;font-size:14px;color:var(--azul);text-decoration:none}}
.fuente:hover{{text-decoration:underline}}
.fuente.chica{{font-weight:500;font-size:12.5px;color:var(--gris);padding-top:2px}}
.extra{{align-self:flex-start;font-size:13.5px;font-weight:600;text-decoration:none;color:#0f5132;background:#e8f5ee;border:1px solid #cde9d9;padding:6px 10px;border-radius:8px}}
.directo{{margin-top:auto;align-self:flex-start;font-size:15px;font-weight:800;text-decoration:none;color:#fff;background:#157347;padding:10px 14px;border-radius:10px}}
.extra:hover,.directo:hover{{text-decoration:underline}}
.destacada{{padding:26px 28px;margin-bottom:18px}}
.destacada h2{{font-size:clamp(24px,3.4vw,34px);font-weight:900;line-height:1.15}}
.destacada p{{font-size:17px;max-width:760px}}
.consejo{{border-radius:14px;padding:20px 24px;margin:0 0 18px;color:#fff;background:#0c4a6e}}
.consejo.kiloclaro{{background:#146e3c}}
.cetq{{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#fde68a}}
.consejo h2{{margin:6px 0 4px;font-size:22px;font-weight:900}}
.consejo p{{margin:0 0 12px;line-height:1.5;color:#e6f0ec;max-width:760px}}
.consejo a{{display:inline-block;background:#fff;color:#0f2b20;font-weight:800;text-decoration:none;padding:9px 14px;border-radius:999px;font-size:14px}}
.rejilla{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}}
.oculta{{display:none}}
.vacio{{text-align:center;color:var(--gris);padding:60px 0}}
footer{{background:var(--azul);color:#cfd8e6;font-size:14px}}
.pie{{max-width:1100px;margin:auto;padding:28px 16px;display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between}}
.pie img{{width:48px;height:48px;border-radius:10px}}
.pie a{{color:#fff;font-weight:600}}
@media (max-width:600px){{.hoy{{display:none}}.destacada{{padding:20px}}}}
</style></head>
<body>
<div class="franja"></div>
<header>
  <div class="barra">
    <img src="img/logo-512.png" alt="">
    <a class="marca" href="./">Al Día <span>RD</span></a>
    <div class="hoy" id="hoy"></div>
  </div>
  <nav><button data-f="todas" aria-pressed="true">Todas</button>{botones_nav}</nav>
</header>
<main>{cuerpo}</main>
<footer><div class="pie">
  <div style="display:flex;gap:12px;align-items:center"><img src="img/logo-512.png" alt="">
    <div>Resúmenes propios hechos a partir de las noticias de cada medio.<br>Cada noticia enlaza a su fuente original.</div></div>
  <div>Síguenos en Instagram: <a href="https://instagram.com/{INSTAGRAM}" target="_blank" rel="noopener">@{INSTAGRAM}</a><br>
    También: <a href="https://divisasrd.com" target="_blank" rel="noopener">DivisasRD.com</a> ·
    <a href="https://kiloclarord.com" target="_blank" rel="noopener">KiloClaroRD.com</a></div>
</div></footer>
<script>
var hoy=new Date().toLocaleDateString('es-DO',{{weekday:'long',day:'numeric',month:'long',year:'numeric'}});
document.getElementById('hoy').textContent=hoy.charAt(0).toUpperCase()+hoy.slice(1);
function hace(iso){{var m=Math.round((Date.now()-new Date(iso))/60000);
 if(m<1)return'ahora';if(m<60)return'hace '+m+' min';var h=Math.round(m/60);
 if(h<24)return'hace '+h+(h==1?' hora':' horas');var d=Math.round(h/24);return'hace '+d+(d==1?' día':' días');}}
document.querySelectorAll('.hora').forEach(function(e){{e.textContent='· '+hace(e.dataset.fecha)}});
document.querySelectorAll('nav button').forEach(function(b){{b.onclick=function(){{
 document.querySelectorAll('nav button').forEach(function(x){{x.setAttribute('aria-pressed',x===b)}});
 document.querySelectorAll('.nota').forEach(function(n){{n.classList.toggle('oculta',b.dataset.f!=='todas'&&n.dataset.sec!==b.dataset.f)}});
 var c=document.querySelector('.consejo'); if(c)c.classList.toggle('oculta',b.dataset.f!=='todas');
}}}});
</script>
</body></html>"""
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)

# ================= Principal =================
def main():
    os.makedirs("docs/ig", exist_ok=True)
    guardadas = cargar(ARCHIVO)
    consejos = cargar(ARCHIVO_CONSEJOS)
    nuevas = buscar(guardadas)
    todas = (nuevas + guardadas)[:MAX_GUARDADAS]
    calcular_tendencia(todas)
    elegida = elegir_para_instagram(todas)
    consejo_del_dia(todas, consejos)
    consejos = consejos[-30:]
    limpiar_imagenes(todas, consejos)
    guardar(ARCHIVO, todas)
    guardar(ARCHIVO_CONSEJOS, consejos)
    generar_html(todas, consejos)
    print(f"{len(nuevas)} noticias nuevas, {len(todas)} en total")
    if elegida:
        print(f"Para Instagram (tendencia {elegida.get('tendencia', 1)}): {elegida['titulo']}")

if __name__ == "__main__":
    main()
