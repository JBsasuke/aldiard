"""Genera el logo de Al Día RD (se corre una sola vez: python logo.py)."""
from PIL import Image, ImageDraw, ImageFont

AZUL, ROJO, BLANCO = (0, 45, 98), (206, 17, 38), (255, 255, 255)
F_BLACK = "fuentes/Inter-Black.otf"

def marca(tam, fondo=True, redondo=False):
    """Logo cuadrado: 'AL DÍA' en blanco sobre azul y 'RD' en un bloque rojo."""
    s = tam * 4  # se dibuja grande y se reduce para que quede suave
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if fondo:
        if redondo:
            d.ellipse((0, 0, s, s), fill=AZUL)
        else:
            d.rounded_rectangle((0, 0, s, s), radius=int(s * 0.18), fill=AZUL)
    # "AL DÍA"
    f1 = ImageFont.truetype(F_BLACK, int(s * 0.215))
    t1 = "AL DÍA"
    w1 = d.textlength(t1, font=f1)
    y1 = int(s * 0.22)
    d.text(((s - w1) / 2, y1), t1, font=f1, fill=BLANCO)
    # bloque rojo con "RD"
    bw, bh = int(s * 0.50), int(s * 0.30)
    bx, by = (s - bw) // 2, int(s * 0.53)
    d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=int(s * 0.05), fill=ROJO)
    f2 = ImageFont.truetype(F_BLACK, int(s * 0.23))
    t2 = "RD"
    l, t, r, b = d.textbbox((0, 0), t2, font=f2)
    d.text((bx + (bw - (r - l)) / 2 - l, by + (bh - (b - t)) / 2 - t), t2, font=f2, fill=BLANCO)
    # rayita blanca entre las dos partes (guiño a la cruz de la bandera)
    ly = int(s * 0.475)
    d.rounded_rectangle((int(s * 0.34), ly, int(s * 0.66), ly + int(s * 0.016)),
                        radius=int(s * 0.008), fill=BLANCO)
    return img.resize((tam, tam), Image.LANCZOS)

if __name__ == "__main__":
    marca(1080).save("docs/img/logo.png")                       # logo general
    perfil = Image.new("RGB", (1080, 1080), AZUL)                 # foto de perfil de Instagram
    perfil.paste(marca(1080, fondo=False), (0, 0), marca(1080, fondo=False))
    perfil.save("docs/img/perfil-instagram.png")
    marca(180).save("docs/img/apple-touch-icon.png")
    marca(64).save("docs/img/favicon.png")
    marca(512).save("docs/img/logo-512.png")
    print("Logo listo en docs/img/")
