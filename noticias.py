"""Al Día RD: busca noticias, hace un resumen corto con Claude, genera la página en docs/
y prepara las imágenes que instagram.py publica después."""
import feedparser, json, os, re, html, hashlib, textwrap, urllib.parse
from datetime import datetime, timezone, timedelta

# ---------------- Configuración ----------------
SITIO = "https://aldiard.com"
INSTAGRAM = "aldiardnews"

def gnews(q):
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:1d")
            + "&hl=es-419&gl=US&ceid=US:es-419")

FUENTES_RD = [
    gnews("site:listindiario.com"),
    gnews("site:diariolibre.com"),
    gnews("site:elnuevodiario.com.do"),
    gnews("site:hoy.com.do"),
    gnews("site:eldia.com.do"),
    gnews("site:noticiassin.com"),
    gnews("site:cdn.com.do"),
]
FUENTES_USA = [  # EE.UU.: solo noticias sobre dominicanos
    gnews("dominicanos Nueva York"),
    gnews("dominicanos New Jersey"),
    gnews("dominicanos Florida"),
    gnews("dominicanos Massachusetts"),
    gnews("dominicanos Pensilvania"),
    gnews("dominicanos Rhode Island"),
    gnews("comunidad dominicana Estados Unidos"),
]

FUENTES_PRECIOS = [  # combustibles y precios de productos en RD
    gnews("precios combustibles República Dominicana"),
    gnews("precio gasolina gasoil GLP semana MICM"),
    gnews("precios canasta básica República Dominicana"),
    gnews("precios productos alimentos República Dominicana"),
]
FUENTES_JUEGOS = [  # videojuegos
    gnews("GTA 6"),
    gnews("videojuegos lanzamiento"),
    gnews("PlayStation 5 juegos"),
    gnews("Nintendo Switch 2"),
    gnews("Xbox juegos"),
]

SEC_RD, SEC_USA = "República Dominicana", "Dominicanos en EE.UU."
SEC_PRECIOS, SEC_JUEGOS = "Precios y combustibles", "Videojuegos"
# sección: (fuentes, cuántas noticias nuevas como máximo por corrida, clase, color)
SECCIONES = {
    SEC_RD:      (FUENTES_RD,      7, "rd", (206, 17, 38)),
    SEC_USA:     (FUENTES_USA,     6, "us", (0, 45, 98)),
    SEC_PRECIOS: (FUENTES_PRECIOS, 3, "pr", (180, 83, 9)),
    SEC_JUEGOS:  (FUENTES_JUEGOS,  4, "vj", (109, 40, 217)),
}
ORDEN_IG = [SEC_USA, SEC_JUEGOS, SEC_RD, SEC_PRECIOS]  # rotación en Instagram

# Enlaces a tus otras páginas según el tema de la noticia
ENLACES = [
    (r"d[oó]lar|divisa|tasa de cambio|tasa del|remesa|peso dominicano|\busd\b|\beuro\b",
     "Tasa del dólar hoy", "https://divisasrd.com", "divisasrd.com"),
    (r"combustible|gasolina|gasoil|\bglp\b|gas licuado",
     "Precios de combustibles", "https://divisasrd.com", "divisasrd.com"),
    (r"\bluz\b|apag[oó]n|apagones|el[eé]ctric|edenorte|edesur|edeeste|\bkwh\b|kilovat",
     "Calcula tu factura de luz", "https://kiloclarord.com", "kiloclarord.com"),
]

# Títulos que no son noticias de verdad (se saltan)
BASURA = r"^en vivo\b|\ben vivo -|gu[ií]a deportiva|resultados de (las )?loter|loter[ií]as? (de|del) hoy|^hor[oó]scopo|^portada"

ARCHIVO = "docs/noticias.json"
POR_FUENTE = 3        # noticias que mira de cada fuente por corrida
MAX_GUARDADAS = 300
IG_POR_CORRIDA = 4    # cuántas noticias se suben a Instagram cada 3 horas (32 al día)
MODELO = os.environ.get("MODELO_IA", "claude-haiku-5-5")

AZUL, ROJO, BLANCO = (0, 45, 98), (206, 17, 38), (255, 255, 255)
FUENTE_NEGRA = "fuentes/Inter-Black.otf"
FUENTE_FUERTE = "fuentes/Inter-ExtraBold.otf"
FUENTE_MEDIA = "fuentes/Inter-SemiBold.otf"

# ---------------- Noticias ----------------
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

def resumir(titulo, texto):
    msg = cliente().messages.create(
        model=MODELO,
        max_tokens=300,
        messages=[{"role": "user", "content":
            "Escribe un resumen corto (2-3 oraciones) en español, con tus propias palabras, "
            "neutral y sin inventar datos, de esta noticia. Si solo tienes el título, "
            "escribe una o dos oraciones con lo que dice el título, sin agregar detalles. "
            "Nunca menciones que falta información, que solo tienes el título o 'según el título'. "
            "No copies frases textuales. Responde solo con el resumen.\n\n"
            f"Título: {titulo}\nTexto: {texto}"}])
    return msg.content[0].text.strip()

def cargar():
    if os.path.exists(ARCHIVO):
        with open(ARCHIVO, encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar(todas):
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(todas, f, ensure_ascii=False, indent=1)

def extras(n):
    """Enlaces a divisasrd.com / kiloclarord.com si la noticia habla de eso."""
    texto = (n.get("titulo", "") + " " + n.get("resumen", "")).lower()
    return [{"texto": t, "url": u, "sitio": s} for patron, t, u, s in ENLACES
            if re.search(patron, texto)]

def clase(seccion):
    return SECCIONES.get(seccion, (None, 0, "rd", ROJO))[2]

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
                    continue  # en vivo, guías, loterías y títulos sin noticia
                try:
                    resumen = resumir(titulo, limpiar(e.get("summary", "")))
                except Exception as err:
                    print("Error IA:", err)
                    continue
                nuevas.append({"id": hashlib.md5(link.encode()).hexdigest()[:10],
                               "titulo": titulo, "resumen": resumen, "link": link,
                               "fuente": fuente, "seccion": seccion,
                               "fecha": datetime.now(timezone.utc).isoformat()})
                vistos.update((link, titulo))
                de_esta += 1
    return nuevas

# ---------------- Imágenes para Instagram ----------------
def _envolver(d, texto, fuente, ancho):
    """Parte el texto en líneas que quepan en 'ancho' píxeles."""
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

def imagen_instagram(n, ruta):
    """Tarjeta 1080x1350 (formato vertical de Instagram) con el titular."""
    from PIL import Image, ImageDraw, ImageFont
    from logo import marca
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), BLANCO)
    d = ImageDraw.Draw(img)
    # franja superior azul con logo y sección
    d.rectangle((0, 0, W, 230), fill=AZUL)
    lg = marca(150, fondo=False)
    img.paste(lg, (50, 40), lg)
    f_sec = ImageFont.truetype(FUENTE_FUERTE, 34)
    sec = n["seccion"].upper()
    sw = d.textlength(sec, font=f_sec)
    color = SECCIONES.get(n["seccion"], (None, 0, "rd", ROJO))[3]
    if color == AZUL:
        color = ROJO  # sobre la franja azul, la etiqueta azul no se vería
    d.rounded_rectangle((W - 60 - sw - 48, 88, W - 60, 146), radius=29, fill=color)
    d.text((W - 60 - sw - 24, 98), sec, font=f_sec, fill=BLANCO)
    d.rectangle((0, 230, W, 242), fill=ROJO)
    # titular: busca el tamaño más grande que quepa
    margen, top, fondo = 70, 300, 1120
    for tam in range(104, 40, -4):
        f_tit = ImageFont.truetype(FUENTE_NEGRA, tam)
        lineas = _envolver(d, n["titulo"], f_tit, W - 2 * margen)
        alto_linea = int(tam * 1.18)
        if len(lineas) * alto_linea + 60 <= fondo - top:
            break
    y = top + (fondo - top - (len(lineas) * alto_linea + 60)) // 2  # centrado
    for ln in lineas:
        d.text((margen, y), ln, font=f_tit, fill=(20, 24, 33))
        y += alto_linea
    # barrita roja bajo el titular
    d.rectangle((margen, y + 24, margen + 120, y + 36), fill=ROJO)
    # pie: fuente y sitio (o tu otra página si la noticia es del dólar o de la luz)
    f_pie = ImageFont.truetype(FUENTE_MEDIA, 34)
    d.line((margen, 1180, W - margen, 1180), fill=(220, 224, 232), width=3)
    d.text((margen, 1215), "Fuente: " + n["fuente"], font=f_pie, fill=(90, 98, 112))
    f_web = ImageFont.truetype(FUENTE_FUERTE, 34)
    ex = extras(n)
    web = ex[0]["sitio"] if ex else "aldiard.com"
    d.text((W - margen - d.textlength(web, font=f_web), 1215), web, font=f_web, fill=AZUL)
    img.save(ruta, "JPEG", quality=88)

def preparar_instagram(nuevas, todas):
    """Escoge hasta IG_POR_CORRIDA noticias nuevas (una de cada sección) y les hace la imagen."""
    os.makedirs("docs/ig", exist_ok=True)
    grupos = [[n for n in nuevas if n["seccion"] == s] for s in ORDEN_IG]
    escogidas = []
    while any(grupos) and len(escogidas) < IG_POR_CORRIDA:
        for grupo in grupos:
            if grupo and len(escogidas) < IG_POR_CORRIDA:
                escogidas.append(grupo.pop(0))
    for n in escogidas:
        ruta = f"docs/ig/{n['id']}.jpg"
        try:
            imagen_instagram(n, ruta)
            n["ig"], n["ig_img"] = "pendiente", f"ig/{n['id']}.jpg"
        except Exception as err:
            print("Error imagen:", err)
    # borra imágenes viejas que ya no hacen falta (Instagram guarda su copia)
    en_uso = {n.get("ig_img") for n in todas if n.get("ig") == "pendiente"}
    limite = datetime.now(timezone.utc) - timedelta(days=2)
    fechas = {n.get("ig_img"): n["fecha"] for n in todas if n.get("ig_img")}
    for archivo in os.listdir("docs/ig"):
        rel = "ig/" + archivo
        if rel in en_uso:
            continue
        f = fechas.get(rel)
        if f is None or datetime.fromisoformat(f) < limite:
            os.remove(os.path.join("docs/ig", archivo))

# ---------------- Página web ----------------
def generar_html(todas):
    def tarjeta(n, grande=False):
        c = clase(n["seccion"])
        ex = "".join(f'<a class="extra" href="{e["url"]}" target="_blank" rel="noopener">'
                     f'{html.escape(e["texto"])} en {e["sitio"]} →</a>' for e in extras(n))
        return f"""
<article class="nota {c}{' destacada' if grande else ''}" data-sec="{c}">
  <div class="meta"><span class="chip">{html.escape(n['seccion'])}</span>
    <span class="hora" data-fecha="{n['fecha']}"></span></div>
  <h2><a href="{html.escape(n['link'])}" target="_blank" rel="noopener">{html.escape(n['titulo'])}</a></h2>
  <p>{html.escape(n['resumen'])}</p>
  {ex}
  <a class="fuente" href="{html.escape(n['link'])}" target="_blank" rel="noopener">Leer en {html.escape(n['fuente'])} <span aria-hidden="true">→</span></a>
</article>"""
    lista = todas[:100]
    if lista:
        cuerpo = tarjeta(lista[0], True) + '<div class="rejilla">' + "".join(tarjeta(n) for n in lista[1:]) + "</div>"
    else:
        cuerpo = "<p class='vacio'>Pronto tendremos noticias aquí.</p>"
    pagina = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Al Día RD · Noticias de RD y de los dominicanos en EE.UU.</title>
<meta name="description" content="Resúmenes de noticias de República Dominicana y de los dominicanos en Estados Unidos, con enlace a la fuente original.">
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
:root{{--azul:#002d62;--rojo:#ce1126;--ambar:#b45309;--morado:#6d28d9;--tinta:#141821;--gris:#5a6270;--linea:#e3e6ec;--fondo:#f5f6f8;--blanco:#fff}}
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
nav{{max-width:1100px;margin:auto;padding:0 16px 10px;display:flex;gap:8px;overflow-x:auto}}
nav button{{font:600 14px Inter,system-ui,sans-serif;border:1px solid var(--linea);background:var(--blanco);color:var(--tinta);padding:8px 14px;border-radius:999px;cursor:pointer;white-space:nowrap}}
nav button[aria-pressed=true]{{background:var(--azul);border-color:var(--azul);color:#fff}}
main{{max-width:1100px;margin:auto;padding:20px 16px 40px}}
.nota{{background:var(--blanco);border:1px solid var(--linea);border-radius:14px;padding:18px 20px;display:flex;flex-direction:column;gap:8px;border-top:4px solid var(--rojo)}}
.nota.us{{border-top-color:var(--azul)}}
.nota.pr{{border-top-color:var(--ambar)}} .pr .chip{{color:var(--ambar)}}
.nota.vj{{border-top-color:var(--morado)}} .vj .chip{{color:var(--morado)}}
.extra{{align-self:flex-start;font-size:13.5px;font-weight:600;text-decoration:none;color:#0f5132;background:#e8f5ee;border:1px solid #cde9d9;padding:6px 10px;border-radius:8px}}
.extra:hover{{text-decoration:underline}}
.meta{{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--gris)}}
.chip{{font-weight:800;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--rojo)}}
.us .chip{{color:var(--azul)}}
.nota h2{{margin:0;font-size:19px;line-height:1.3;font-weight:800;letter-spacing:-.01em}}
.nota h2 a{{text-decoration:none}} .nota h2 a:hover{{text-decoration:underline}}
.nota p{{margin:0;color:#353b47;line-height:1.55;font-size:15.5px}}
.fuente{{margin-top:auto;padding-top:6px;font-weight:600;font-size:14px;color:var(--azul);text-decoration:none}}
.fuente:hover{{text-decoration:underline}}
.destacada{{padding:26px 28px;margin-bottom:18px}}
.destacada h2{{font-size:clamp(24px,3.4vw,34px);font-weight:900;line-height:1.15}}
.destacada p{{font-size:17px;max-width:760px}}
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
  <nav>
    <button data-f="todas" aria-pressed="true">Todas</button>
    <button data-f="rd" aria-pressed="false">República Dominicana</button>
    <button data-f="us" aria-pressed="false">Dominicanos en EE.UU.</button>
    <button data-f="pr" aria-pressed="false">Precios y combustibles</button>
    <button data-f="vj" aria-pressed="false">Videojuegos</button>
  </nav>
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
}}}});
</script>
</body></html>"""
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)

def main():
    guardadas = cargar()
    nuevas = buscar(guardadas)
    todas = (nuevas + guardadas)[:MAX_GUARDADAS]
    os.makedirs("docs", exist_ok=True)
    preparar_instagram(nuevas, todas)
    guardar(todas)
    generar_html(todas)
    print(f"{len(nuevas)} noticias nuevas, {len(todas)} en total")

if __name__ == "__main__":
    main()
