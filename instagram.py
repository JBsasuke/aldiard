"""Publica en Instagram (@aldiardnews) varias cosas por corrida:
un solo consejo al día y hasta 5 noticias por hora, la más en tendencia primero.
Necesita los secretos IG_TOKEN e IG_USER_ID en GitHub."""
import json, os, re, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

from noticias import (destino, extras, ARCHIVO, ARCHIVO_CONSEJOS, cargar, guardar,
                      SEC_USA, SEC_PRECIOS, SEC_JUEGOS, SEC_FAMOSOS, SEC_INTER)

SITIO = "https://aldiard.com"
API = "https://graph.instagram.com/v23.0"
TOKEN = os.environ.get("IG_TOKEN", "").strip()
USUARIO = os.environ.get("IG_USER_ID", "").strip() or "me"
MAX_INTENTOS = 3
ESPERA_ENTRE = 75        # segundos entre una publicación y otra (para que Instagram no lo tome como spam)
TIEMPO_MAX = 20 * 60     # una corrida no pasa más de 20 minutos publicando

def es_limite(err):
    """Instagram dice que hay que esperar (límite de pedidos o de publicaciones del día)."""
    return re.search(r"request limit|2207051|2207042|\"code\": ?4[,}]", str(err), re.I) is not None

HORA_RD = timezone(timedelta(hours=-4))  # República Dominicana, sin cambio de horario

HASHTAGS = {
    SEC_USA: "#AlDíaRD #Dominicanos #DominicanosEnUSA #NoticiasRD",
    SEC_PRECIOS: "#AlDíaRD #PreciosRD #Combustibles #RepúblicaDominicana",
    SEC_JUEGOS: "#AlDíaRD #Videojuegos #Gaming #GTA6 #PlayStation",
    SEC_FAMOSOS: "#AlDíaRD #Farándula #Famosos #FarándulaRD #Celebridades",
    SEC_INTER: "#AlDíaRD #Internacionales #NoticiasDelMundo #Mundo",
}
HASHTAGS_RD = "#AlDíaRD #RepúblicaDominicana #Dominicanos #NoticiasRD"

import re
# Videojuegos: los hashtags van con la consola de la noticia (si es solo de Nintendo, solo Nintendo)
CONSOLAS = [
    (r"switch 2", "#NintendoSwitch2"), (r"nintendo|\bswitch\b", "#Nintendo"),
    (r"playstation|\bps5\b|\bps4\b", "#PlayStation"), (r"\bps5\b", "#PS5"),
    (r"xbox", "#Xbox"), (r"\bpc\b|steam", "#PCGaming"),
]
JUEGOS = [(r"\bgta\b|grand theft auto", "#GTA6"), (r"pok[eé]mon", "#Pokemon"), (r"zelda", "#Zelda"),
          (r"\bmario\b", "#Mario"), (r"call of duty", "#CallOfDuty"), (r"fortnite", "#Fortnite"),
          (r"minecraft", "#Minecraft"), (r"\bfc ?2\d\b|ea sports fc", "#EASportsFC")]
MULTI = r"multiplataforma|todas las (consolas|plataformas)|all platforms"

def hashtags_juegos(n):
    # se mira el titular, el gancho y los datos clave (no todo el texto, que a veces compara con otras consolas)
    t = " ".join([n["titulo"], n.get("gancho") or n["resumen"]] + (n.get("claves") or [])).lower()
    tags = ["#AlDíaRD", "#Videojuegos"]
    if re.search(MULTI, t):
        tags += ["#Nintendo", "#PlayStation", "#Xbox"]
    if re.search(r"pok[eé]mon|zelda|\bmario\b|kirby|metroid|donkey kong|animal crossing|splatoon", t):
        tags.append("#Nintendo")  # juegos que solo salen en Nintendo
    for patron, tag in CONSOLAS + JUEGOS:
        if re.search(patron, t) and tag not in tags:
            tags.append(tag)
    if len(tags) == 2:
        tags.append("#Gaming")
    return " ".join(tags)

def pedir(url, datos=None):
    cuerpo = urllib.parse.urlencode(datos).encode() if datos else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code}: {e.read().decode(errors='replace')[:400]}")

NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

def esperar_imagen(url, minutos=15):
    """Cloudflare Pages tarda unos minutos en publicar la imagen nueva.
    Se pide como un navegador (Cloudflare a veces bloquea a Python) y se anota qué responde."""
    fin, ultimo, vueltas = time.time() + minutos * 60, "", 0
    while time.time() < fin:
        vueltas += 1
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR, "Range": "bytes=0-1023"})
            with urllib.request.urlopen(pedido, timeout=20) as r:
                tipo = r.headers.get("Content-Type", "")
                if r.status in (200, 206) and tipo.startswith("image/"):
                    print(f"Imagen lista en la página (intento {vueltas})")
                    return True
                ultimo = f"respondió {r.status} pero no es imagen ({tipo or 'sin tipo'})"
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
        except Exception as e:
            ultimo = repr(e)[:150]
        time.sleep(30)
    print(f"La imagen no apareció en {minutos} minutos. Lo último que respondió aldiard.com: {ultimo}")
    return False

def texto_noticia(n):
    t = f"{n['titulo']}\n\n{n['resumen']}\n\n"
    dst = destino(n)
    if dst:
        t += f"👉 {dst['texto']}: {dst['sitio']}\n"
    for e in extras(n):
        t += f"👉 {e['texto']}: {e['sitio']}\n"
    fuentes = [f["nombre"] for f in (n.get("fuentes") or [{"nombre": n["fuente"]}])]
    t += f"📲 Léela completa en español e inglés en nuestra web: aldiard.com/n/{n['id']}\n"
    t += "(el enlace a aldiard.com está en la bio)\n"
    t += ("Fuentes: " if len(fuentes) > 1 else "Fuente: ") + ", ".join(fuentes) + "\n\n"
    etiquetas = hashtags_juegos(n) if n["seccion"] == SEC_JUEGOS else HASHTAGS.get(n["seccion"], HASHTAGS_RD)
    return (t + etiquetas)[:2200]

def texto_consejo(c):
    t = f"💡 Consejo del día: {c['titulo']}\n\n{c['texto']}\n\n👉 {c['boton']} en {c['sitio']}\n\n"
    t += "Síguenos en Instagram y X: @aldiardnews\n\n#AlDíaRD #ConsejoDelDía " + ("#AhorraLuz #KiloClaro" if c["tema"] == "kiloclaro" else "#DivisasRD #Dólar #Remesas")
    return t

def publicar(ig_img, clave, caption, historia=False):
    img = f"{SITIO}/{ig_img}?v={clave}"
    if not esperar_imagen(img):
        raise RuntimeError("la imagen no apareció en la página a tiempo")
    datos = {"image_url": img, "access_token": TOKEN}
    if historia:
        datos["media_type"] = "STORIES"  # las historias no llevan texto
    else:
        datos["caption"] = caption
    cid = pedir(f"{API}/{USUARIO}/media", datos)["id"]
    for _ in range(10):  # espera a que Instagram procese la imagen
        estado = pedir(f"{API}/{cid}?" + urllib.parse.urlencode(
            {"fields": "status_code", "access_token": TOKEN})).get("status_code")
        if estado == "FINISHED":
            break
        if estado == "ERROR":
            raise RuntimeError("Instagram no pudo procesar la imagen")
        time.sleep(5)
    return pedir(f"{API}/{USUARIO}/media_publish",
                 {"creation_id": cid, "access_token": TOKEN})["id"]

def intentar(item, ig_img, clave, caption):
    try:
        item["ig_id"] = publicar(ig_img, clave, caption)
        item["ig"] = "publicado"
        item["ig_fecha"] = datetime.now(timezone.utc).isoformat()
        print("Publicado:", item["titulo"])
    except Exception as err:
        if es_limite(err):  # no es culpa de la noticia: no cuenta como intento
            print("Límite de Instagram:", item["titulo"], "->", err)
            return "limite"
        item["ig_intentos"] = item.get("ig_intentos", 0) + 1
        if item["ig_intentos"] >= MAX_INTENTOS:
            item["ig"] = "error"
        print("Error Instagram:", item["titulo"], "->", err)
        return "error"
    if item.get("historia") == "pendiente":  # está en tendencia (o es el consejo): también a historias
        try:
            publicar(item["historia_img"], clave + "h", "", historia=True)
            item["historia"] = "publicado"
            item["historia_fecha"] = datetime.now(timezone.utc).isoformat()
            print("Historia publicada:", item["titulo"])
        except Exception as err:
            item["historia"] = "error"
            print("Error historia:", item["titulo"], "->", err)
    return "ok"

def dia_rd(fecha_iso):
    """Convierte una fecha guardada (ISO) al día en hora de RD. Si no se entiende, devuelve None."""
    try:
        f = datetime.fromisoformat(str(fecha_iso).replace("Z", "+00:00"))
        if f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        return f.astimezone(HORA_RD).date()
    except Exception:
        return None

def escoger_consejo(consejos):
    """Un solo consejo al día. Devuelve el consejo a publicar, o None si ya salió uno hoy."""
    hoy = datetime.now(HORA_RD).date()
    if any(c.get("ig") == "publicado" and dia_rd(c.get("ig_fecha")) == hoy for c in consejos):
        print("Ya salió el consejo de hoy; esta corrida es para noticias.")
        return None
    # los consejos pendientes de días anteriores se descartan para que no se acumulen
    for c in consejos:
        if c.get("ig") == "pendiente":
            dia = dia_rd(c.get("fecha"))
            if dia and dia < hoy:
                c["ig"] = "vencido"
                print("Consejo viejo descartado:", c.get("titulo"))
    return next((c for c in consejos if c.get("ig") == "pendiente"), None)

def renovar_token():
    """Alarga la vida del token (dura 60 días). Se intenta una vez al día."""
    if datetime.now(timezone.utc).hour != 12:
        return
    try:
        r = pedir("https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
            {"grant_type": "ig_refresh_token", "access_token": TOKEN}))
        print(f"Token renovado: vence en {int(r.get('expires_in', 0)) // 86400} días")
        if r.get("access_token") and r["access_token"] != TOKEN:
            print("AVISO: Instagram dio un token nuevo. Cámbialo en el secreto IG_TOKEN.")
    except Exception as err:
        print("No se pudo renovar el token:", err)

def main():
    print(f"IG_TOKEN: {'encontrado' if TOKEN else 'NO ENCONTRADO'} · "
          f"IG_USER_ID: {'encontrado' if os.environ.get('IG_USER_ID', '').strip() else 'NO ENCONTRADO (uso me)'}")
    if not TOKEN:
        sys.exit("ERROR: falta el secreto IG_TOKEN. Ponlo en Settings → Secrets and variables → "
                 "Actions → pestaña Secrets → New repository secret (nombre exacto: IG_TOKEN).")
    todas, consejos = cargar(ARCHIVO), cargar(ARCHIVO_CONSEJOS)
    consejo = escoger_consejo(consejos)
    cola = []
    if consejo:
        cola.append((consejo, consejo["ig_img"], consejo["fecha"], texto_consejo(consejo)))
    # todas las noticias que noticias.py dejó listas, la más en tendencia primero
    pendientes = sorted((n for n in todas if n.get("ig") == "pendiente"),
                        key=lambda n: n.get("tendencia", 1), reverse=True)
    cola += [(n, n["ig_img"], n["id"], texto_noticia(n)) for n in pendientes]
    if not cola:
        print("Nada nuevo para Instagram en esta corrida.")
    inicio = time.time()
    for i, (item, img, clave, texto) in enumerate(cola):
        if i:
            if time.time() - inicio > TIEMPO_MAX:
                print("Se acabó el tiempo de esta corrida: lo que falta compite en la próxima.")
                break
            print(f"Esperando {ESPERA_ENTRE} segundos antes de la próxima (para que Instagram no lo tome como spam)...")
            time.sleep(ESPERA_ENTRE)
        if intentar(item, img, clave, texto) == "limite":
            print("Instagram puso un límite por ahora: lo que falta sale en la próxima corrida.")
            break
        guardar(ARCHIVO, todas)  # se guarda después de cada una, por si algo se corta
        guardar(ARCHIVO_CONSEJOS, consejos)
    guardar(ARCHIVO, todas)
    guardar(ARCHIVO_CONSEJOS, consejos)
    renovar_token()

if __name__ == "__main__":
    main()
