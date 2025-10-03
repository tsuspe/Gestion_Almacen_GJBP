#!/usr/bin/env python3
"""
limpia_historial_salidas.py

- Normaliza el número de albarán: quita decimales tipo "1252488.0" -> "1252488"
- Arregla cliente en salidas: si es "EXCEL" o vacío, intenta asignarlo por el modelo
  a partir de prevision.json["info_modelos"][modelo]["cliente"].
- Valida (opcional) el cliente contra clientes.json.
- Hace copia de seguridad automática antes de escribir.
- Modo --dry-run para ver qué haría sin tocar archivos.

Uso:
  python limpia_historial_salidas.py \
    --datos datos_almacen.json \
    --prevision prevision.json \
    --clientes clientes.json \
    --apply        # para aplicar cambios (sin esto, va en dry-run)

Recomendación: ejecuta primero SIN --apply para revisar el informe.
"""
import argparse
import json
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Set, Union

Json = Dict[str, Any]

def load_json(path: str) -> Json:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data: Json) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def backup_file(path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base, ext = os.path.splitext(path)
    bak = f"{base}.backup-{ts}{ext or '.json'}"
    shutil.copy2(path, bak)
    return bak

def to_str_no_decimal(v: Union[str, int, float]) -> str:
    """
    Convierte el albarán a string:
    - 1252488.0 -> "1252488"
    - "1252488.0" -> "1252488"
    - 1252488 -> "1252488"
    - "00123" -> "00123" (respeta ceros a la izquierda si ya venía como str sin .0)
    """
    if isinstance(v, (int,)):
        return str(v)
    s = str(v).strip()
    # si es float en str (termina en .0) => cast a float -> int -> str
    # ojo con strings tipo "00123.0": al pasar a int perderá ceros a izq. Si quieres conservarlos,
    # tendríamos que decidir una longitud fija. Por defecto: preferimos valor numérico limpio.
    if s.endswith(".0"):
        try:
            as_int = int(float(s))
            return str(as_int)
        except ValueError:
            return s[:-2]  # fallback: quitar los dos últimos caracteres ".0"
    # también si realmente es float
    try:
        if isinstance(v, float):
            return str(int(v))
    except Exception:
        pass
    return s

def normalize_cliente(nombre: Optional[str]) -> str:
    if not nombre:
        return ""
    # Limpio espacios y normalizo duplicados típicos
    nombre = nombre.strip()
    if nombre.upper() == "EXCEL":
        return "EXCEL"  # lo dejamos como marcador para sobreescribir luego
    return nombre

def infer_cliente_from_modelo(modelo: str, info_modelos: Json) -> Optional[str]:
    if not modelo:
        return None
    info = info_modelos.get(modelo, {})
    cliente = info.get("cliente")
    if isinstance(cliente, str) and cliente.strip():
        return cliente.strip()
    return None

def closest_match(nombre: str, valid_set: Set[str]) -> Optional[str]:
    """
    Si quieres, aquí podrías implementar una leve "fuzzy match".
    De momento, hacemos una coincidencia exacta por ahora.
    """
    if nombre in valid_set:
        return nombre
    return None

def process_salidas(
    datos: Json,
    info_modelos: Json,
    clientes_validos: Set[str],
    dry_run: bool = True
) -> Dict[str, int]:
    counters = {
        "salidas_total": 0,
        "albaran_normalizados": 0,
        "clientes_arreglados": 0,
        "clientes_no_encontrados": 0,
        "lineas_nan_eliminadas": 0
    }

    salidas: List[Json] = datos.get("historial_salidas", [])
    if not isinstance(salidas, list):
        return counters

    nuevas_salidas = []
    for salida in salidas:
        counters["salidas_total"] += 1

        modelo = str(salida.get("modelo", "")).strip().upper()
        fecha = str(salida.get("fecha", "")).strip()

        # --- 1) FILTRAR NAN ---
        if modelo == "NAN" or fecha.upper() == "NAT":
            counters["lineas_nan_eliminadas"] += 1
            if not dry_run:
                continue  # saltamos esta línea, no se añade a nuevas_salidas
            else:
                # en dry-run, mantenemos la línea pero contamos
                nuevas_salidas.append(salida)
            continue

        # --- 2) NORMALIZAR ALBARÁN ---
        if "albaran" in salida:
            original = salida["albaran"]
            nuevo = to_str_no_decimal(original)
            if nuevo != str(original).strip():
                counters["albaran_normalizados"] += 1
                if not dry_run:
                    salida["albaran"] = nuevo

        # --- 3) NORMALIZAR CLIENTE ---
        cliente_original = normalize_cliente(salida.get("cliente"))
        if cliente_original in ("EXCEL", ""):
            cliente_inferido = infer_cliente_from_modelo(modelo, info_modelos)
            if cliente_inferido:
                cliente_final = closest_match(cliente_inferido, clientes_validos) or cliente_inferido
                if not dry_run:
                    salida["cliente"] = cliente_final
                counters["clientes_arreglados"] += 1
            else:
                counters["clientes_no_encontrados"] += 1
                if not dry_run:
                    salida["cliente"] = ""
        else:
            cliente_match = closest_match(cliente_original, clientes_validos)
            if not dry_run and cliente_match and cliente_match != salida.get("cliente"):
                salida["cliente"] = cliente_match

        nuevas_salidas.append(salida)

    # Sustituimos el listado por el depurado
    if not dry_run:
        datos["historial_salidas"] = nuevas_salidas

    return counters


def main():
    ap = argparse.ArgumentParser(description="Limpia historial de salidas en datos_almacen.json")
    ap.add_argument("--datos", required=True, help="Ruta a datos_almacen.json")
    ap.add_argument("--prevision", required=True, help="Ruta a prevision.json (para info_modelos)")
    ap.add_argument("--clientes", required=True, help="Ruta a clientes.json (lista/estructura de clientes)")
    ap.add_argument("--apply", action="store_true", help="Aplica cambios (por defecto: dry-run)")
    args = ap.parse_args()

    datos_path = args.datos
    prevision_path = args.prevision
    clientes_path = args.clientes
    dry_run = not args.apply

    # Carga archivos
    datos = load_json(datos_path)
    prev = load_json(prevision_path)
    cli = load_json(clientes_path)

    # info_modelos para inferir cliente por modelo
    info_modelos = prev.get("info_modelos", {})

    # set de clientes válidos (ajusta según tu estructura real de clientes.json)
    # Opciones comunes:
    # - clientes.json = {"clientes": [{"nombre": "AIR EUROPA..."}, ...]}
    # - clientes.json = ["AIR EUROPA...", "GLOBALIA...", ...]
    clientes_validos: Set[str] = set()
    if isinstance(cli, dict) and "clientes" in cli and isinstance(cli["clientes"], list):
        for c in cli["clientes"]:
            if isinstance(c, dict):
                nombre = c.get("nombre")
                if isinstance(nombre, str) and nombre.strip():
                    clientes_validos.add(nombre.strip())
            elif isinstance(c, str):
                clientes_validos.add(c.strip())
    elif isinstance(cli, list):
        for c in cli:
            if isinstance(c, str):
                clientes_validos.add(c.strip())
            elif isinstance(c, dict) and "nombre" in c:
                nombre = c.get("nombre")
                if isinstance(nombre, str) and nombre.strip():
                    clientes_validos.add(nombre.strip())

    # Procesa
    counters = process_salidas(datos, info_modelos, clientes_validos, dry_run=dry_run)

    # Informe
    print("=== LIMPIEZA HISTORIAL SALIDAS ===")
    print(f"Archivo datos         : {datos_path}")
    print(f"Archivo prevision     : {prevision_path}")
    print(f"Archivo clientes      : {clientes_path}")
    print(f"Modo                  : {'APPLY (escritura)' if not dry_run else 'DRY-RUN (no escribe)'}")
    print("-----------------------------------")
    print(f"Salidas totales       : {counters['salidas_total']}")
    print(f"Albaranes normalizados: {counters['albaran_normalizados']}")
    print(f"Clientes arreglados   : {counters['clientes_arreglados']}")
    print(f"Clientes sin inferir  : {counters['clientes_no_encontrados']}")

    # Guardado con backup
    if not dry_run:
        bak = backup_file(datos_path)
        save_json(datos_path, datos)
        print("-----------------------------------")
        print(f"Backup creado en      : {bak}")
        print(f"Cambios guardados en  : {datos_path}")
    else:
        print("-----------------------------------")
        print("No se han escrito cambios (dry-run). Añade --apply para aplicar.")

if __name__ == "__main__":
    main()
