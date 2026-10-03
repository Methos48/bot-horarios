import os
import io
import json
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from PIL import Image
import config

logger = logging.getLogger("SalidaRaid")
ZONA_ARGENTINA = ZoneInfo(getattr(config,"TZ","America/Argentina/Buenos_Aires"))

CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO = {
    "valakas":"si","antharas":"si","fafureon":"si",
    "baium":"si","zaken":"si","core":"si","orfen":"si","queenant":"si",
    "frintezza":"si","freya":"si","zariche":"si",
    "decarbia":"si","hekaton":"si","queenshyeed":"si","golkonda":"si",
    "galaxia":"si","barakiel":"si","balrog":"no","electrical":"no",
    "otros_60_mas":"si","otros_60_menos":"no",
}

CANAL_DUPLICADO_PRUEBA = 1549577944999927999
RAIDS_DUPLICADOS = {"baium","zaken","core","orfen","queenant","frintezza","freya","zariche","valakas","antharas","fafureon"}
NUMEROS={str(i):getattr(config,f"NUMERO_{i}",None) for i in range(10)}
NUMEROS[":"]=getattr(config,"NUMERO_DOS_PUNTOS",None)

MEMORIA_DUPLICADOS=set()
ULTIMO_RESET_DIA=None

def normalizar(nombre):
    return str(nombre or "").strip().lower().replace(" ","")

def filtro_ok(nombre,lista):
    if nombre in CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO:
        return CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO[nombre]=="si"
    if lista=="raid_60_plus":
        return CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_mas","no")=="si"
    return CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_menos","no")=="si"

def cargar_raids(data):
    for lista in ("raid_60_plus","raid_60_menos","vivo_o_muerto"):
        valores=data.get(lista,[])
        if isinstance(valores,list):
            for item in valores:
                if isinstance(item,dict):
                    yield item,lista

def catalogo():
    base=os.path.join("imagen","raid","raid","antes")
    salida={}
    if not os.path.exists(base):
        return salida
    for root,_,files in os.walk(base):
        for f in files:
            if f.lower().endswith((".png",".webp",".jpg",".jpeg")):
                salida[f.lower()]=os.path.join(root,f)
    return salida

def plantilla(nombre,sufijo):
    c=catalogo()
    base=f"{normalizar(nombre)}{sufijo}"
    for ext in (".png",".webp",".jpg",".jpeg"):
        if base+ext in c:
            return c[base+ext]
    return None

def estampar(img,hora):
    cargados=[]; ancho_total=0; espacio=4; escala=.15
    for c in hora:
        p=NUMEROS.get(c)
        if p and os.path.exists(p):
            d=Image.open(p).convert("RGBA")
            w=int(d.width*escala); h=int(d.height*escala)
            d=d.resize((w,h),Image.Resampling.LANCZOS)
            cargados.append(d); ancho_total+=w
        else:
            cargados.append(None); ancho_total+=20
    if len(cargados)>1: ancho_total+=espacio*(len(cargados)-1)
    x=(img.width-ancho_total)//2; y=int(img.height*.83)
    for d in cargados:
        if d:
            img.paste(d,(x,y),d); x+=d.width+espacio
        else: x+=20+espacio

async def canal(bot,id_):
    if not id_: return None
    c=bot.get_channel(int(id_))
    if c is None:
        try: c=await bot.fetch_channel(int(id_))
        except Exception as e:
            logger.error("No se pudo obtener canal %s: %s",id_,e)
    return c

async def publicar(bot,nombre,sufijo,hora=None,clave=None):
    nombre_normalizado = normalizar(nombre)
    # LA HORA SOLO SE PERMITE PARA VALAKAS 4 Y ANTHARAS 4.
    poner_hora = hora is not None and nombre_normalizado in {"valakas", "antharas"} and str(sufijo) == "4"
    if clave and clave in MEMORIA_DUPLICADOS: return False
    ruta=plantilla(nombre,sufijo)
    if not ruta:
        logger.warning("No existe plantilla SALIO: %s%s",normalizar(nombre),sufijo)
        return False
    principal=await canal(bot,getattr(config,"ENVIAR_MENSAJE_CHANNEL_ID",None))
    if not principal: return False

    img=None; buf=None
    if poner_hora:
        img=Image.open(ruta).convert("RGBA")
        estampar(img,hora.strftime("%H:%M"))
        buf=io.BytesIO(); img.convert("RGB").save(buf,"PNG"); buf.seek(0)
        await principal.send(file=discord.File(buf,filename=f"{normalizar(nombre)}{sufijo}.png"))
    else:
        with open(ruta,"rb") as f:
            await principal.send(file=discord.File(f,filename=f"{normalizar(nombre)}{sufijo}.png"))

    if normalizar(nombre) in RAIDS_DUPLICADOS:
        prueba=await canal(bot,CANAL_DUPLICADO_PRUEBA)
        if prueba:
            if poner_hora:
                buf2=io.BytesIO(); img.convert("RGB").save(buf2,"PNG"); buf2.seek(0)
                await prueba.send(file=discord.File(buf2,filename=f"{normalizar(nombre)}{sufijo}.png"))
                buf2.close()
            else:
                with open(ruta,"rb") as f:
                    await prueba.send(file=discord.File(f,filename=f"{normalizar(nombre)}{sufijo}.png"))
    if buf: buf.close()
    if clave: MEMORIA_DUPLICADOS.add(clave)
    logger.info("[SALIO] publicado %s%s",normalizar(nombre),sufijo)
    return True

def obtener_datetime(item):
    dt=item.get("datetime")
    if isinstance(dt,datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=ZONA_ARGENTINA)
    iso=str(item.get("datetime_iso","")).strip()
    if iso:
        try:
            dt=datetime.fromisoformat(iso)
            return dt if dt.tzinfo else dt.replace(tzinfo=ZONA_ARGENTINA)
        except Exception: pass
    tiempo=str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
    if not tiempo or tiempo.upper() in {"VIVO","ALIVE","-","NONE"}: return None
    for fmt in ("%d/%m/%Y %H:%M","%d-%m-%Y %H:%M"):
        try: return datetime.strptime(tiempo,fmt).replace(tzinfo=ZONA_ARGENTINA)
        except ValueError: pass
    if len(tiempo)==5 and tiempo[2]==":":
        try:
            h,m=map(int,tiempo.split(":")); ahora=datetime.now(ZONA_ARGENTINA)
            return ahora.replace(hour=h,minute=m,second=0,microsecond=0)
        except Exception: pass
    return None

async def procesar_por_hora(bot_instance,item,lista,ahora):
    if not isinstance(item,dict): return
    nombre=normalizar(item.get("nombre"))
    if not nombre or not filtro_ok(nombre,lista): return
    programado=obtener_datetime(item)
    if not programado or programado.date()!=ahora.date(): return
    diferencia=(ahora-programado).total_seconds()
    if diferencia<0 or diferencia>300: return
    fecha=programado.strftime("%Y-%m-%d")
    clave=f"{nombre}|{fecha}|salio"
    if nombre in {"valakas","antharas","fafureon"}:
        sufijo="4"
    else:
        sufijo="2"

    # Solo Valakas 4 y Antharas 4 llevan la hora exacta.
    hora_publicacion = programado if nombre in {"valakas", "antharas"} and sufijo == "4" else None

    if await publicar(bot_instance,nombre,sufijo,hora_publicacion,clave):
        logger.info("[SALIO] %s detectado por hora %s",nombre,programado.strftime("%H:%M"))

def reset_memorias(ahora):
    global ULTIMO_RESET_DIA
    dia=ahora.strftime("%Y-%m-%d")
    if ahora.hour>=4 and ULTIMO_RESET_DIA!=dia:
        MEMORIA_DUPLICADOS.clear()
        ULTIMO_RESET_DIA=dia
        logger.info("Memorias SALIO limpiadas a las 04:00 Argentina.")

async def servicio_publicar_raids_salio(bot_instance,ruta_json,json_lock):
    await bot_instance.wait_until_ready()
    logger.info("Servicio PUBLICAR_RAIDS_SALIO iniciado correctamente.")
    while not bot_instance.is_closed():
        try:
            ahora=datetime.now(ZONA_ARGENTINA); reset_memorias(ahora)
            if os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json,encoding="utf-8") as f: data=json.load(f)
                for item,lista in cargar_raids(data):
                    await procesar_por_hora(bot_instance,item,lista,ahora)
        except Exception as e:
            logger.exception("Error en PUBLICAR_RAIDS_SALIO: %s",e)
        await asyncio.sleep(30)

