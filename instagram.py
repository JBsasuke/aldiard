"""Publica en Instagram (@aldiardnews) las noticias que noticias.py dejó 'pendiente'.
Necesita los secretos IG_TOKEN e IG_USER_ID en GitHub."""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error

SITIO = "https://aldiard.com"
ARCHIVO = "docs/noticias.json"
API = "https://graph.instagram.com/v23.0"
TOKEN = os.environ.get("IG_TOKEN", "").strip()
USUARIO = os.environ.get("IG_USER_ID", "").strip() or "me"
MAX_INTENTOS = 3
from noticias import extras, SEC_USA, SEC_PRECIOS, SEC_JUEGOS

HASHTAGS = {
    SEC_USA: "#AlDíaRD #Dominicanos #DominicanosEnUSA #NoticiasRD",
    SEC_PRECIOS: "#AlDíaRD #PreciosRD #Combustibles #RepúblicaDominicana",
    SEC_JUEGOS: "#AlDíaRD #Videojuegos #Gaming #GTA6 #PlayStation",
}
HASHTAGS_RD = "#AlDíaRD #RepúblicaDominicana #Dominicanos #NoticiasRD"

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

def texto(n):
    t = f"{n['titulo']}\n\n{n['resumen']}\n\nFuente: {n['fuente']}\n"
    for e in extras(n):
        t += f"👉 {e['texto']}: {e['sitio']}\n"
    t += "Más noticias en aldiard.com (enlace en la bio)\n\n" + HASHTAGS.get(n["seccion"], HASHTAGS_RD)
    return t[:2200]

def publicar(n):
    img = f"{SITIO}/{n['ig_img']}?v={n['id']}"
    if not esperar_imagen(img):
        raise RuntimeError("la imagen no apareció en la página a tiempo")
    c = pedir(f"{API}/{USUARIO}/media",
              {"image_url": img, "caption": texto(n), "access_token": TOKEN})
    cid = c["id"]
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

def renovar_token():
    """Alarga la vida del token (dura 60 días). Si falla, no pasa nada."""
    try:
        r = pedir("https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
            {"grant_type": "ig_refresh_token", "access_token": TOKEN}))
        dias = int(r.get("expires_in", 0)) // 86400
        print(f"Token renovado: vence en {dias} días")
        if r.get("access_token") and r["access_token"] != TOKEN:
            print("AVISO: Instagram dio un token nuevo. Cámbialo en el secreto IG_TOKEN.")
    except Exception as err:
        print("No se pudo renovar el token (normal si tiene menos de 24 horas):", err)

def main():
    if not TOKEN:
        print("Falta el secreto IG_TOKEN; no se publica en Instagram.")
        return
    with open(ARCHIVO, encoding="utf-8") as f:
        todas = json.load(f)
    pendientes = [n for n in todas if n.get("ig") == "pendiente"]
    print(f"{len(pendientes)} pendientes para Instagram")
    for n in reversed(pendientes):  # la más vieja primero
        try:
            n["ig_id"] = publicar(n)
            n["ig"] = "publicado"
            print("Publicado:", n["titulo"])
        except Exception as err:
            n["ig_intentos"] = n.get("ig_intentos", 0) + 1
            if n["ig_intentos"] >= MAX_INTENTOS:
                n["ig"] = "error"
            print("Error Instagram:", n["titulo"], "->", err)
        time.sleep(10)
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(todas, f, ensure_ascii=False, indent=1)
    renovar_token()

if __name__ == "__main__":
    main()
