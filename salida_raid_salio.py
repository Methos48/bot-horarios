import os
import io
import json
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from PIL import Image
import config

logger = logging.getLogger("SalidaRaid")
ZONA_ARGENTINA = ZoneInfo(getattr(config,"TZ","America/Argentina/Buenos_Aires"))

FILTRO_PUBLICAR_RAIDS_SALIO = {
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

ESTADO_ANTERIOR={}
MEMORIA_DUPLICADOS=set()
MEMORIA_30_MIN={}
ULTIMO_RESET_DIA=None

def normalizar(nombre):
    return str(nombre or "").strip().lower().replace(" ","")

def filtro_ok(nombre,lista):
    if nombre in FILTRO_PUBLICAR_RAIDS_SALIO:
        return FILTRO_PUBLICAR_RAIDS_SALIO[nombre]=="si"
    if lista=="raid_60_plus":
        return FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_mas","no")=="si"
    return FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_menos","no")=="si"

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
    if clave and clave in MEMORIA_DUPLICADOS: return False
    ruta=plantilla(nombre,sufijo)
    if not ruta:
        logger.warning("No existe plantilla SALIO: %s%s",normalizar(nombre),sufijo)
        return False
    principal=await canal(bot,getattr(config,"ENVIAR_MENSAJE_CHANNEL_ID",None))
    if not principal: return False

    img=None; buf=None
    if hora is not None:
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
            if hora is not None:
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

async def FILTRO_PUBLICAR_RAIDS_SALIO(bot_instance,raid_data,tipo_lista="vivo_o_muerto"):
    if not isinstance(raid_data,dict): return
    nombre=normalizar(raid_data.get("nombre"))
    estado=str(raid_data.get("estado","")).strip().lower()
    if not nombre or not filtro_ok(nombre,tipo_lista): return
    anterior=ESTADO_ANTERIOR.get(nombre)
    ESTADO_ANTERIOR[nombre]=estado
    if anterior!="muerto" or estado!="vivo": return

    ahora=datetime.now(ZONA_ARGENTINA)
    clave=f"{nombre}|{ahora.date()}|nacimiento"
    if nombre in {"valakas","antharas"}:
        if await publicar(bot_instance,nombre,"4",ahora,clave):
            MEMORIA_30_MIN[nombre]=(asyncio.get_event_loop().time()+1800,ahora.date())
    elif nombre=="fafureon":
        await publicar(bot_instance,nombre,"4",None,clave)
    elif nombre in {"baium","zaken","core","orfen","queenant","frintezza","freya","zariche"}:
        await publicar(bot_instance,nombre,"2",None,clave)

def reset_memorias(ahora):
    global ULTIMO_RESET_DIA
    dia=ahora.strftime("%Y-%m-%d")
    if ahora.hour>=4 and ULTIMO_RESET_DIA!=dia:
        ESTADO_ANTERIOR.clear()
        MEMORIA_DUPLICADOS.clear()
        MEMORIA_30_MIN.clear()
        ULTIMO_RESET_DIA=dia
        logger.info("Memorias SALIO limpiadas a las 04:00 Argentina.")

async def servicio_publicar_raids_salio(bot_instance,ruta_json,json_lock):
    await bot_instance.wait_until_ready()
    logger.info("Servicio PUBLICAR_RAIDS_SALIO iniciado correctamente.")
    while not bot_instance.is_closed():
        try:
            ahora=datetime.now(ZONA_ARGENTINA)
            reset_memorias(ahora)

            # +30 min de Valakas/Antharas.
            ahora_mono=asyncio.get_event_loop().time()
            for nombre,(objetivo,fecha_nacimiento) in list(MEMORIA_30_MIN.items()):
                if ahora_mono>=objetivo:
                    clave=f"{nombre}|{fecha_nacimiento}|30min"
                    await publicar(bot_instance,nombre,"5",None,clave)
                    del MEMORIA_30_MIN[nombre]

            if os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json,encoding="utf-8") as f:
                        data=json.load(f)
                for item,lista in cargar_raids(data):
                    await FILTRO_PUBLICAR_RAIDS_SALIO(bot_instance,item,lista)

        except Exception as e:
            logger.exception("Error en PUBLICAR_RAIDS_SALIO: %s",e)
        await asyncio.sleep(30)
