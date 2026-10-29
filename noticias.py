"""Al Día RD: busca noticias, hace un resumen corto con Claude y genera la página en docs/."""
import feedparser, json, os, re, html, urllib.parse
from datetime import datetime, timezone

# Fuentes vía Google News RSS (funciona aunque el periódico no tenga RSS propio)
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
# EE.UU.: solo noticias sobre dominicanos
FUENTES_USA = [
    gnews("dominicanos Nueva York"),
    gnews("dominicanos New Jersey"),
    gnews("dominicanos Florida"),
    gnews("dominicanos Massachusetts"),
    gnews("dominicanos Pensilvania"),
    gnews("dominicanos Rhode Island"),
    gnews("comunidad dominicana Estados Unidos"),
]

ARCHIVO = "docs/noticias.json"
POR_FUENTE = 3       # noticias que mira de cada fuente por corrida
MAX_NUEVAS = 15      # máximo de noticias nuevas por corrida (controla el gasto de IA)
MAX_GUARDADAS = 300
MODELO = os.environ.get("MODELO_IA", "claude-haiku-5-5")

_cliente = None
def cliente():
    global _cliente
    if _cliente is None:
        import anthropic
        _cliente = anthropic.Anthropic()  # usa la variable ANTHROPIC_API_KEY
    return _cliente

def limpiar(texto):
    """Quita etiquetas HTML y espacios de más."""
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()

def titulo_sin_fuente(titulo, fuente):
    """Google News pone ' - Nombre del periódico' al final del título."""
    fin = " - " + fuente
    return titulo[: -len(fin)] if fuente and titulo.endswith(fin) else titulo

def resumir(titulo, texto):
    msg = cliente().messages.create(
        model=MODELO,
        max_tokens=300,
        messages=[{"role": "user", "content":
            "Escribe un resumen corto (2-3 oraciones) en español, con tus propias palabras, "
            "neutral y sin inventar datos, de esta noticia. Si solo tienes el título, "
            "resume lo que dice el título sin agregar detalles. No copies frases textuales. "
            "Responde solo con el resumen.\n\n"
            f"Título: {titulo}\nTexto: {texto}"}])
    return msg.content[0].text.strip()

def cargar():
    if os.path.exists(ARCHIVO):
        with open(ARCHIVO, encoding="utf-8") as f:
            return json.load(f)
    return []

def main():
    guardadas = cargar()
    vistos = {n["link"] for n in guardadas} | {n["titulo"] for n in guardadas}
    nuevas = []
    for seccion, fuentes in (("República Dominicana", FUENTES_RD),
                             ("Dominicanos en EE.UU.", FUENTES_USA)):
        for url in fuentes:
            for e in feedparser.parse(url).entries[:POR_FUENTE]:
                if len(nuevas) >= MAX_NUEVAS:
                    break
                fuente = e.get("source", {}).get("title", "Fuente")
                titulo = titulo_sin_fuente(limpiar(e.get("title", "")), fuente)
                link = e.get("link", "")
                if not titulo or not link or link in vistos or titulo in vistos:
                    continue
                try:
                    resumen = resumir(titulo, limpiar(e.get("summary", "")))
                except Exception as err:
                    print("Error IA:", err)
                    continue
                nuevas.append({"titulo": titulo, "resumen": resumen, "link": link,
                               "fuente": fuente, "seccion": seccion,
                               "fecha": datetime.now(timezone.utc).isoformat()})
                vistos.update((link, titulo))
    todas = (nuevas + guardadas)[:MAX_GUARDADAS]
    os.makedirs("docs", exist_ok=True)
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(todas, f, ensure_ascii=False, indent=1)
    generar_html(todas)
    print(f"{len(nuevas)} noticias nuevas, {len(todas)} en total")

def generar_html(todas):
    tarjetas = ""
    for n in todas[:100]:
        fecha = n["fecha"][:10]
        tarjetas += f"""
<article>
  <span class="sec">{html.escape(n['seccion'])}</span> <span class="fecha">{fecha}</span>
  <h2>{html.escape(n['titulo'])}</h2>
  <p>{html.escape(n['resumen'])}</p>
  <a href="{html.escape(n['link'])}" target="_blank" rel="noopener">Fuente: {html.escape(n['fuente'])} →</a>
</article>"""
    if not tarjetas:
        tarjetas = "<p class='vacio'>Pronto tendremos noticias aquí.</p>"
    pagina = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Al Día RD – Noticias de RD y dominicanos en EE.UU.</title>
<meta name="description" content="Resúmenes de noticias de República Dominicana y de los dominicanos en Estados Unidos, con enlace a la fuente original.">
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f4f4f4;color:#222}}
header{{background:#002d62;color:#fff;padding:16px;text-align:center;border-bottom:5px solid #ce1126}}
header h1{{margin:0 0 4px}}
main{{max-width:760px;margin:auto;padding:12px}}
article{{background:#fff;border-radius:10px;padding:14px;margin:12px 0;box-shadow:0 1px 3px #0002}}
.sec{{font-size:12px;color:#ce1126;font-weight:bold;text-transform:uppercase}}
.fecha{{font-size:12px;color:#888}}
h2{{font-size:18px;margin:6px 0}} a{{color:#002d62}}
.vacio{{text-align:center;color:#666;padding:40px 0}}
footer{{text-align:center;font-size:12px;color:#777;padding:20px}}
</style></head><body>
<header><h1>Al Día RD</h1><div>Noticias de República Dominicana y de los dominicanos en EE.UU.</div></header>
<main>{tarjetas}</main>
<footer>Resúmenes propios. Cada noticia enlaza a su fuente original.</footer>
</body></html>"""
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)

if __name__ == "__main__":
    main()
