"""Publica UNA cosa por corrida en Instagram (@aldiardnews):
el consejo del día si está listo, si no la noticia que noticias.py escogió.
Necesita los secretos IG_TOKEN e IG_USER_ID en GitHub."""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

from noticias import (destino, extras, ARCHIVO, ARCHIVO_CONSEJOS, cargar, guardar,
                      SEC_USA, SEC_PRECIOS, SEC_JUEGOS, SEC_FAMOSOS, SEC_INTER)

SITIO = "https://aldiard.com"
API = "https://graph.instagram.com/v23.0"
TOKEN = os.environ.get("IG_TOKEN", "").strip()
USUARIO = os.environ.get("IG_USER_ID", "").strip() or "me"
MAX_INTENTOS = 3

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

def esperar_imagen(url, minutos=10):
    """GitHub Pages tarda un par de minutos en publicar la imagen nueva."""
    fin = time.time() + minutos * 60
    while time.time() < fin:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(20)
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
        item["ig_intentos"] = item.get("ig_intentos", 0) + 1
        if item["ig_intentos"] >= MAX_INTENTOS:
            item["ig"] = "error"
        print("Error Instagram:", item["titulo"], "->", err)
        return
    if item.get("historia") == "pendiente":  # está en tendencia (o es el consejo): también a historias
        try:
            publicar(item["historia_img"], clave + "h", "", historia=True)
            item["historia"] = "publicado"
            item["historia_fecha"] = datetime.now(timezone.utc).isoformat()
            print("Historia publicada:", item["titulo"])
        except Exception as err:
            item["historia"] = "error"
            print("Error historia:", item["titulo"], "->", err)

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
    consejo = next((c for c in consejos if c.get("ig") == "pendiente"), None)
    noticia = next((n for n in todas if n.get("ig") == "pendiente"), None)
    if consejo:
        intentar(consejo, consejo["ig_img"], consejo["fecha"], texto_consejo(consejo))
    elif noticia:
        intentar(noticia, noticia["ig_img"], noticia["id"], texto_noticia(noticia))
    else:
        print("Nada nuevo para Instagram en esta corrida.")
    guardar(ARCHIVO, todas)
    guardar(ARCHIVO_CONSEJOS, consejos)
    renovar_token()

if __name__ == "__main__":
    main()
