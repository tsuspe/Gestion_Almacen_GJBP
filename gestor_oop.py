"""Gestor de stock y previsión con orientación a objetos.

Este módulo unifica las funcionalidades de los antiguos
gestor_almacen_v_2.py y gestor_prevision_v_2.py en una sola
aplicación modular.  Se utilizan clases para encapsular la
lógica del inventario, la previsión, los talleres y los clientes,
facilitando así su mantenimiento y ampliación.

Actualmente las rutas de los ficheros JSON se mantienen en
los nombres por defecto (datos_almacen.json y prevision.json),
pero podrían inyectarse desde el exterior si se integra en
una aplicación mayor.  La interfaz de usuario sigue siendo
de consola y se organiza en un menú principal que delega en
cada una de las clases de dominio.
"""

from __future__ import annotations

import json
import os
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

try:
    import pandas as pd
except ImportError:
    pd = None  # así tus funciones pueden seguir avisando "no disponible"


def norm_talla(x):
    """
    Normaliza representaciones de talla:
    - 36.0 (float/str) -> "36"
    - " 36 , 5 " -> "36,5" -> "36.5" (se estandariza a punto)
    - "xs" -> "XS"
    - Mantiene códigos tipo "T36", "U", "TU", etc. en mayúsculas.
    """
    try:
        if x is None:
            return ""
        # str limpio y upper
        s = str(x).strip()
        if s == "":
            return ""
        s = s.replace(",", ".").strip().upper()

        # float entero -> int
        try:
            f = float(s)
            if f.is_integer():
                return str(int(f))
            # si es número con decimales reales, lo dejamos como viene (p.ej. 36.5)
            return s
        except Exception:
            pass

        # "NNN.0" textual
        if s.endswith(".0") and s[:-2].isdigit():
            return s[:-2]

        # normalización mínima de alias de talla única
        if s in {"U", "UNICA", "ÚNICA", "UNITALLA", "ONE SIZE", "OS", "TU"}:
            return "U"

        return s
    except Exception:
        return str(x).strip().upper()

import re

TALLA_ORDEN_TEXTUAL = {
    "XXXS": 0,
    "XXS": 1,
    "XS": 2,
    "S": 3,
    "M": 4,
    "L": 5,
    "XL": 6,
    "XXL": 7,
    "3XL": 8,
    "4XL": 9,
    "5XL": 10,
    "U": 11,  # Talla única al final de las textuales
}

def talla_sort_key(t: str):
    """
    Clave de orden natural para tallas:
    1) Números (p.ej., 34, 36) y prefijo 'T' + número (T36) -> orden numérico
    2) Textuales conocidas (XS..XXL..U) -> orden definido
    3) Resto -> alfabético al final
    """
    s = norm_talla(t)

    # 1) Estrictamente numérica (o decimal)
    if re.fullmatch(r"\d+(\.\d+)?", s):
        # Si tiene decimales, ordénala por float (zapatillas 36.5)
        try:
            return (0, float(s))
        except Exception:
            return (0, float(int(s)))  # fallback

    # 1b) 'T' + número (T36, T38.5)
    m = re.fullmatch(r"T(\d+(\.\d+)?)", s)
    if m:
        num = m.group(1)
        try:
            return (0, float(num))
        except Exception:
            return (0, float(int(num)))

    # 2) Textuales conocidas (XS..XXL..U)
    if s in TALLA_ORDEN_TEXTUAL:
        return (1, TALLA_ORDEN_TEXTUAL[s], s)

    # 3) Resto (alfabético)
    return (2, 0, s)

    
def norm_codigo(x: object) -> str:
    """
    Normaliza códigos numérico-textuales (pedido, albarán, etc.):
    - 1234.0 / "1234.0" -> "1234"
    - "  00123 " -> "00123" (respeta ceros a la izquierda si no es float puro)
    - None -> ""
    """
    if x is None:
        return ""
    s = str(x).strip()
    s_dot = s.replace(",", ".")
    try:
        f = float(s_dot)
        if f.is_integer() and s_dot.replace(".", "", 1).isdigit():
            return str(int(f))
    except ValueError:
        pass
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s
def parse_fecha_excel(value) -> str:
    """
    Intenta normalizar una fecha proveniente de Excel a 'YYYY-MM-DD'.
    Acepta:
    - datetime/pandas.Timestamp
    - serial de Excel (int/float)
    - string en formatos comunes (YYYY-MM-DD, DD/MM/YYYY, etc.)
    Devuelve '' si no se puede interpretar.
    """
    try:
        # Vacíos / NaN
        if value is None:
            return ""
        if pd is not None:
            try:
                # pd.isna maneja NaT/NaN
                if pd.isna(value):
                    return ""
            except Exception:
                pass

        # datetime o Timestamp
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")

        # Serial de Excel (número de días desde 1899-12-30)
        if isinstance(value, (int, float)):
            base = datetime(1899, 12, 30)
            # soporta fracciones; nos quedamos con la parte de fecha
            dt = base + timedelta(days=float(value))
            return dt.strftime("%Y-%m-%d")

        # String
        s = str(value).strip()
        if not s:
            return ""
        # Intenta ISO directo
        try:
            return datetime.fromisoformat(s.split()[0]).strftime("%Y-%m-%d")
        except Exception:
            pass
        # Prueba con pandas (más flexible)
        if pd is not None:
            try:
                dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
                if not pd.isna(dt):
                    return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        # Fallback manual para DD/MM/YYYY o DD-MM-YYYY
        import re
        m = re.match(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
        if m:
            d, mth, y = m.groups()
            y = ("20" + y) if len(y) == 2 else y
            try:
                return datetime(int(y), int(mth), int(d)).strftime("%Y-%m-%d")
            except Exception:
                return ""
        # Último recurso: intenta quedarse con el primer token "fecha"
        token = s.split()[0]
        try:
            return datetime.fromisoformat(token).strftime("%Y-%m-%d")
        except Exception:
            return ""
    except Exception:
        return ""    
    
def prompt_select_name(prompt: str, disponibles: list[str], allow_empty: bool = True) -> str:
    """
    Input con autocompletado por prefijo, selección por índice y sugerencias difusas.
    - Muestra la lista numerada 1..N.
    - Si el usuario teclea un índice válido, selecciona directo.
    - Prefijo único autocompleta.
    - Si no hay prefijo, busca 'contiene' único.
    - Si no hay nada, sugiere 1-3 parecidos (difflib).
    - Enter devuelve "" si allow_empty=True; si no, reintenta.
    """
    nombres = sorted({str(n) for n in disponibles if str(n).strip()})
    if not nombres:
        # Si no hay disponibles, el caller decide si abortar o no; aquí sólo devolvemos "" si se permite.
        return "" if allow_empty else ""

    print("Disponibles:")
    for i, n in enumerate(nombres, 1):
        print(f"{i}. {n}")

    while True:
        s = input(f"{prompt} ").strip()

        # Vacío
        if s == "":
            if allow_empty:
                return ""
            print("Este campo no puede quedar vacío. Escribe un prefijo, parte del nombre o un número de la lista.")
            continue

        # Selección por índice
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(nombres):
                elegido = nombres[idx - 1]
                print(f"→ Seleccionado: {elegido}")
                return elegido
            else:
                print("Índice fuera de rango. Prueba de nuevo.")
                continue

        # Coincidencia exacta
        if s in nombres:
            return s

        # Coincidencias por prefijo (case-insensitive)
        pref = [n for n in nombres if n.lower().startswith(s.lower())]
        if len(pref) == 1:
            print(f"→ Autocompletado: {pref[0]}")
            return pref[0]
        if len(pref) > 1:
            listado = ", ".join(pref[:10]) + (" ..." if len(pref) > 10 else "")
            print(f"Coincidencias (prefijo): {listado}")
            continue

        # Coincidencias por 'contiene' (case-insensitive)
        contiene = [n for n in nombres if s.lower() in n.lower()]
        if len(contiene) == 1:
            print(f"→ Autocompletado: {contiene[0]}")
            return contiene[0]
        if len(contiene) > 1:
            listado = ", ".join(contiene[:10]) + (" ..." if len(contiene) > 10 else "")
            print(f"Coincidencias (contiene): {listado}")
            continue

        # Sugerencias difusas
        try:
            import difflib
            sug = difflib.get_close_matches(s, nombres, n=3, cutoff=0.6)
        except Exception:
            sug = []

        if len(sug) == 1:
            resp = input(f"¿Querías decir '{sug[0]}'? (s/n): ").strip().lower()
            if resp == "s":
                return sug[0]
        elif len(sug) > 1:
            print("Sugerencias:", ", ".join(sug))

        print("❌ No hay coincidencias. Prueba otro prefijo, parte del nombre o un número.")



###############################################################################
# Utilidades de almacenamiento
###############################################################################

class DataStore:
    """Componente de persistencia genérico.

    Este objeto abstrae la lectura y escritura de un fichero JSON.  Se le
    suministra una ruta y una estructura por defecto.  Al cargar, si el
    fichero no existe o contiene datos corruptos, se usa la estructura por
    defecto.  Al guardar, se serializa el diccionario interno en JSON con
    indentación para facilitar la lectura humana.
    """

    def __init__(self, path: str, default_structure: Dict):
        self.path = path
        # Copiamos el default para no modificar el original
        self.default_structure = json.loads(json.dumps(default_structure))
        self.data = self.load()

    def load(self) -> Dict:
        """Carga el fichero JSON o devuelve la estructura por defecto."""
        if not os.path.exists(self.path):
            # Si no existe, nos aseguramos de crear la carpeta contenedora
            base_dir = os.path.dirname(self.path)
            if base_dir and not os.path.exists(base_dir):
                os.makedirs(base_dir, exist_ok=True)
            return json.loads(json.dumps(self.default_structure))
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Si hay error, devolvemos copia del default
            return json.loads(json.dumps(self.default_structure))

    def save(self) -> None:
        """Guarda el diccionario actual en disco."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

###############################################################################
# Gestor de talleres y clientes
###############################################################################

@dataclass
class Workshop:
    """Representa un taller.

    Por simplicidad sólo se almacenan nombre y contacto.  Se podría ampliar
    con dirección, CIF, etc.  El identificador del taller es el nombre.
    """
    nombre: str
    contacto: Optional[str] = None

@dataclass
class Client:
    """Representa un cliente.

    Contiene nombre y, opcionalmente, datos de contacto.  El identificador
    se basa en el nombre; en un sistema real se usaría un ID único.
    """
    nombre: str
    contacto: Optional[str] = None

class WorkshopManager:
    """Gestor CRUD para talleres."""

    def __init__(self, data_store: DataStore):
        # Internamente guardamos en un diccionario por nombre
        self.store = data_store
        self._talleres: Dict[str, Workshop] = {
            nombre: Workshop(nombre=nombre, contacto=info.get("contacto"))
            for nombre, info in self.store.data.items()
        }

    def add(self, nombre: str, contacto: Optional[str] = None) -> None:
        if nombre in self._talleres:
            print(f"⚠️ El taller '{nombre}' ya existe.")
            return
        self._talleres[nombre] = Workshop(nombre=nombre, contacto=contacto)
        self.store.data[nombre] = {"contacto": contacto}
        self.store.save()
        print(f"✅ Taller '{nombre}' añadido.")

    def edit(self, nombre: str, nuevo_nombre: Optional[str] = None,
             nuevo_contacto: Optional[str] = None) -> None:
        taller = self._talleres.get(nombre)
        if not taller:
            print(f"❌ Taller '{nombre}' no encontrado.")
            return
        # Actualizamos los campos si se proporcionan
        if nuevo_nombre:
            if nuevo_nombre in self._talleres:
                print(f"❌ Ya existe un taller con nombre '{nuevo_nombre}'.")
                return
            # Renombrar la clave
            self._talleres[nuevo_nombre] = self._talleres.pop(nombre)
            self._talleres[nuevo_nombre].nombre = nuevo_nombre
            # Actualizar en el store
            self.store.data[nuevo_nombre] = self.store.data.pop(nombre)
            nombre = nuevo_nombre
        if nuevo_contacto is not None:
            self._talleres[nombre].contacto = nuevo_contacto
            self.store.data[nombre]["contacto"] = nuevo_contacto
        self.store.save()
        print(f"✅ Taller '{nombre}' actualizado.")

    def delete(self, nombre: str) -> None:
        if nombre not in self._talleres:
            print(f"❌ Taller '{nombre}' no encontrado.")
            return
        self._talleres.pop(nombre)
        self.store.data.pop(nombre, None)
        self.store.save()
        print(f"🗑️ Taller '{nombre}' eliminado.")

    def list_all(self) -> List[Workshop]:
        return list(self._talleres.values())


class ClientManager:
    """Gestor CRUD para clientes."""

    def __init__(self, data_store: DataStore):
        self.store = data_store
        self._clientes: Dict[str, Client] = {
            nombre: Client(nombre=nombre, contacto=info.get("contacto"))
            for nombre, info in self.store.data.items()
        }

    def add(self, nombre: str, contacto: Optional[str] = None) -> None:
        if nombre in self._clientes:
            print(f"⚠️ El cliente '{nombre}' ya existe.")
            return
        self._clientes[nombre] = Client(nombre=nombre, contacto=contacto)
        self.store.data[nombre] = {"contacto": contacto}
        self.store.save()
        print(f"✅ Cliente '{nombre}' añadido.")

    def edit(self, nombre: str, nuevo_nombre: Optional[str] = None,
             nuevo_contacto: Optional[str] = None) -> None:
        cliente = self._clientes.get(nombre)
        if not cliente:
            print(f"❌ Cliente '{nombre}' no encontrado.")
            return
        if nuevo_nombre:
            if nuevo_nombre in self._clientes:
                print(f"❌ Ya existe un cliente con nombre '{nuevo_nombre}'.")
                return
            self._clientes[nuevo_nombre] = self._clientes.pop(nombre)
            self._clientes[nuevo_nombre].nombre = nuevo_nombre
            self.store.data[nuevo_nombre] = self.store.data.pop(nombre)
            nombre = nuevo_nombre
        if nuevo_contacto is not None:
            self._clientes[nombre].contacto = nuevo_contacto
            self.store.data[nombre]["contacto"] = nuevo_contacto
        self.store.save()
        print(f"✅ Cliente '{nombre}' actualizado.")

    def delete(self, nombre: str) -> None:
        if nombre not in self._clientes:
            print(f"❌ Cliente '{nombre}' no encontrado.")
            return
        self._clientes.pop(nombre)
        self.store.data.pop(nombre, None)
        self.store.save()
        print(f"🗑️ Cliente '{nombre}' eliminado.")

    def list_all(self) -> List[Client]:
        return list(self._clientes.values())

###############################################################################
# Inventario
###############################################################################

class Inventory:
    """Gestiona el stock real y los movimientos de entradas/salidas."""

    def __init__(self, data_store: DataStore, prevision: 'Prevision'):
        self.store = data_store
        self.prevision = prevision
        # Las siguientes referencias son alias del diccionario de la store
        self.almacen: Dict[str, Dict[str, int]] = self.store.data.setdefault("almacen", {})
        self.historial_entradas: List[Dict] = self.store.data.setdefault("historial_entradas", [])
        self.historial_salidas: List[Dict] = self.store.data.setdefault("historial_salidas", [])
        self.info_modelos: Dict[str, Dict[str, str]] = self.store.data.setdefault("info_modelos", {})

    def _ensure_model(self, modelo: str, descripcion: str = "", color: str = "", cliente: Optional[str] = None) -> None:
        """Asegura que un modelo existe en el inventario y en info_modelos.

        Si se proporciona `cliente`, también se asignará ese valor al modelo en
        info_modelos.  El cliente identifica la entidad a la que está
        asociado el artículo (por ejemplo, el cliente final o el proveedor).
        """
        if modelo not in self.almacen:
            self.almacen[modelo] = {}
        if modelo not in self.info_modelos:
            self.info_modelos[modelo] = {"descripcion": descripcion, "color": color, "cliente": cliente or ""}
        else:
            # Actualizamos cliente si es proporcionado y no existía
            if cliente is not None and not self.info_modelos[modelo].get("cliente"):
                self.info_modelos[modelo]["cliente"] = cliente
        # También sincronizamos con prevision
        if modelo not in self.prevision.info_modelos:
            self.prevision.info_modelos[modelo] = {"descripcion": descripcion, "color": color, "cliente": cliente or ""}

    def register_entry(
        self,
        modelo: str,
        talla: str,
        cantidad: int,
        taller: str = "",
        fecha: Optional[str] = None,
        proveedor: str = "",
        observaciones: str = "",
    ) -> None:
        modelo = str(modelo).strip().upper()
        talla = norm_talla(talla)
        if not modelo or not talla or cantidad <= 0:
            print("❌ Datos de entrada inválidos.")
            return

        if not fecha:
            fecha = datetime.now().strftime("%Y-%m-%d")

        # 1) Histórico de ENTRADAS (incluye taller)
        entrada = {
            "modelo": modelo,
            "talla": talla,
            "cantidad": int(cantidad),
            "fecha": fecha,
            "taller": taller,               # <-- ahora sí lo guardamos
            "proveedor": proveedor,
            "observaciones": observaciones,
        }
       
        self.historial_entradas.append(entrada)

        # 2) Stock real
        self.almacen.setdefault(modelo, {})
        self.almacen[modelo][talla] = self.almacen[modelo].get(talla, 0) + int(cantidad)

        # 3) Órdenes de corte (pedidos_fabricacion)
        cubierto_desde_entrada = int(cantidad)
        pendientes = getattr(self.prevision, "pedidos_fabricacion", {}).get(modelo, [])
        pendientes.sort(key=lambda x: (x.get("fecha") or ""))


        i = 0
        while i < len(pendientes) and cubierto_desde_entrada > 0:
            p = pendientes[i]
            if norm_talla(p.get("talla")) != talla:
                i += 1
                continue
            por_cubrir = int(p.get("cantidad", 0))
            if por_cubrir <= 0:
                i += 1
                continue
            usa = min(por_cubrir, cubierto_desde_entrada)
            p["cantidad"] = por_cubrir - usa
            cubierto_desde_entrada -= usa
            if p["cantidad"] <= 0:
                pendientes.pop(i)
                continue
            i += 1

        # limpiar contenedor vacío con tolerancia
        if modelo in self.prevision.pedidos_fabricacion and not self.prevision.pedidos_fabricacion[modelo]:
            self.prevision.pedidos_fabricacion.pop(modelo, None)


        # 4) Guardar
        self.save()
        self.prevision.save()   # <-- IMPORTANTE: persistir cambios en prevision

        # 5) Mensaje
        cubierto = int(cantidad) - max(cubierto_desde_entrada, 0)
        print(
            f"✅ Entrada registrada: {modelo} {talla} +{cantidad} uds → stock real +{cantidad}. "
            f"Órdenes de corte cubiertas: {cubierto} uds."
        )   

    def register_exit(self, modelo: str, talla: str, cantidad: int, cliente: str,
                  pedido: str, albaran: str, fecha: Optional[str] = None) -> bool:
        """Registra una salida de producto y descuenta pedidos pendientes.
        Permite dejar el stock en negativo (avisa si no hay suficiente).
        """
        modelo = str(modelo).strip().upper()
        talla = norm_talla(talla)
        pedido = norm_codigo(pedido)
        albaran = norm_codigo(albaran)
        
        self.almacen.setdefault(modelo, {})
        self.almacen[modelo].setdefault(talla, 0)

        if fecha is None:
            fecha = datetime.now().strftime("%Y-%m-%d")

        disponible = self.almacen[modelo][talla]
        if cantidad > disponible:
            print(f"⚠️ Stock insuficiente: hay {disponible} uds de {modelo} T{talla}. Registrando salida igualmente.")

        # Descontamos del stock real
        self.almacen[modelo][talla] -= cantidad

        # Registramos la salida
        self.historial_salidas.append({
            "modelo": modelo,
            "talla": talla,
            "cantidad": cantidad,
            "fecha": fecha,
            "pedido": pedido,
            "albaran": albaran,
            "cliente": cliente,
        })

        # Actualizamos pedidos pendientes
        nuevas_pedidos = []
        restante = cantidad
        for p in self.prevision.pedidos:
            p_modelo = str(p.get("modelo","")).strip().upper()
            p_talla = norm_talla(p.get("talla",""))
            if (p_modelo == modelo and
                p_talla == talla and
                norm_codigo(p.get("pedido","")) == pedido and
                restante > 0):
                if restante >= p["cantidad"]:
                    restante -= p["cantidad"]
                else:
                    p["cantidad"] -= restante
                    restante = 0
                    nuevas_pedidos.append(p)
            else:
                nuevas_pedidos.append(p)
        self.prevision.pedidos[:] = nuevas_pedidos

        self.save()
        self.prevision.save()
        print(f"✅ Salida registrada: {modelo} T{talla} -{cantidad}")
        return True


    def modify_stock(self, modelo: str, talla: str, nuevo_valor: Optional[int],
                     descripcion: Optional[str] = None, color: Optional[str] = None,
                     cliente: Optional[str] = None) -> None:
        """Permite añadir/modificar/eliminar cantidades del stock manualmente.

        - Si `nuevo_valor` es `None`, se elimina la talla del modelo.  Si el modelo
          queda sin tallas, se elimina del inventario.
        - Si el modelo no existe, se crea con los datos proporcionados.
        - Si la talla no existe y nuevo_valor es un entero, se añade.
        Además, se puede actualizar la descripción, el color y el cliente del modelo.
        """
        talla = norm_talla(talla)
        # Aseguramos la estructura del modelo e info
        self._ensure_model(modelo, descripcion or "", color or "", cliente)
        if descripcion or color or cliente:
            # Actualizamos info_modelos
            info = self.info_modelos[modelo]
            if descripcion:
                info["descripcion"] = descripcion
            if color:
                info["color"] = color
            if cliente:
                info["cliente"] = cliente
        if nuevo_valor is None:
            # Eliminar talla
            if modelo in self.almacen and talla in self.almacen[modelo]:
                self.almacen[modelo].pop(talla)
                print(f"🗑️ Talla {talla} del modelo {modelo} eliminada.")
                # Si se queda vacío, eliminamos el modelo
                if not self.almacen[modelo]:
                    self.almacen.pop(modelo)
                    self.info_modelos.pop(modelo, None)
                    self.prevision.info_modelos.pop(modelo, None)
                    print(f"🗑️ Modelo {modelo} eliminado (sin tallas).")
            else:
                print(f"❌ No existe {modelo} T{talla}.")
        else:
            # Asignar nuevo valor
            self.almacen.setdefault(modelo, {})
            self.almacen[modelo][talla] = nuevo_valor
            print(f"🛠️ Stock actualizado: {modelo} T{talla} = {nuevo_valor} uds")
        self.save()
        self.prevision.save()

    def update_model_info(self, modelo: str, descripcion: Optional[str] = None,
                          color: Optional[str] = None, cliente: Optional[str] = None) -> None:
        """Actualiza la descripción, color o cliente de un modelo existente."""
        if modelo not in self.info_modelos:
            print(f"❌ El modelo {modelo} no existe en el inventario.")
            return
        info = self.info_modelos[modelo]
        if descripcion:
            info["descripcion"] = descripcion
        if color:
            info["color"] = color
        if cliente is not None:
            info["cliente"] = cliente
        # Sincronizamos con la prevision
        if modelo in self.prevision.info_modelos:
            if descripcion:
                self.prevision.info_modelos[modelo]["descripcion"] = descripcion
            if color:
                self.prevision.info_modelos[modelo]["color"] = color
            if cliente is not None:
                self.prevision.info_modelos[modelo]["cliente"] = cliente
        self.save()
        self.prevision.save()
        print(f"✅ Información del modelo {modelo} actualizada.")

    def consult_stock(self, modelo_filtro: str = "") -> None:
        """Muestra el stock real actual por modelo y talla."""
        modelos = sorted(self.almacen.keys())
        for modelo in modelos:
            if modelo_filtro and modelo != modelo_filtro:
                continue
            print(f"\n🔹 {modelo} - {self.info_modelos.get(modelo, {}).get('descripcion', '')}")
            for talla, cantidad in sorted(self.almacen[modelo].items(), key=lambda x: talla_sort_key(x[0])):
                alerta = "⚠️" if cantidad < 10 else ""
                print(f"  Talla {talla}: {cantidad} uds {alerta}")

    def save(self) -> None:
        self.store.save()
        
    # --- en class Inventory ---
    # >>> PATCH START: Inventory.audit_and_fix_stock + apply_stock_fixes
    def audit_and_fix_stock(self, aplicar: bool = False, solo_modelo: str | None = None) -> list[dict]:
        """
        Audita el stock recalculándolo desde historial_entradas/salidas.
        - aplicar=False: solo calcula y devuelve diferencias (no toca almacén).
        - aplicar=True: aplica TODOS los cambios recibidos (modo legacy, aún soportado).
        - solo_modelo: si se indica, limita la auditoría a ese modelo (upper).

        Devuelve una lista de dicts: {modelo,talla,antes,despues,delta}
        """
        from collections import defaultdict
        neto = defaultdict(int)

        # 1) sumar entradas / salidas
        for e in self.historial_entradas:
            m = str(e.get("modelo","")).strip().upper()
            t = norm_talla(e.get("talla",""))
            if solo_modelo and m != solo_modelo.upper():
                continue
            c = int(e.get("cantidad",0) or 0)
            neto[(m,t)] += c

        for s in self.historial_salidas:
            m = str(s.get("modelo","")).strip().upper()
            t = norm_talla(s.get("talla",""))
            if solo_modelo and m != solo_modelo.upper():
                continue
            c = int(s.get("cantidad",0) or 0)
            neto[(m,t)] -= c

        # 2) asegurar pares que existan en almacén aunque no estén en neto
        for m, tallas in self.almacen.items():
            if solo_modelo and m != solo_modelo.upper():
                continue
            for t in tallas.keys():
                neto.setdefault((m,t), tallas[t])

        # 3) construir lista de diferencias
        cambios = []
        for (m,t), esperado in sorted(neto.items()):
            real = self.almacen.get(m, {}).get(t, 0)
            if real != esperado:
                cambios.append({
                    "modelo": m,
                    "talla": t,
                    "antes": real,
                    "despues": esperado,
                    "delta": int(esperado) - int(real),
                })

        # legado: aplicar todos si se pide (comportamiento anterior)
        if aplicar and cambios:
            for row in cambios:
                m, t, nuevo = row["modelo"], row["talla"], row["despues"]
                self.almacen.setdefault(m, {})
                self.almacen[m][t] = nuevo
            self.save()

        return cambios

    def apply_stock_fixes(self, cambios: list[dict]) -> int:
        """
        Aplica una lista de cambios tal como la devuelve audit_and_fix_stock(aplicar=False).
        Devuelve el número de tallas ajustadas.
        """
        if not cambios:
            return 0
        for row in cambios:
            m, t, nuevo = row["modelo"], row["talla"], int(row["despues"])
            self.almacen.setdefault(m, {})
            self.almacen[m][t] = nuevo
        self.save()
        return len(cambios)
    # >>> PATCH END

    # >>> PATCH START: Inventory.regularize_history_to_current
    def regularize_history_to_current(
        self,
        cambios: list[dict],
        fecha: Optional[str] = None,
        observacion: str = "Ajuste auditoría para cuadrar histórico con stock real",
    ) -> int:
        """
        Crea asientos de AJUSTE en historiales para que el neto (entradas-salidas)
        pase a coincidir con el stock real actual. NO toca 'almacen'.

        Para cada cambio:
        delta = esperado - real
        delta > 0 -> añadir SALIDA de AJUSTE por 'delta'
        delta < 0 -> añadir ENTRADA de AJUSTE por '-delta'

        Devuelve el nº de asientos creados.
        """
        if not cambios:
            return 0

        if not fecha:
            fecha = datetime.now().strftime("%Y-%m-%d")

        creados = 0
        for row in cambios:
            m = str(row["modelo"]).strip().upper()
            t = norm_talla(row["talla"])
            delta = int(row["delta"])

            if delta == 0:
                continue

            meta = {
                "modelo": m,
                "talla": t,
                "cantidad": abs(delta),
                "fecha": fecha,
                # metadatos de ajuste
                "taller": "",
                "proveedor": "",
                "observaciones": f"{observacion} | antes={row['antes']} despues={row['despues']} delta={delta:+}",
                "ajuste": True,
                "origen": "regularizacion_auditoria",
            }

            if delta < 0:
                # falta en histórico: metemos ENTRADA de ajuste por -delta
                entrada = dict(meta)
                self.historial_entradas.append(entrada)
            else:
                # sobra en histórico: metemos SALIDA de ajuste por delta
                salida = {
                    "modelo": m,
                    "talla": t,
                    "cantidad": delta,
                    "fecha": fecha,
                    "pedido": "AJUSTE",
                    "albaran": "AJUSTE",
                    "cliente": "",
                    "ajuste": True,
                    "origen": "regularizacion_auditoria",
                    "observaciones": f"{observacion} | antes={row['antes']} despues={row['despues']} delta={delta:+}",
                }
                self.historial_salidas.append(salida)

            creados += 1

        # Solo guardamos historiales; NO tocamos self.almacen
        self.save()
        return creados
    # >>> PATCH END


###############################################################################
# Previsión
###############################################################################

class Prevision:
    """Gestiona la previsión de stock, órdenes de fabricación y pedidos."""

    def __init__(self, data_store: DataStore):
        self.store = data_store
        self.pedidos_fabricacion: Dict[str, List[Dict]] = \
        self.store.data.setdefault("pedidos_fabricacion", {})
        self.ordenes: List[Dict] = self.store.data.setdefault("ordenes", [])
        self.pedidos: List[Dict] = self.store.data.setdefault("pedidos", [])
        self.info_modelos: Dict[str, Dict[str, str]] = self.store.data.setdefault("info_modelos", {})

    # ---------------------------------------------------------------------
    # Registro de órdenes de fabricación
    # ---------------------------------------------------------------------
    def register_order(self, modelo: str, talla: str, cantidad: int, fecha: Optional[str] = None) -> None:
        talla = norm_talla(talla)
        if fecha is None:
            fecha = datetime.now().strftime("%Y-%m-%d")
        self.pedidos_fabricacion.setdefault(modelo, []).append({
            "talla": talla,
            "cantidad": cantidad,
            "fecha": fecha
        })
        self.save()
        print(f"✅ Orden de fabricación registrada: {modelo} T{talla} +{cantidad}")


    # ---------------------------------------------------------------------
    # Registro de pedidos pendientes
    # ---------------------------------------------------------------------
    def register_pending(self, modelo: str, talla: str, cantidad: int, pedido: str,
                     cliente: str, fecha: Optional[str] = None,
                     numero_pedido: Optional[str] = None) -> None:
        talla = norm_talla(talla)
        if fecha is None:
            fecha = datetime.now().strftime("%Y-%m-%d")
        modelo = str(modelo).strip().upper()
        pedido = norm_codigo(pedido)
        numero_pedido = norm_codigo(numero_pedido)

        self.pedidos.append({
            "modelo": modelo,
            "talla": talla,
            "cantidad": int(cantidad),
            "pedido": pedido,
            "numero_pedido": numero_pedido or "",
            "cliente": cliente,
            "fecha": fecha,
        })
        self.save()
        print(f"✅ Pedido pendiente registrado: {modelo} T{talla} -{cantidad}")
        
    # -----------------------------
    # Utilidades de listado (con índice)
    # -----------------------------
    def list_pendings(self):
        """Devuelve lista [(idx, dict_pedido), ...]."""
        return list(enumerate(self.pedidos, start=1))

    # -----------------------------
    # Editar / Eliminar PEDIDOS PENDIENTES
    # -----------------------------
    def edit_pending(self, index: int, modelo: str = None, talla: str = None,
                 cantidad: int = None, pedido: str = None,
                 cliente: str = None, fecha: str = None,
                 numero_pedido: str = None) -> None:
        """Edita un pedido pendiente sin tocar stock_previsto (se calcula al vuelo)."""
        if index < 1 or index > len(self.pedidos):
            print("❌ Índice fuera de rango.")
            return

        ped = self.pedidos[index - 1]

        # Aplicar cambios directamente sobre el pedido
        if modelo: ped["modelo"] = modelo.upper().strip()
        if talla: ped["talla"] = norm_talla(talla)
        if cantidad is not None:
            if cantidad < 0:
                print("❌ Cantidad no puede ser negativa en pedidos.")
                return
            ped["cantidad"] = cantidad
        if pedido is not None: ped["pedido"] = norm_codigo(pedido)
        if cliente is not None: ped["cliente"] = cliente
        if fecha is not None: ped["fecha"] = fecha
        if numero_pedido is not None: ped["numero_pedido"] = norm_codigo(numero_pedido)

        self.save()
        print("✅ Pedido pendiente actualizado.")

    def delete_pending(self, index: int) -> None:
        """Elimina un pedido pendiente sin tocar stock_previsto (se calcula al vuelo)."""
        if index < 1 or index > len(self.pedidos):
            print("❌ Índice fuera de rango.")
            return

        self.pedidos.pop(index - 1)
        self.save()
        print("🗑️ Pedido pendiente eliminado.")

    # -----------------------------
    # Gestión de PEDIDOS_DE_FABRICACION (antes 'ordenes')
    # -----------------------------
    def list_fabrication(self):
        """Aplana pedidos_fabricacion -> lista [(idx, item_dict)] para menú."""
        items = []
        idx = 1
        for modelo in sorted(self.pedidos_fabricacion.keys()):
            for i, it in enumerate(self.pedidos_fabricacion[modelo]):
                items.append((
                    idx,
                    {
                        "modelo": modelo,
                        "talla": norm_talla(it.get("talla","")),
                        "cantidad": int(it.get("cantidad",0) or 0),
                        "fecha": it.get("fecha") or "",
                        "_pos": i  # posición interna dentro del modelo
                    }
                ))
                idx += 1
        return items

    def delete_fabrication(self, index: int) -> None:
        """Elimina un ítem de pedidos_fabricacion sin tocar stock_previsto."""
        items = self.list_fabrication()
        if index < 1 or index > len(items):
            print("❌ Índice fuera de rango.")
            return

        _, it = items[index - 1]
        m = it["modelo"]
        pos = it["_pos"]

        self.pedidos_fabricacion[m].pop(pos)
        if not self.pedidos_fabricacion[m]:
            self.pedidos_fabricacion.pop(m, None)

        self.save()
        print("🗑️ Orden de fabricación eliminada.")

    
    def edit_fabrication_qty(self, index: int, nueva_cantidad: int) -> None:
        """
        Cambia las unidades de una orden en pedidos_fabricacion sin tocar stock_previsto.
        - Si nueva_cantidad == 0, elimina la orden (equivalente a delete_fabrication).
        """
        if nueva_cantidad is None:
            print("❌ Debes indicar una cantidad nueva.")
            return
        if nueva_cantidad < 0:
            print("❌ La cantidad no puede ser negativa.")
            return

        items = self.list_fabrication()
        if index < 1 or index > len(items):
            print("❌ Índice fuera de rango.")
            return

        _, it = items[index - 1]
        m = it["modelo"]
        pos = it["_pos"]

        if nueva_cantidad == 0:
            # Borrar la orden
            self.pedidos_fabricacion[m].pop(pos)
            if not self.pedidos_fabricacion[m]:
                self.pedidos_fabricacion.pop(m, None)
            self.save()
            print("🗑️ Orden de fabricación eliminada (cantidad editada a 0).")
            return

        # Actualizar la cantidad de la orden
        self.pedidos_fabricacion[m][pos]["cantidad"] = int(nueva_cantidad)
        self.save()
        print(f"✏️ Orden actualizada: {m} T{it['talla']} → {nueva_cantidad}.")



    # ---------------------------------------------------------------------
    # Cálculo de stock estimado
    # ---------------------------------------------------------------------
    def calc_estimated_stock(self, inventory: Inventory) -> List[Dict[str, object]]:
        """
        Stock estimado = stock real + (sumatorio de pedidos_fabricacion) - (sumatorio de pedidos pendientes),
        calculado al vuelo por modelo/talla. No usa 'stock_previsto' persistido.
        """
        result: List[Dict[str, object]] = []

        # Construir el set de todos los modelos y tallas que aparecen en alguna parte
        modelos = set(inventory.almacen.keys()) \
                | set(self.pedidos_fabricacion.keys()) \
                | {str(p.get("modelo","")).strip().upper() for p in self.pedidos}

        for modelo in sorted(modelos):
            info = inventory.info_modelos.get(modelo, {}) or self.info_modelos.get(modelo, {})

            tallas = set(inventory.almacen.get(modelo, {}).keys())
            tallas |= {norm_talla(it.get("talla","")) for it in self.pedidos_fabricacion.get(modelo, [])}
            tallas |= {norm_talla(p.get("talla","")) for p in self.pedidos if str(p.get("modelo","")).strip().upper() == modelo}

            for talla in sorted(tallas, key=talla_sort_key):
                real = int(inventory.almacen.get(modelo, {}).get(talla, 0))

                fabricar = sum(
                    int(it.get("cantidad", 0) or 0)
                    for it in self.pedidos_fabricacion.get(modelo, [])
                    if norm_talla(it.get("talla","")) == talla
                )

                pendientes = sum(
                    int(p.get("cantidad", 0) or 0)
                    for p in self.pedidos
                    if str(p.get("modelo","")).strip().upper() == modelo
                    and norm_talla(p.get("talla","")) == talla
                )

                total = real + fabricar - pendientes

                result.append({
                    "modelo": modelo,
                    "descripcion": info.get("descripcion", ""),
                    "color": info.get("color", ""),
                    "talla": talla,
                    "stock_estimado": total,
                })

        return result


    
    def save(self) -> None:
        self.store.data["ordenes"] = self.ordenes
        self.store.data["pedidos"] = self.pedidos
        self.store.data["info_modelos"] = self.info_modelos
        self.store.data["pedidos_fabricacion"] = self.pedidos_fabricacion
        # Ojo: NO escribir "stock"
        self.store.save()


###############################################################################
# Sistema principal
###############################################################################

class GestorStock:
    """Clase orquestadora que expone un menú de consola para interactuar.

    Agrupa instancias de Inventory, Prevision, WorkshopManager y ClientManager.
    """
    def convertir_a_str_sin_decimal(self, valor) -> str:
        """Alias a norm_codigo para mantener compatibilidad con el código existente."""
        return norm_codigo(valor)
    
    def __init__(self,
                 path_inventario: str = "datos_almacen.json",
                 path_prevision: str = "prevision.json",
                 path_talleres: str = "talleres.json",
                 path_clientes: str = "clientes.json"):
        # Definimos estructuras por defecto
        inv_default = {
            "almacen": {},
            "historial_entradas": [],
            "historial_salidas": [],
            "info_modelos": {},
        }
        pre_default = {
            "ordenes": [],
            "pedidos": [],
            "info_modelos": {},
            "pedidos_fabricacion": {},
        }
        talleres_default: Dict[str, Dict] = {}
        clientes_default: Dict[str, Dict] = {}
        # Creamos data stores
        self.ds_inventario = DataStore(path_inventario, inv_default)
        self.ds_prevision = DataStore(path_prevision, pre_default)
        self.ds_talleres = DataStore(path_talleres, talleres_default)
        self.ds_clientes = DataStore(path_clientes, clientes_default)
        # Instanciamos entidades
        self.prevision = Prevision(self.ds_prevision)
        self.inventory = Inventory(self.ds_inventario, self.prevision)
        self.workshops = WorkshopManager(self.ds_talleres)
        self.clients = ClientManager(self.ds_clientes)
        # --- Migración/fusión de órdenes antiguas a pedidos_fabricacion ---
        # Toma todo lo que haya en self.prevision.ordenes y lo asegura en pedidos_fabricacion
        # sin duplicar talla/fecha para un mismo modelo. Se ejecuta SOLO una vez.
        migrado = self.ds_prevision.data.get("__migracion_ordenes_fusionada__", False)
        if self.prevision.ordenes and not migrado:
            for o in self.prevision.ordenes:
                m = str(o.get("modelo", "")).strip().upper()
                t = norm_talla(o.get("talla", ""))
                c = int(o.get("cantidad", 0) or 0)
                f = o.get("fecha") or ""
                if c <= 0:
                    continue
                lista = self.prevision.pedidos_fabricacion.setdefault(m, [])
                # intenta fusionar con un item existente (misma talla y fecha)
                existing = next((it for it in lista
                                if norm_talla(it.get("talla")) == t and (it.get("fecha") or "") == f), None)
                if existing:
                    existing["cantidad"] = int(existing.get("cantidad", 0) or 0) + c
                else:
                    lista.append({"talla": t, "cantidad": c, "fecha": f})

            # ✅ marcar como ejecutada y limpiar 'ordenes' para no re-sumar nunca más
            self.ds_prevision.data["__migracion_ordenes_fusionada__"] = True
            self.prevision.ordenes.clear()
            # Persistimos cambios
            self.prevision.save()
            print("ℹ️ Migración a 'pedidos_fabricacion' ejecutada una sola vez.")


        # Normaliza tallas ya guardadas en prevision para evitar '36.0' duplicadas
        try:
            changed = False
            for p in self.prevision.pedidos:
                nt = norm_talla(p.get('talla',''))
                if p.get('talla','') != nt:
                    p['talla'] = nt
                    changed = True
            if changed:
                self.prevision.save()
        except Exception:
            pass
        # Directorios y rutas de exportación/importación
        # Ruta por defecto para los CSV exportados (coincide con los scripts originales)
        self.EXPORT_DIR = r"Z:\GLOBALIA\STOCK UNIFORMES\csv_exportados"
        # Rutas por defecto de los Excel de importación
        self.ALBARANES_EXCEL = r"Y:\AITOR\EXPORTAR_CSV\ALBARANES_SERVIDOS.xlsx"
        self.PEDIDOS_EXCEL = r"Y:\AITOR\EXPORTAR_CSV\PEDIDOS_PENDIENTES.xlsx"
        # Nos aseguramos de que la carpeta de exportación existe
        try:
            os.makedirs(self.EXPORT_DIR, exist_ok=True)
        except Exception:
            # Si falla (por ejemplo, en sistemas sin esa unidad), ignoramos
            pass
    def _exportar_stock_negativo(self) -> None:
        """Exporta un listado de tallas con stock real negativo."""
        info = self.inventory.info_modelos
        stock_negativo = []
        for modelo in sorted(self.inventory.almacen.keys()):
            for talla, cantidad in self.inventory.almacen[modelo].items():
                if cantidad < 0:
                    stock_negativo.append({
                        "MODELO": modelo,
                        "DESCRIPCION": info.get(modelo, {}).get("descripcion", ""),
                        "COLOR": info.get(modelo, {}).get("color", ""),
                        "CLIENTE": info.get(modelo, {}).get("cliente", ""),
                        "TALLA": talla,
                        "STOCK": cantidad
                    })
        if not stock_negativo:
            print("✅ No hay artículos con stock negativo.")
            return
        self._export_csv("11_stock_negativo", stock_negativo, ["MODELO", "DESCRIPCION", "COLOR", "CLIENTE", "TALLA", "STOCK"])

    def _ajustar_stock_negativo_a_cero(self) -> None:
        """Pone a 0 todas las tallas con stock negativo (tras confirmación)."""
        negativos = []
        for modelo in sorted(self.inventory.almacen.keys()):
            for talla, cantidad in self.inventory.almacen[modelo].items():
                if cantidad < 0:
                    negativos.append((modelo, talla, cantidad))
    
        if not negativos:
            print("✅ No hay artículos con stock negativo.")
            return

        print("\n⚠️ Se han detectado las siguientes tallas con stock negativo:")
        for modelo, talla, cantidad in negativos:
            print(f" - {modelo} T{talla}: {cantidad} uds")

        confirm = input("¿Deseas ajustar todos estos valores a 0? (s/n): ").lower()
        if confirm != "s":
            print("❌ Operación cancelada.")
            return

        ajustes = []
        for modelo, talla, cantidad in negativos:
            self.inventory.almacen[modelo][talla] = 0
            ajustes.append({
                "MODELO": modelo,
                "DESCRIPCION": self.inventory.info_modelos.get(modelo, {}).get("descripcion", ""),
                "COLOR": self.inventory.info_modelos.get(modelo, {}).get("color", ""),
                "CLIENTE": self.inventory.info_modelos.get(modelo, {}).get("cliente", ""),
                "TALLA": talla,
                "ANTES": cantidad,
                "AJUSTADO_A": 0
            })
    
        self.inventory.save()
        print(f"✅ Se han ajustado {len(ajustes)} artículos a 0.")

        # Exportar log del ajuste
        fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._export_csv(f"12_ajuste_negativos_{fecha}", ajustes, ["MODELO", "DESCRIPCION", "COLOR", "CLIENTE", "TALLA", "ANTES", "AJUSTADO_A"])
    # ------------------------------------------------------------------
    # Menús de gestión
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Bucle principal interactivo."""
        while True:
            print("\n--- SISTEMA DE GESTIÓN DE STOCK Y PREVISIÓN ---")
            print("1. Registrar entrada de stock")
            print("2. Registrar salida de stock")
            print("3. Consultar stock real")
            print("4. Registrar orden de fabricación")
            print("5. Registrar pedido pendiente")
            print("6. Consultar stock estimado")
            print("7. Gestionar talleres")
            print("8. Gestionar clientes")
            print("9. Exportar datos a CSV")
            print("10. Importar albaranes servidos desde Excel")
            print("11. Importar pedidos pendientes desde Excel")
            print("12. Crear backup manual")
            print("13. Restaurar backup desde fichero")
            print("14. Modificar stock manualmente")
            print("15. Asignar/cambiar cliente de un modelo")
            print("16. Renombrar modelo/artículo")
            print("17. Exportar informe de stock negativo")
            print("18. Ajustar todos los stocks negativos a 0")
            print("19. Gestionar órdenes de fabricación (listar/editar/eliminar)")
            print("20. Gestionar pedidos pendientes (editar/eliminar)")
            print("21. Auditar y arreglar el Stock")
            print("22. Salir")
            opcion = input("Elige una opción: ")
            if opcion == "1":
                self._menu_registrar_entrada()
            elif opcion == "2":
                self._menu_registrar_salida()
            elif opcion == "3":
                modelo = input("Modelo a consultar (vacío para todos): ").upper()
                self.inventory.consult_stock(modelo_filtro=modelo)
            elif opcion == "4":
                self._menu_registrar_orden()
            elif opcion == "5":
                self._menu_registrar_pedido()
            elif opcion == "6":
                est = self.prevision.calc_estimated_stock(self.inventory)
                for item in est:
                    alerta = "⚠️" if item["stock_estimado"] < 10 else ""
                    print(f"{item['modelo']} T{item['talla']} = {item['stock_estimado']} uds {alerta}")
            elif opcion == "7":
                self._menu_talleres()
            elif opcion == "8":
                self._menu_clientes()
            elif opcion == "9":
                # Exportar todos los datos a CSV
                self._exportar_todos_los_datos()
            elif opcion == "10":
                self._importar_albaranes_excel()
            elif opcion == "11":
                self._importar_pedidos_excel()
            elif opcion == "12":
                self._crear_backup_manual()
            elif opcion == "13":
                self._restaurar_backup()
            elif opcion == "14":
                self._menu_modificar_stock()
            elif opcion == "15":
                self._menu_modificar_cliente_modelo()
            elif opcion == "16":
                self._menu_renombrar_modelo()
            elif opcion == "17":
                self._exportar_stock_negativo()
            elif opcion == "18":
                self._ajustar_stock_negativo_a_cero()
            elif opcion == "19":
                self._menu_gestion_ordenes()
            elif opcion == "20":
                self._menu_gestion_pedidos()
            elif opcion == "21":
                self._menu_auditar_y_arreglar()
            elif opcion == "22":
                print("👋 Saliendo del sistema. ¡Hasta pronto!")
                break
            else:
                print("❌ Opción no válida.")
    # Submenú de entrada
        # Submenú de entrada (nuevo flujo: modelo -> taller+fecha -> bucle talla/cantidad)
    def _menu_registrar_entrada(self) -> None:
        modelo = input("Modelo: ").upper().strip()

        # Si el modelo no existe, pedimos info básica una única vez
        if modelo not in self.inventory.info_modelos:
            desc = input("Descripción del modelo: ").strip()
            color = input("Color del modelo: ").strip()
            self.inventory._ensure_model(modelo, descripcion=desc, color=color)

        print("Talleres disponibles:")
        talleres = self.workshops.list_all()
        if not talleres:
            print("ℹ️ No hay talleres dados de alta. Puedes crearlos en 'Gestionar talleres'.")
            taller = ""  # nada que elegir
        else:
            talleres_nombres = [t.nombre for t in talleres]
            taller = prompt_select_name("Taller (prefijo o Enter para vacío):", talleres_nombres, allow_empty=True)

        # Fecha única para todas las líneas (enter = hoy)
        fecha = input("Fecha (YYYY-MM-DD, dejar vacío para hoy): ").strip() or None

        print("\nIntroduce líneas de (Talla, Cantidad). Deja la Talla vacía para terminar.")
        while True:
            talla_raw = input("Talla: ").strip()

            if talla_raw == "":
                print("✅ Finalizado registro de entradas para este modelo.")
                break

            talla = norm_talla(talla_raw)
            try:
                cantidad = int(input("Cantidad: ").strip())
            except ValueError:
                print("❌ Cantidad no válida. Inténtalo de nuevo.")
                continue

            if cantidad == 0:
                print("⚠️ Cantidad 0 ignorada.")
                continue
            if cantidad < 0:
                print("⚠️ Cantidad negativa no permitida en entradas. Usa 'Modificar stock' si deseas ajustar.")
                continue

            self.inventory.register_entry(modelo, talla, cantidad, taller, fecha)


    # Submenú de salida
    # Submenú de salida (nuevo flujo: modelo -> cliente+pedido+albarán+fecha -> bucle talla/cantidad)
    def _menu_registrar_salida(self) -> None:
        # 1) Modelo (una vez)
        modelo = input("Modelo: ").upper().strip()
        if not modelo:
            print("❌ Modelo vacío. Cancelado.")
            return

        # Si el modelo no existe en info, damos opción a crearlo mínimamente (opcional)
        if modelo not in self.inventory.info_modelos and modelo not in self.prevision.info_modelos:
            print("ℹ️ El modelo no existe en el catálogo. Puedes introducir datos básicos (opcional).")
            desc = input("Descripción del modelo (opcional): ").strip()
            color = input("Color del modelo (opcional): ").strip()
            # Solo para tenerlo en catálogo (no toca stock)
            self.inventory._ensure_model(modelo, descripcion=desc, color=color)

        # 2) Cliente (mostrar listado una vez; dejamos vacío si no aplica)
        print("Clientes disponibles:")
        clientes = self.clients.list_all()
        if not clientes:
            print("ℹ️ No hay clientes dados de alta. Puedes crearlos en 'Gestionar clientes'.")
            cliente = ""  # nada que elegir
        else:
            clientes_nombres = [c.nombre for c in clientes]
            cliente = prompt_select_name("Cliente (prefijo o Enter para vacío):", clientes_nombres, allow_empty=True)


        # 3) Pedido y albarán (una vez)
        pedido = norm_codigo(input("Número de pedido: "))
        albaran = norm_codigo(input("Número de albarán: "))

        # 4) Fecha única para todas las líneas (enter = hoy)
        fecha = input("Fecha (YYYY-MM-DD, dejar vacío para hoy): ").strip() or None

        # 5) Bucle de líneas (talla, cantidad); talla vacía para terminar
        print("\nIntroduce líneas de (Talla, Cantidad). Deja la Talla vacía para terminar.")
        while True:
            talla_raw = input("Talla: ").strip()
            if talla_raw == "":
                print("✅ Finalizado registro de salidas para este modelo.")
                break

            talla = norm_talla(talla_raw)
            try:
                cantidad = int(input("Cantidad: ").strip())
            except ValueError:
                print("❌ Cantidad no válida. Inténtalo de nuevo.")
                continue

            if cantidad == 0:
                print("⚠️ Cantidad 0 ignorada.")
                continue
            if cantidad < 0:
                print("⚠️ Cantidad negativa no permitida en salidas. Usa 'Modificar stock' si quieres ajustar manualmente.")
                continue

            # Si el cliente quedó vacío, intentamos resolverlo como en la importación:
            # 1) por un pendiente coincidente; 2) por info_modelos; 3) vacío.
            cliente_resuelto = cliente
            if not cliente_resuelto:
                cliente_pend = ""
                for p in self.prevision.pedidos:
                    if (str(p.get("modelo","")).strip().upper() == modelo and
                        norm_talla(p.get("talla","")) == talla and
                        p.get("pedido","") == pedido):
                        cliente_pend = p.get("cliente","") or ""
                        if cliente_pend:
                            break
                cliente_info = self.prevision.info_modelos.get(modelo, {}).get("cliente", "")
                cliente_resuelto = cliente_pend or cliente_info or ""

            self.inventory.register_exit(
                modelo=modelo,
                talla=talla,
                cantidad=cantidad,
                cliente=cliente_resuelto,
                pedido=pedido,
                albaran=albaran,
                fecha=fecha
            )


    # Submenú para registrar orden de fabricación (fecha -> modelo -> bucle talla/cantidad)
    def _menu_registrar_orden(self) -> None:
        # 1) Fecha única para todas las líneas (enter = hoy)
        fecha = input("Fecha (YYYY-MM-DD, dejar vacío para hoy): ").strip() or None

        # 2) Modelo (una vez)
        modelo = input("Modelo: ").upper().strip()
        if not modelo:
            print("❌ Modelo vacío. Cancelado.")
            return

        # Si el modelo no existe en info, pide datos mínimos una sola vez (opcional)
        if modelo not in self.inventory.info_modelos and modelo not in self.prevision.info_modelos:
            desc = input("Descripción del modelo (opcional): ").strip()
            color = input("Color del modelo (opcional): ").strip()
            # Sólo para tenerlo en catálogo; no toca stocks
            self.inventory._ensure_model(modelo, descripcion=desc, color=color)

        # 3) Bucle de líneas (talla, cantidad); talla vacía para terminar
        print("\nIntroduce líneas de (Talla, Cantidad). Deja la Talla vacía para terminar.")
        while True:
            talla_raw = input("Talla: ").strip()
            if talla_raw == "":
                print("✅ Finalizado registro de órdenes de fabricación para este modelo.")
                break

            talla = norm_talla(talla_raw)
            try:
                cantidad = int(input("Cantidad: ").strip())
            except ValueError:
                print("❌ Cantidad no válida. Inténtalo de nuevo.")
                continue

            if cantidad <= 0:
                print("⚠️ Cantidad debe ser positiva. Línea ignorada.")
                continue

            # Registra la orden (se acumula en pedidos_fabricacion)
            self.prevision.register_order(modelo, talla, cantidad, fecha=fecha)


    # Submenú para registrar pedido pendiente
    def _menu_registrar_pedido(self) -> None:
        modelo = input("Modelo: ").upper()
        talla = norm_talla(input("Talla: "))
        try:
            cantidad = int(input("Cantidad: "))
        except ValueError:
            print("❌ Cantidad no válida.")
            return

        print("Clientes disponibles:")
        clientes_lista = self.clients.list_all()
        if not clientes_lista:
            print("❌ No hay clientes dados de alta. Crea uno en 'Gestionar clientes'.")
            return

        clientes_nombres = [c.nombre for c in clientes_lista]
        cliente = prompt_select_name("Cliente (prefijo, parte del nombre o número):", clientes_nombres, allow_empty=False)

        pedido = norm_codigo(input("Número de pedido: "))
        numero_pedido = norm_codigo(input("Número interno de pedido (opcional): ")) or None

        fecha = input("Fecha (YYYY-MM-DD, dejar vacío para hoy): ") or None

        self.prevision.register_pending(
            modelo, talla, cantidad, pedido, cliente, fecha=fecha, numero_pedido=numero_pedido
        )
    
    # >>> PATCH START: nuevo submenú de auditoría selectiva
    def _parse_index_selection(self, s: str, max_idx: int) -> list[int]:
        """
        Convierte expresiones tipo '1,3,5-8,12' en una lista de índices únicos (1..max_idx).
        Ignora fuera de rango.
        """
        sel = set()
        for token in s.replace(" ", "").split(","):
            if not token:
                continue
            if "-" in token:
                a, b = token.split("-", 1)
                if a.isdigit() and b.isdigit():
                    a, b = int(a), int(b)
                    if a <= b:
                        for x in range(a, b+1):
                            if 1 <= x <= max_idx:
                                sel.add(x)
            else:
                if token.isdigit():
                    x = int(token)
                    if 1 <= x <= max_idx:
                        sel.add(x)
        return sorted(sel)

    def _menu_auditar_y_arreglar(self) -> None:
        """
        1) Audita sin aplicar
        2) Muestra diferencias con índice
        3) Deja aplicar: todo, selección, solo positivos, solo negativos
        4) Permite exportar CSV del informe antes/después
        """
        filtro_modelo = input("Auditar solo un modelo (Enter = todos): ").strip().upper() or None
        cambios = self.inventory.audit_and_fix_stock(aplicar=False, solo_modelo=filtro_modelo)

        if not cambios:
            print("✅ Sin desajustes. Todo cuadra con el histórico.")
            return

        # Mostrar listado paginado básico (hasta 200 por pantalla para no saturar)
        print("\n🔎 DIFERENCIAS DETECTADAS (antes -> después) [delta]")
        for i, row in enumerate(cambios, 1):
            print(f"{i:>4}. {row['modelo']} T{row['talla']}: {row['antes']} -> {row['despues']}  [Δ {row['delta']:+}]")
            if i % 200 == 0 and i < len(cambios):
                cont = input("Pulsa Enter para ver más (o 'q' para parar vista): ").strip().lower()
                if cont == "q":
                    break

        print("\nOpciones:")
        print("  1) Aplicar TODOS")
        print("  2) Aplicar por selección (p.ej. 1,3,5-8)")
        print("  3) Aplicar solo con Δ positivo (sube stock)")
        print("  4) Aplicar solo con Δ negativo (baja stock)")
        print("  5) Exportar informe CSV y salir (sin aplicar)")
        print("  6) Cancelar (no aplicar)")
        print("  7) Generar asientos de regularización (NO toca stock)")

        op = input("Elige opción: ").strip()

        if op in ("6", "c", "C"):
            print("❌ Operación cancelada. No se aplican cambios.")
            return

        if op == "5":
            rows = [{
                "MODELO": r["modelo"],
                "TALLA": r["talla"],
                "ANTES": r["antes"],
                "DESPUES": r["despues"],
                "DELTA": r["delta"]
            } for r in cambios]
            self._export_csv("21_auditoria_stock", rows, ["MODELO","TALLA","ANTES","DESPUES","DELTA"])
            print("✅ Informe exportado. No se han aplicado cambios.")
            return

        # NUEVA RAMA: REGULARIZACIÓN DE HISTÓRICO
        if op == "7":
            # elegir universo (todos / selección / Δ+/Δ-)
            print("\nRegularizar histórico contra stock real. Universo de líneas:")
            print("  a) Todas")
            print("  b) Por selección (índices)")
            print("  c) Solo Δ positivo (sobran en histórico → salidas de ajuste)")
            print("  d) Solo Δ negativo (faltan en histórico → entradas de ajuste)")
            u = input("Elige [a/b/c/d]: ").strip().lower()

            a_regularizar = []
            if u == "a":
                a_regularizar = cambios[:]
            elif u == "b":
                s = input("Índices a regularizar (ej. 1,3,5-8): ").strip()
                idxs = self._parse_index_selection(s, len(cambios))
                if not idxs:
                    print("❌ Selección vacía. Cancelado.")
                    return
                a_regularizar = [cambios[i-1] for i in idxs]
            elif u == "c":
                a_regularizar = [r for r in cambios if r["delta"] > 0]
                if not a_regularizar:
                    print("ℹ️ No hay registros con Δ positivo.")
                    return
            elif u == "d":
                a_regularizar = [r for r in cambios if r["delta"] < 0]
                if not a_regularizar:
                    print("ℹ️ No hay registros con Δ negativo.")
                    return
            else:
                print("❌ Opción no válida.")
                return

            # fecha y observación
            fecha = input("Fecha para los asientos (YYYY-MM-DD, Enter=hoy): ").strip() or None
            obs = input("Observación (opcional): ").strip() or "Ajuste auditoría"

            # Confirmación
            print(f"\nSe crearán {len(a_regularizar)} asientos de regularización en el HISTÓRICO (sin tocar stock). Ejemplos:")
            for r in a_regularizar[:10]:
                signo = "SALIDA" if r["delta"] > 0 else "ENTRADA"
                unidades = abs(int(r["delta"]))
                print(f"  - {r['modelo']} T{r['talla']}: {signo} AJUSTE x{unidades} (antes={r['antes']} esperado={r['despues']} Δ={r['delta']:+})")
            resp = input("¿Confirmas? (s/n): ").strip().lower()
            if resp != "s":
                print("❌ Operación cancelada.")
                return

            n = self.inventory.regularize_history_to_current(a_regularizar, fecha=fecha, observacion=obs)

            # Export de log de asientos creados
            from datetime import datetime
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            rows = []
            for r in a_regularizar:
                rows.append({
                    "FECHA": fecha or datetime.now().strftime("%Y-%m-%d"),
                    "MODELO": r["modelo"],
                    "TALLA": r["talla"],
                    "TIPO_ASIENTO": "SALIDA" if r["delta"] > 0 else "ENTRADA",
                    "UNIDADES": abs(int(r["delta"])),
                    "ANTES_STOCK_REAL": r["antes"],
                    "NETO_HISTORICO_ANTES": r["despues"],  # el esperado antes de regularizar
                    "OBSERVACION": obs,
                })
            self._export_csv(f"21_regularizaciones_historico_{ts}", rows,
                            ["FECHA","MODELO","TALLA","TIPO_ASIENTO","UNIDADES","ANTES_STOCK_REAL","NETO_HISTORICO_ANTES","OBSERVACION"])

            print(f"✅ Creados {n} asientos de regularización y exportado el log.")
            # TIP: si ahora vuelves a auditar, debería dar 0 diferencias.
            return

        aplicar = []
        if op == "1":
            aplicar = cambios[:]  # todos
        elif op == "2":
            s = input("Índices a aplicar (ej. 1,3,5-8): ").strip()
            idxs = self._parse_index_selection(s, len(cambios))
            if not idxs:
                print("❌ Selección vacía. Cancelado.")
                return
            aplicar = [cambios[i-1] for i in idxs]
        elif op == "3":
            aplicar = [r for r in cambios if r["delta"] > 0]
            if not aplicar:
                print("ℹ️ No hay registros con Δ positivo.")
                return
        elif op == "4":
            aplicar = [r for r in cambios if r["delta"] < 0]
            if not aplicar:
                print("ℹ️ No hay registros con Δ negativo.")
                return
        else:
            print("❌ Opción no válida.")
            return

        # Confirmación
        print(f"\nVas a aplicar {len(aplicar)} ajustes. Ejemplos:")
        for r in aplicar[:10]:
            print(f"  - {r['modelo']} T{r['talla']}: {r['antes']} -> {r['despues']} (Δ {r['delta']:+})")
        resp = input("¿Confirmas aplicar estos cambios? (s/n): ").strip().lower()
        if resp != "s":
            print("❌ Operación cancelada.")
            return

        n = self.inventory.apply_stock_fixes(aplicar)

        # Exportar log aplicado
        fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        rows = [{
            "MODELO": r["modelo"],
            "TALLA": r["talla"],
            "ANTES": r["antes"],
            "AJUSTADO_A": r["despues"],
            "DELTA": r["delta"]
        } for r in aplicar]
        self._export_csv(f"21_ajustes_aplicados_{fecha}", rows, ["MODELO","TALLA","ANTES","AJUSTADO_A","DELTA"])

        print(f"✅ Aplicados {n} ajustes y exportado el log.")
    # >>> PATCH END

    
    # -----------------------------
    # Gestión manual de ÓRDENES
    # -----------------------------
    def _menu_gestion_ordenes(self) -> None:
        # Operamos sobre prevision.pedidos_fabricacion
        while True:
            print("\n--- Gestión de Órdenes de fabricación ---")
            print("1. Listar órdenes (pedidos_fabricacion)")
            print("2. Editar unidades por índice")
            print("3. Eliminar una orden por índice")
            print("4. Volver")
            op = input("Elige una opción: ").strip()

            if op == "1":
                items = self.prevision.list_fabrication()
                if not items:
                    print("(sin órdenes)")
                else:
                    for idx, it in items:
                        print(f"{idx}. {it['fecha']} - {it['modelo']} T{it['talla']} +{it['cantidad']}")

            elif op == "2":
                try:
                    idx = int(input("Índice de la orden a editar: ").strip())
                    nueva = int(input("Nueva cantidad (0 para eliminar): ").strip())
                except ValueError:
                    print("❌ Valores no válidos.")
                    continue
                self.prevision.edit_fabrication_qty(idx, nueva)

            elif op == "3":
                try:
                    idx = int(input("Índice de la orden a eliminar: ").strip())
                except ValueError:
                    print("❌ Índice no válido.")
                    continue
                self.prevision.delete_fabrication(idx)

            elif op == "4":
                break
            else:
                print("❌ Opción no válida.")


    # -----------------------------
    # Gestión manual de PEDIDOS PENDIENTES
    # -----------------------------
    def _menu_gestion_pedidos(self) -> None:
        while True:
            print("\n--- Gestión de Pedidos pendientes ---")
            print("1. Listar pedidos")
            print("2. Editar un pedido por índice")
            print("3. Eliminar un pedido por índice")
            print("4. Volver")
            op = input("Elige una opción: ").strip()
            if op == "1":
                pedidos = self.prevision.list_pendings()
                if not pedidos:
                    print("(sin pedidos)")
                else:
                    for idx, p in pedidos:
                        num_int = p.get('numero_pedido', '')
                        print(f"{idx}. {p['fecha']} - {p['pedido']} ({num_int}) | {p['modelo']} T{p['talla']} -{p['cantidad']} | Cliente: {p.get('cliente','')}")
            elif op == "2":
                try:
                    idx = int(input("Índice del pedido a editar: ").strip())
                except ValueError:
                    print("❌ Índice no válido.")
                    continue
                m = input("Nuevo modelo (enter para no cambiar): ").strip() or None
                t = input("Nueva talla (enter para no cambiar): ").strip() or None
                c_raw = input("Nueva cantidad (enter para no cambiar): ").strip()
                c = int(c_raw) if c_raw else None
                ped = input("Nuevo Nº de pedido (enter para no cambiar): ").strip() or None
                cli = input("Nuevo cliente (enter para no cambiar): ").strip() or None
                f = input("Nueva fecha YYYY-MM-DD (enter para no cambiar): ").strip() or None
                num_int = input("Nuevo Nº interno (enter para no cambiar): ").strip() or None
                self.prevision.edit_pending(idx, modelo=m, talla=t, cantidad=c,
                                            pedido=ped, cliente=cli, fecha=f, numero_pedido=num_int)
            elif op == "3":
                try:
                    idx = int(input("Índice del pedido a eliminar: ").strip())
                except ValueError:
                    print("❌ Índice no válido.")
                    continue
                self.prevision.delete_pending(idx)
            elif op == "4":
                break
            else:
                print("❌ Opción no válida.")

    # ------------------------------------------------------------------
    # Exportación de datos
    # ------------------------------------------------------------------
    def _export_csv(self, nombre_base: str, rows: List[Dict], campos: List[str]) -> None:
        """Escribe un listado de filas en un CSV en la ruta de exportación.

        Usa como nombre el parámetro `nombre_base` seguido de la fecha actual.
        """
        fecha = datetime.now().strftime("%Y-%m-%d")
        ruta = os.path.join(self.EXPORT_DIR, f"{nombre_base}_{fecha}.csv")
        try:
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=campos, delimiter=';')
                writer.writeheader()
                writer.writerows(rows)
            print(f"✅ Exportado: {ruta}")
        except Exception as e:
            print(f"❌ Error exportando {nombre_base}: {e}")

    def _exportar_todos_los_datos(self) -> None:
        """Exporta las tablas principales a CSV (entradas, salidas, stock, órdenes, pedidos, estimado)."""
        # Exportar entradas con totalizadores
        info = self.inventory.info_modelos
        entradas_export = []
        for e in self.inventory.historial_entradas:
            modelo_info = info.get(e["modelo"], {})
            entradas_export.append({
                "FECHA": e["fecha"],
                "MODELO": e["modelo"],
                "DESCRIPCION": modelo_info.get("descripcion", ""),
                "COLOR": modelo_info.get("color", ""),
                "TALLA": e["talla"],
                "CANTIDAD": e["cantidad"],
                "TALLER": e.get("taller", ""),
                "CLIENTE": e.get("cliente", modelo_info.get("cliente", ""))
            })
        # Añadir totales por modelo y total general
        entradas_sorted = sorted(entradas_export, key=lambda x: (x["MODELO"], talla_sort_key(x["TALLA"])))
        entradas_con_totales = []
        total_general_ent = 0
        total_modelo = 0
        current_model = None
        for row in entradas_sorted:
            modelo = row["MODELO"]
            cantidad = row["CANTIDAD"]
            total_general_ent += cantidad
            if current_model is None:
                current_model = modelo
            if modelo != current_model:
                entradas_con_totales.append({
                    "FECHA": "",
                    "MODELO": current_model,
                    "DESCRIPCION": "",
                    "COLOR": "",
                    "TALLA": "TOTAL MODELO",
                    "CANTIDAD": total_modelo,
                    "TALLER": "",
                    "CLIENTE": ""
                })
                total_modelo = 0
                current_model = modelo
            total_modelo += cantidad
            entradas_con_totales.append(row)
        if current_model is not None:
            entradas_con_totales.append({
                "FECHA": "",
                "MODELO": current_model,
                "DESCRIPCION": "",
                "COLOR": "",
                "TALLA": "TOTAL MODELO",
                "CANTIDAD": total_modelo,
                "TALLER": "",
                "CLIENTE": ""
            })
        entradas_con_totales.append({
            "FECHA": "",
            "MODELO": "",
            "DESCRIPCION": "",
            "COLOR": "",
            "TALLA": "TOTAL GENERAL",
            "CANTIDAD": total_general_ent,
            "TALLER": "",
            "CLIENTE": ""
        })
        self._export_csv("01_entradas", entradas_con_totales, ["FECHA", "MODELO", "DESCRIPCION", "COLOR", "TALLA", "CANTIDAD", "TALLER", "CLIENTE"])

        # También exportamos un resumen de la última fecha de entrada.
        # Agrupamos las entradas por fecha y modelo y calculamos el total de la fecha más reciente.
        if entradas_export:
            # Identificar la última fecha registrada en las entradas (lexicográficamente más reciente).
            fechas = [e["FECHA"] for e in entradas_export if e["FECHA"]]
            try:
                # Convertir a datetime para ordenar correctamente fechas con diferentes formatos
                fechas_dt = [datetime.fromisoformat(f) for f in fechas if f]
                last_date = max(fechas_dt).strftime("%Y-%m-%d")
            except Exception:
                # Si alguna fecha no es ISO, recurrimos a ordenar como cadena
                last_date = max(fechas) if fechas else ""
            entradas_last_summary = []
            total_general_last = 0
            # Agrupamos por modelo
            entries_last = [e for e in entradas_export if e["FECHA"] == last_date]
            modelo_totals: Dict[str, int] = {}
            for e in entries_last:
                modelo_totals[e["MODELO"]] = modelo_totals.get(e["MODELO"], 0) + e["CANTIDAD"]
                total_general_last += e["CANTIDAD"]
            # Generar filas con total por modelo
            for modelo, cant in sorted(modelo_totals.items()):
                entradas_last_summary.append({
                    "FECHA": last_date,
                    "MODELO": modelo,
                    "DESCRIPCION": info.get(modelo, {}).get("descripcion", ""),
                    "COLOR": info.get(modelo, {}).get("color", ""),
                    "TALLA": "TOTAL FECHA",
                    "CANTIDAD": cant,
                    "TALLER": "",
                    "CLIENTE": info.get(modelo, {}).get("cliente", "")
                })
            # Añadir fila total general
            entradas_last_summary.append({
                "FECHA": last_date,
                "MODELO": "",
                "DESCRIPCION": "",
                "COLOR": "",
                "TALLA": "TOTAL FECHA",
                "CANTIDAD": total_general_last,
                "TALLER": "",
                "CLIENTE": ""
            })
            # Guardamos este resumen con un nombre específico
            self._export_csv("07_entradas_ultima_fecha", entradas_last_summary, ["FECHA", "MODELO", "DESCRIPCION", "COLOR", "TALLA", "CANTIDAD", "TALLER", "CLIENTE"])
        # Exportar salidas con totalizadores
        salidas_export = []
        for s in self.inventory.historial_salidas:
            modelo_info = info.get(s["modelo"], {})
            salidas_export.append({
                "FECHA": s["fecha"],
                "MODELO": s["modelo"],
                "DESCRIPCION": modelo_info.get("descripcion", ""),
                "COLOR": modelo_info.get("color", ""),
                "TALLA": s["talla"],
                "CANTIDAD": s["cantidad"],
                "PEDIDO": s["pedido"],
                "ALBARAN": s["albaran"],
                "CLIENTE": s.get("cliente") or modelo_info.get("cliente", "")
            })
        salidas_sorted = sorted(salidas_export, key=lambda x: (x["MODELO"], talla_sort_key(x["TALLA"])))
        salidas_con_totales = []
        total_general_sal = 0
        total_modelo = 0
        current_model = None
        for row in salidas_sorted:
            modelo = row["MODELO"]
            cantidad = row["CANTIDAD"]
            total_general_sal += cantidad
            if current_model is None:
                current_model = modelo
            if modelo != current_model:
                salidas_con_totales.append({
                    "FECHA": "",
                    "MODELO": current_model,
                    "DESCRIPCION": "",
                    "COLOR": "",
                    "TALLA": "TOTAL MODELO",
                    "CANTIDAD": total_modelo,
                    "PEDIDO": "",
                    "ALBARAN": "",
                    "CLIENTE": ""
                })
                total_modelo = 0
                current_model = modelo
            total_modelo += cantidad
            salidas_con_totales.append(row)
        if current_model is not None:
            salidas_con_totales.append({
                "FECHA": "",
                "MODELO": current_model,
                "DESCRIPCION": "",
                "COLOR": "",
                "TALLA": "TOTAL MODELO",
                "CANTIDAD": total_modelo,
                "PEDIDO": "",
                "ALBARAN": "",
                "CLIENTE": ""
            })
        salidas_con_totales.append({
            "FECHA": "",
            "MODELO": "",
            "DESCRIPCION": "",
            "COLOR": "",
            "TALLA": "TOTAL GENERAL",
            "CANTIDAD": total_general_sal,
            "PEDIDO": "",
            "ALBARAN": "",
            "CLIENTE": ""
        })
        self._export_csv("02_salidas", salidas_con_totales, ["FECHA", "MODELO", "DESCRIPCION", "COLOR", "TALLA", "CANTIDAD", "PEDIDO", "ALBARAN", "CLIENTE"])
        # Exportar stock actual
        stock_list = []
        total_general = 0
        for modelo in sorted(self.inventory.almacen.keys()):
            total_modelo = 0
            for talla, cantidad in sorted(self.inventory.almacen[modelo].items(), key=lambda x: talla_sort_key(x[0])):
                stock_list.append({
                    "MODELO": modelo,
                    "DESCRIPCION": info.get(modelo, {}).get("descripcion", ""),
                    "COLOR": info.get(modelo, {}).get("color", ""),
                    "CLIENTE": info.get(modelo, {}).get("cliente", ""),
                    "TALLA": talla,
                    "STOCK": cantidad
                })
                total_modelo += cantidad
                total_general += cantidad
            stock_list.append({
                "MODELO": modelo,
                "DESCRIPCION": "",
                "COLOR": "",
                "CLIENTE": "",
                "TALLA": "TOTAL MODELO",
                "STOCK": total_modelo
            })
        stock_list.append({
            "MODELO": "",
            "DESCRIPCION": "",
            "COLOR": "",
            "CLIENTE": "",
            "TALLA": "TOTAL GENERAL",
            "STOCK": total_general
        })
        self._export_csv("00_stock_actual", stock_list, ["MODELO", "DESCRIPCION", "COLOR", "CLIENTE", "TALLA", "STOCK"])
        # Exportar órdenes de fabricación PENDIENTES (desde pedidos_fabricacion)
        ordenes_export = []
        for modelo, items in self.prevision.pedidos_fabricacion.items():
            modelo_info = info.get(modelo, self.prevision.info_modelos.get(modelo, {}))
            for it in items:
                if int(it.get("cantidad", 0) or 0) <= 0:
                    continue
                ordenes_export.append({
                    "FECHA": it.get("fecha", ""),
                    "MODELO": modelo,
                    "DESCRIPCION": modelo_info.get("descripcion", ""),
                    "COLOR": modelo_info.get("color", ""),
                    "TALLA": norm_talla(it.get("talla", "")),
                    "CANTIDAD": int(it.get("cantidad", 0) or 0),
                })

        ordenes_sorted = sorted(ordenes_export, key=lambda x: (x["MODELO"], talla_sort_key(x["TALLA"])))
        ordenes_con_totales = []
        total_general_ord = 0
        total_modelo = 0
        current_model = None
        for row in ordenes_sorted:
            modelo = row["MODELO"]
            cantidad = row["CANTIDAD"]
            total_general_ord += cantidad
            if current_model is None:
                current_model = modelo
            if modelo != current_model:
                ordenes_con_totales.append({
                    "FECHA": "",
                    "MODELO": current_model,
                    "DESCRIPCION": "",
                    "COLOR": "",
                    "TALLA": "TOTAL MODELO",
                    "CANTIDAD": total_modelo
                })
                total_modelo = 0
                current_model = modelo
            total_modelo += cantidad
            ordenes_con_totales.append(row)
        if current_model is not None:
            ordenes_con_totales.append({
                "FECHA": "",
                "MODELO": current_model,
                "DESCRIPCION": "",
                "COLOR": "",
                "TALLA": "TOTAL MODELO",
                "CANTIDAD": total_modelo
            })
        ordenes_con_totales.append({
            "FECHA": "",
            "MODELO": "",
            "DESCRIPCION": "",
            "COLOR": "",
            "TALLA": "TOTAL GENERAL",
            "CANTIDAD": total_general_ord
        })
        self._export_csv("04_ordenes_fabricacion", ordenes_con_totales, ["FECHA", "MODELO", "DESCRIPCION", "COLOR", "TALLA", "CANTIDAD"])

        # Además, generamos un CSV con totales por fecha y modelo para las órdenes de fabricación.
        if ordenes_export:
            # Agrupar por fecha y modelo
            ordenes_by_date: Dict[Tuple[str, str], int] = {}
            fechas_ord_set = set()
            for o in ordenes_export:
                fecha = o.get("FECHA", "")
                modelo = o["MODELO"]
                fechas_ord_set.add(fecha)
                key = (fecha, modelo)
                ordenes_by_date[key] = ordenes_by_date.get(key, 0) + o["CANTIDAD"]
            # Construir resumen: para cada fecha, totales por modelo y total general
            ordenes_summary: List[Dict[str, object]] = []
            for fecha in sorted(fechas_ord_set):
                total_general_fecha = 0
                # Extraer modelos para esta fecha
                modelos_fecha = {modelo for (f, modelo) in ordenes_by_date.keys() if f == fecha}
                for modelo in sorted(modelos_fecha):
                    cantidad = ordenes_by_date[(fecha, modelo)]
                    total_general_fecha += cantidad
                    ordenes_summary.append({
                        "FECHA": fecha,
                        "MODELO": modelo,
                        "DESCRIPCION": info.get(modelo, self.prevision.info_modelos.get(modelo, {})).get("descripcion", ""),
                        "COLOR": info.get(modelo, self.prevision.info_modelos.get(modelo, {})).get("color", ""),
                        "TALLA": "TOTAL FECHA",
                        "CANTIDAD": cantidad
                    })
                # Añadir total general para la fecha
                ordenes_summary.append({
                    "FECHA": fecha,
                    "MODELO": "",
                    "DESCRIPCION": "",
                    "COLOR": "",
                    "TALLA": "TOTAL FECHA",
                    "CANTIDAD": total_general_fecha
                })
            self._export_csv("08_ordenes_por_fecha", ordenes_summary, ["FECHA", "MODELO", "DESCRIPCION", "COLOR", "TALLA", "CANTIDAD"])
        # Exportar pedidos pendientes
        pedidos_export = []
        for p in self.prevision.pedidos:
            modelo_info = info.get(p["modelo"], self.prevision.info_modelos.get(p["modelo"], {}))
            pedidos_export.append({
                "FECHA": p["fecha"],
                "PEDIDO": p["pedido"],
                "NUMERO_PEDIDO": p.get("numero_pedido", ""),
                "MODELO": p["modelo"],
                "DESCRIPCION": modelo_info.get("descripcion", ""),
                "COLOR": modelo_info.get("color", ""),
                "TALLA": p["talla"],
                "CANTIDAD": p["cantidad"],
                "CLIENTE": p.get("cliente") or modelo_info.get("cliente", "")
            })
        # Añadir totales por modelo y total general a pedidos pendientes
        # Agrupamos por modelo
        pedidos_export_sorted = sorted(pedidos_export, key=lambda x: (x["MODELO"], talla_sort_key(x["TALLA"])))
        pedidos_con_totales = []
        total_general_pedidos = 0
        total_modelo = 0
        current_model = None
        for row in pedidos_export_sorted:
            modelo = row["MODELO"]
            cantidad = row["CANTIDAD"]
            total_general_pedidos += cantidad
            if current_model is None:
                current_model = modelo
            if modelo != current_model:
                # Añadir total del modelo anterior
                pedidos_con_totales.append({
                    "FECHA": "",
                    "PEDIDO": "",
                    "NUMERO_PEDIDO": "",
                    "MODELO": current_model,
                    "DESCRIPCION": "",
                    "COLOR": "",
                    "TALLA": "TOTAL MODELO",
                    "CANTIDAD": total_modelo,
                    "CLIENTE": ""
                })
                total_modelo = 0
                current_model = modelo
            total_modelo += cantidad
            pedidos_con_totales.append(row)
        # Añadir total del último modelo
        if current_model is not None:
            pedidos_con_totales.append({
                "FECHA": "",
                "PEDIDO": "",
                "NUMERO_PEDIDO": "",
                "MODELO": current_model,
                "DESCRIPCION": "",
                "COLOR": "",
                "TALLA": "TOTAL MODELO",
                "CANTIDAD": total_modelo,
                "CLIENTE": ""
            })
        # Añadir total general
        pedidos_con_totales.append({
            "FECHA": "",
            "PEDIDO": "",
            "NUMERO_PEDIDO": "",
            "MODELO": "",
            "DESCRIPCION": "",
            "COLOR": "",
            "TALLA": "TOTAL GENERAL",
            "CANTIDAD": total_general_pedidos,
            "CLIENTE": ""
        })
        self._export_csv("03_pedidos_pendientes", pedidos_con_totales, ["FECHA", "PEDIDO", "NUMERO_PEDIDO", "MODELO", "DESCRIPCION", "COLOR", "TALLA", "CANTIDAD", "CLIENTE"])
        # Exportar stock estimado
        estimado_export = []
        for item in self.prevision.calc_estimated_stock(self.inventory):
            estimado_export.append({
                "MODELO": item["modelo"],
                "DESCRIPCION": item["descripcion"],
                "COLOR": item["color"],
                "TALLA": item["talla"],
                "STOCK_ESTIMADO": item["stock_estimado"]
            })
        # Añadir totales por modelo y total general al stock estimado
        estimado_sorted = sorted(estimado_export, key=lambda x: (x["MODELO"], talla_sort_key(x["TALLA"])))
        estimado_con_totales = []
        total_general_est = 0
        total_modelo = 0
        current_model = None
        for row in estimado_sorted:
            modelo = row["MODELO"]
            cantidad = row["STOCK_ESTIMADO"]
            total_general_est += cantidad
            if current_model is None:
                current_model = modelo
            if modelo != current_model:
                # total del modelo anterior
                estimado_con_totales.append({
                    "MODELO": current_model,
                    "DESCRIPCION": "",
                    "COLOR": "",
                    "TALLA": "TOTAL MODELO",
                    "STOCK_ESTIMADO": total_modelo
                })
                total_modelo = 0
                current_model = modelo
            total_modelo += cantidad
            estimado_con_totales.append(row)
        # total del último modelo
        if current_model is not None:
            estimado_con_totales.append({
                "MODELO": current_model,
                "DESCRIPCION": "",
                "COLOR": "",
                "TALLA": "TOTAL MODELO",
                "STOCK_ESTIMADO": total_modelo
            })
        # total general
        estimado_con_totales.append({
            "MODELO": "",
            "DESCRIPCION": "",
            "COLOR": "",
            "TALLA": "TOTAL GENERAL",
            "STOCK_ESTIMADO": total_general_est
        })
        self._export_csv("05_stock_estimado", estimado_con_totales, ["MODELO", "DESCRIPCION", "COLOR", "TALLA", "STOCK_ESTIMADO"])
        # Exportar informe de stock bajo
        low_stock_export = [item for item in estimado_export if item["STOCK_ESTIMADO"] < 10]
        self._export_csv("06_orden_corte_sugerida", low_stock_export, ["MODELO", "DESCRIPCION", "COLOR", "TALLA", "STOCK_ESTIMADO"])

    # # ------------------------------------------------------------------
    # # Importar albaranes desde Excel (con control de duplicados)
    # # ------------------------------------------------------------------
    def _importar_albaranes_excel(self) -> None:
        if pd is None:
            print("❌ La librería pandas no está disponible; no se puede importar.")
            return

        ruta = input("Ruta del Excel de albaranes servidos (dejar vacío para usar la predeterminada): ").strip()
        ruta = ruta or self.ALBARANES_EXCEL

        try:
            df = pd.read_excel(ruta, skiprows=25)
        except Exception as e:
            print(f"❌ Error leyendo el Excel: {e}")
            return

        columnas = ["CodigoArticulo", "DesTalla", "Total", "SuPedido", "FechaAlbaran", "NumeroAlbaran"]
        if not all(col in df.columns for col in columnas):
            print(f"❌ Faltan columnas necesarias en el Excel: {columnas}")
            return

        # 1) Ledger de salidas ya registradas: (modelo,talla,pedido,albaran) -> cantidad acumulada
        from collections import defaultdict
        ya_registrado = defaultdict(int)
        for s in self.inventory.historial_salidas:
            try:
                k = (
                    str(s.get("modelo","")).strip().upper(),
                    norm_talla(s.get("talla","")),
                    norm_codigo(s.get("pedido","")),
                    norm_codigo(s.get("albaran","")),
                )
                ya_registrado[k] += int(s.get("cantidad", 0) or 0)
            except Exception:
                continue  # tolerante a datos raros antiguos

        # 2) Pre-ensamblar líneas del Excel (normalizadas) y detectar posibles duplicados
        lineas = []
        duplicadas = []
        for _, fila in df.iterrows():
            modelo = str(fila["CodigoArticulo"]).strip().upper()
            talla = norm_talla(fila["DesTalla"])
            pedido = norm_codigo(fila["SuPedido"])
            albaran = norm_codigo(fila["NumeroAlbaran"])

            valor = fila["Total"]
            if pd.isna(valor):
                continue
            try:
                cantidad_excel = int(valor)
            except Exception:
                continue

            fecha = parse_fecha_excel(fila["FechaAlbaran"])
            k = (modelo, talla, pedido, albaran)
            qty_prev = ya_registrado.get(k, 0)

            lineas.append({
                "modelo": modelo,
                "talla": talla,
                "pedido": pedido,
                "albaran": albaran,
                "fecha": fecha,
                "cantidad_excel": cantidad_excel,
                "ya_prev": qty_prev,
            })
            if qty_prev > 0:
                duplicadas.append((k, cantidad_excel, qty_prev))

        # 3) Si hay duplicadas, preguntar cómo proceder
        modo = "d"  # por defecto, la opción más segura: descontar diferencias
        if duplicadas:
            print("\n⚠️ Se han detectado líneas que ya existen en el historial (mismo MODELO/TALLA/PEDIDO/ALBARÁN).")
            # Pequeño resumen
            preview = {}
            for (k, excel_qty, prev_qty) in duplicadas:
                preview[k] = preview.get(k, {"excel": 0, "prev": 0})
                preview[k]["excel"] += excel_qty
                preview[k]["prev"] += prev_qty
            print("Resumen claves duplicadas (excel vs ya registrado):")
            for (modelo, talla, pedido, albaran), tot in list(preview.items())[:10]:
                print(f" - {modelo} T{talla} | Pedido {pedido} | Alb {albaran} → Excel:{tot['excel']} / Ya:{tot['prev']}")
            if len(preview) > 10:
                print(f"   ... y {len(preview)-10} más")

            print("\nElige cómo tratar duplicados:")
            print("  i  = Ignorar líneas duplicadas (no registrar nada de esas claves)")
            print("  d  = Descontar solo la diferencia (Excel - Ya registrado)  ✅ recomendado")
            print("  t  = Procesar todo igualmente (puede duplicar salidas)")
            print("  c  = Cancelar importación")
            inp = input("Opción [d]: ").strip().lower()
            if inp in {"i","d","t","c"}:
                modo = inp
            else:
                modo = "d"

            if modo == "c":
                print("❌ Importación cancelada por el usuario.")
                return

        # 4) Procesar con el modo elegido
        nuevas_salidas = 0
        import_rows = []      # Log general de albaranes importados
        pedidos_servicios = []  # Log de pendientes servidos

        for L in lineas:
            modelo = L["modelo"]; talla = L["talla"]; pedido = L["pedido"]
            albaran = L["albaran"]; fecha = L["fecha"]
            qty_excel = int(L["cantidad_excel"])
            qty_prev = int(L["ya_prev"])

            # Ajustar cantidad según el modo
            if qty_prev > 0:
                if modo == "i":
                    continue
                elif modo == "d":
                    qty = max(0, qty_excel - qty_prev)
                    if qty == 0:
                        continue
                elif modo == "t":
                    qty = qty_excel
            else:
                qty = qty_excel

            # Resolver cliente (igual que antes): por pendiente coincidente o info_modelos
            cliente_pend = ""
            for p in self.prevision.pedidos:
                if (str(p.get("modelo","")).strip().upper() == modelo and
                    norm_talla(p.get("talla","")) == talla and
                    p.get("pedido","") == pedido):
                    cliente_pend = p.get("cliente","") or ""
                    if cliente_pend:
                        break
            cliente_info = self.prevision.info_modelos.get(modelo, {}).get("cliente", "")
            cliente_resuelto = cliente_pend or cliente_info or ""

            # Guardar copia de pedidos antes para calcular servido/restante
            pedidos_antes = list(self.prevision.pedidos)

            # Registrar salida final
            ok = self.inventory.register_exit(
                modelo, talla, qty, cliente=cliente_resuelto,
                pedido=pedido, albaran=albaran, fecha=fecha
            )
            if not ok:
                continue
            nuevas_salidas += 1

            # Calcular original/servido/restante usando la copia previa
            total_antes = sum(
                int(p.get("cantidad", 0) or 0)
                for p in pedidos_antes
                if str(p.get("modelo","")).strip().upper() == modelo
                and norm_talla(p.get("talla","")) == talla
                and (p.get("pedido","") or "") == pedido
            )
            total_despues = sum(
                int(p.get("cantidad", 0) or 0)
                for p in self.prevision.pedidos
                if str(p.get("modelo","")).strip().upper() == modelo
                and norm_talla(p.get("talla","")) == talla
                and (p.get("pedido","") or "") == pedido
            )
            cantidad_servida = min(int(qty), int(total_antes))
            restante = max(int(total_despues), 0)

            pedidos_servicios.append({
                "MODELO": modelo,
                "TALLA": talla,
                "PEDIDO": pedido,
                "CANTIDAD_ORIGINAL": int(total_antes),
                "CANTIDAD_SERVIDA": int(cantidad_servida),
                "RESTANTE": int(restante),
                "FECHA_ALBARAN": fecha,
                "NUMERO_ALBARAN": albaran,
            })
            import_rows.append({
                "FECHA": fecha,
                "MODELO": modelo,
                "TALLA": talla,
                "CANTIDAD": int(qty),
                "PEDIDO": pedido,
                "ALBARAN": albaran,
                "CLIENTE": cliente_resuelto,
            })

        print(f"✅ Importación completada: {nuevas_salidas} movimientos de albaranes procesados.")

        # CSV de albaranes importados (ajustados a la cantidad realmente aplicada)
        if import_rows:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            nombre_archivo = f"09_albaranes_importados_{timestamp}"
            campos = ["FECHA", "MODELO", "TALLA", "CANTIDAD", "PEDIDO", "ALBARAN", "CLIENTE"]
            self._export_csv(nombre_archivo, import_rows, campos)

        # CSV de pedidos servidos
        if pedidos_servicios:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            nombre_archivo = f"13_pedidos_servidos_{timestamp}"
            campos = ["MODELO", "TALLA", "PEDIDO", "CANTIDAD_ORIGINAL", "CANTIDAD_SERVIDA", "RESTANTE", "FECHA_ALBARAN", "NUMERO_ALBARAN"]
            self._export_csv(nombre_archivo, pedidos_servicios, campos)
            print(f"📦 Se han servido {len(pedidos_servicios)} pedidos pendientes y se ha generado un informe.")

    
    # ------------------------------------------------------------------
    # Importar pedidos pendientes desde Excel
    # ------------------------------------------------------------------
    def _importar_pedidos_excel(self) -> None:
        if pd is None:
            print("❌ La librería pandas no está disponible; no se puede importar.")
            return
        ruta = input(f"Ruta del Excel de pedidos pendientes (dejar vacío para usar la predeterminada): ")
        ruta = ruta or self.PEDIDOS_EXCEL
        try:
            df = pd.read_excel(ruta, skiprows=26)
        except Exception as e:
            print(f"❌ Error leyendo el Excel: {e}")
            return
        columnas = ["CodigoArticulo", "DesTalla", "UnidadesPendientes", "SuPedido", "FechaEntrega", "NumeroPedido"]
        if not all(col in df.columns for col in columnas):
            print(f"❌ El Excel no contiene todas las columnas necesarias: {columnas}")
            return
        ya_existentes = {
            (
                str(p.get("modelo", "")).strip().upper(),
                norm_talla(p.get("talla", "")),
                self.convertir_a_str_sin_decimal(p.get("pedido", "")).strip()
            )
            for p in self.prevision.pedidos
        }
        nuevos = 0
        duplicados = 0
        import_rows = []  # filas importadas para log
        for _, fila in df.iterrows():
            modelo = str(fila["CodigoArticulo"]).strip().upper()
            talla = norm_talla(fila["DesTalla"])
            pedido = norm_codigo(fila["SuPedido"])
            valor = fila["UnidadesPendientes"]
            if pd.isna(valor):
                continue
            try:
                cantidad = int(valor)
            except:
                continue
            fecha = parse_fecha_excel(fila["FechaEntrega"])
            numero_pedido = norm_codigo(fila["NumeroPedido"])
            clave = (modelo, talla, pedido)
            if clave in ya_existentes:
                duplicados += 1
                continue
            # Resolver cliente: por columna 'Cliente' (si existe) o por info_modelos
            tiene_cliente = "Cliente" in df.columns
            cliente_excel = ""
            if tiene_cliente and not pd.isna(fila["Cliente"]):
                cliente_excel = str(fila["Cliente"]).strip()

            cliente_info = self.prevision.info_modelos.get(modelo, {}).get("cliente", "")
            cliente_resuelto = cliente_excel or cliente_info or ""

            # Registrar pendiente con cliente resuelto
            self.prevision.register_pending(
                modelo, talla, cantidad, pedido,
                cliente=cliente_resuelto, fecha=fecha, numero_pedido=numero_pedido
            )
            ya_existentes.add(clave)
            nuevos += 1

            # Log: guardar el cliente real
            import_rows.append({
                "FECHA": fecha,
                "PEDIDO": pedido,
                "NUMERO_PEDIDO": numero_pedido,
                "MODELO": modelo,
                "TALLA": talla,
                "CANTIDAD": cantidad,
                "CLIENTE": cliente_resuelto
            })

        print(f"✅ Se han importado {nuevos} nuevos pedidos desde el Excel.")
        if duplicados:
            print(f"ℹ️ Se han ignorado {duplicados} registros duplicados.")
        # Exportar log de pedidos importados
        if import_rows:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            nombre_archivo = f"10_pedidos_importados_{timestamp}"
            campos = ["FECHA", "PEDIDO", "NUMERO_PEDIDO", "MODELO", "TALLA", "CANTIDAD", "CLIENTE"]
            self._export_csv(nombre_archivo, import_rows, campos)

    # ------------------------------------------------------------------
    # Backup y restauración
    # ------------------------------------------------------------------
    def _crear_backup_manual(self) -> None:
        """Crea una copia de seguridad de los JSON en la carpeta backups."""
        carpeta = os.path.join(os.path.dirname(self.ds_inventario.path), "backups")
        os.makedirs(carpeta, exist_ok=True)
        fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ruta_datos = os.path.join(carpeta, f"datos_almacen_{fecha}.json")
        ruta_prevision = os.path.join(carpeta, f"prevision_{fecha}.json")
        try:
            # Copiamos los ficheros
            with open(self.ds_inventario.path, "r", encoding="utf-8") as src, open(ruta_datos, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            with open(self.ds_prevision.path, "r", encoding="utf-8") as src, open(ruta_prevision, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            print(f"✅ Backup creado:\n - {ruta_datos}\n - {ruta_prevision}")
        except Exception as e:
            print(f"❌ Error creando backup: {e}")

    def _restaurar_backup(self) -> None:
        """Permite seleccionar un backup y restaurar uno de los dos ficheros."""
        carpeta = os.path.join(os.path.dirname(self.ds_inventario.path), "backups")
        if not os.path.exists(carpeta):
            print("❌ No hay backups disponibles.")
            return
        archivos = [f for f in os.listdir(carpeta) if f.endswith(".json")]
        if not archivos:
            print("❌ No hay archivos de backup en la carpeta.")
            return
        print("\nBackups disponibles:")
        enumerados = {}
        for i, archivo in enumerate(sorted(archivos), 1):
            print(f"{i}. {archivo}")
            enumerados[str(i)] = archivo
        seleccion = input("Selecciona número de archivo para restaurar (0 para cancelar): ")
        if seleccion == "0":
            print("❌ Cancelado.")
            return
        nombre = enumerados.get(seleccion)
        if not nombre:
            print("❌ Opción no válida.")
            return
        if "datos_almacen" in nombre:
            destino = self.ds_inventario.path
        elif "prevision" in nombre:
            destino = self.ds_prevision.path
        else:
            print("❌ Nombre de archivo no reconocido para restaurar.")
            return
        confirm = input(f"⚠️ Esto sobrescribirá {os.path.basename(destino)}. ¿Confirmas? (s/n): ").lower()
        if confirm == "s":
            origen = os.path.join(carpeta, nombre)
            try:
                with open(origen, "r", encoding="utf-8") as src, open(destino, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
                # Recargamos datos en memoria
                self.ds_inventario.data = self.ds_inventario.load()
                self.ds_prevision.data = self.ds_prevision.load()
                # Reinstanciar clases para sincronizar estructuras internas
                self.prevision = Prevision(self.ds_prevision)
                self.inventory = Inventory(self.ds_inventario, self.prevision)
                print(f"✅ Restaurado: {nombre}")
            except Exception as e:
                print(f"❌ Error restaurando backup: {e}")
        else:
            print("❌ Operación cancelada.")

    # Gestión de talleres
    def _menu_talleres(self) -> None:
        while True:
            print("\n--- Gestión de talleres ---")
            print("1. Listar talleres")
            print("2. Añadir taller")
            print("3. Editar taller")
            print("4. Eliminar taller")
            print("5. Volver")
            op = input("Elige una opción: ")
            if op == "1":
                talleres = self.workshops.list_all()
                if not talleres:
                    print("(sin talleres)")
                for t in talleres:
                    print(f"- {t.nombre} (contacto: {t.contacto or '—'})")
            elif op == "2":
                nombre = input("Nombre del taller: ")
                contacto = input("Contacto (opcional): ") or None
                self.workshops.add(nombre, contacto)
            elif op == "3":
                talleres_lista = self.workshops.list_all()
                if not talleres_lista:
                    print("(sin talleres)")
                    return
                talleres_nombres = [t.nombre for t in talleres_lista]
                nombre = prompt_select_name("Taller a editar (prefijo/número):", talleres_nombres, allow_empty=False)
                nuevo_nombre = input("Nuevo nombre (dejar vacío para no cambiar): ") or None
                nuevo_contacto = input("Nuevo contacto (dejar vacío para no cambiar): ") or None
                self.workshops.edit(nombre, nuevo_nombre or None, nuevo_contacto or None)
            elif op == "4":
                talleres_lista = self.workshops.list_all()
                if not talleres_lista:
                    print("(sin talleres)")
                    return
                talleres_nombres = [t.nombre for t in talleres_lista]
                nombre = prompt_select_name("Taller a eliminar (prefijo/número):", talleres_nombres, allow_empty=False)
                self.workshops.delete(nombre)
            elif op == "5":
                break
            else:
                print("❌ Opción no válida.")

    # Gestión de clientes
    def _menu_clientes(self) -> None:
        while True:
            print("\n--- Gestión de clientes ---")
            print("1. Listar clientes")
            print("2. Añadir cliente")
            print("3. Editar cliente")
            print("4. Eliminar cliente")
            print("5. Volver")
            op = input("Elige una opción: ")
            if op == "1":
                clientes = self.clients.list_all()
                if not clientes:
                    print("(sin clientes)")
                for c in clientes:
                    print(f"- {c.nombre} (contacto: {c.contacto or '—'})")
            elif op == "2":
                nombre = input("Nombre del cliente: ")
                contacto = input("Contacto (opcional): ") or None
                self.clients.add(nombre, contacto)
            elif op == "3":
                clientes_lista = self.clients.list_all()
                if not clientes_lista:
                    print("(sin clientes)")
                    return
                clientes_nombres = [c.nombre for c in clientes_lista]
                nombre = prompt_select_name("Cliente a editar (prefijo/número):", clientes_nombres, allow_empty=False)
                nuevo_nombre = input("Nuevo nombre (dejar vacío para no cambiar): ") or None
                nuevo_contacto = input("Nuevo contacto (dejar vacío para no cambiar): ") or None
                self.clients.edit(nombre, nuevo_nombre or None, nuevo_contacto or None)
            elif op == "4":
                clientes_lista = self.clients.list_all()
                if not clientes_lista:
                    print("(sin clientes)")
                    return
                clientes_nombres = [c.nombre for c in clientes_lista]
                nombre = prompt_select_name("Cliente a eliminar (prefijo/número):", clientes_nombres, allow_empty=False)
                self.clients.delete(nombre)
            elif op == "5":
                break
            else:
                print("❌ Opción no válida.")

    # ------------------------------------------------------------------
    # Modificación manual de stock
    # ------------------------------------------------------------------
    def _menu_modificar_stock(self) -> None:
        """Permite crear, modificar o eliminar artículos manualmente."""
        print("\n--- Modificación manual de stock ---")
        modelo = input("Modelo: ").upper()
        accion = input("¿Qué deseas hacer? [a=añadir/modificar stock, e=eliminar talla, u=actualizar datos del modelo]: ").lower()
        if accion not in ("a", "e", "u"):
            print("❌ Acción no reconocida.")
            return
        if accion == "u":
            # Actualizar datos del modelo (sin tocar stock)
            if modelo not in self.inventory.info_modelos:
                print(f"❌ El modelo {modelo} no existe.")
                return
            descripcion = input("Nueva descripción (dejar vacío para mantener): ") or None
            color = input("Nuevo color (dejar vacío para mantener): ") or None
            cambiar_cliente = input("¿Deseas cambiar el cliente? (s/n): ").lower()
            cliente = None
            if cambiar_cliente == "s":
                print("Clientes disponibles:")
                for c in self.clients.list_all():
                    print(f"- {c.nombre}")
                cliente = input("Nuevo cliente (nombre, dejar vacío para eliminar): ")
                # Permitimos cadena vacía como eliminación del cliente
            self.inventory.update_model_info(modelo, descripcion, color, cliente)
            return
        # Para las operaciones de stock necesitamos la talla
        talla = norm_talla(input("Talla: "))
        if accion == "e":
            # Eliminar talla (o modelo si queda vacío)
            self.inventory.modify_stock(modelo, talla, None)
            return
        # Añadir o modificar stock
        try:
            nuevo_valor = int(input("Nuevo stock para esa talla: "))
        except ValueError:
            print("❌ Valor no válido. Debe ser un número entero.")
            return
        # Datos del modelo si es nuevo
        if modelo not in self.inventory.info_modelos:
            print("Introduciendo datos para nuevo modelo...")
            descripcion = input("Descripción del modelo: ")
            color = input("Color del modelo: ")
            print("Clientes disponibles:")
            for c in self.clients.list_all():
                print(f"- {c.nombre}")
            cliente = input("Cliente (nombre, dejar vacío si no aplica): ") or None
        else:
            descripcion = None
            color = None
            actualizar_cliente = input("¿Deseas actualizar el cliente asignado? (s/n): ").lower()
            cliente = None
            if actualizar_cliente == "s":
                print("Clientes disponibles:")
                for c in self.clients.list_all():
                    print(f"- {c.nombre}")
                clientes_nombres = [c.nombre for c in self.clients.list_all()]
                cliente = prompt_select_name("Cliente (prefijo):", clientes_nombres, allow_empty=False) or None
        self.inventory.modify_stock(modelo, talla, nuevo_valor, descripcion, color, cliente)

    # ------------------------------------------------------------------
    # Modificación de cliente de un modelo
    # ------------------------------------------------------------------
    def _menu_modificar_cliente_modelo(self) -> None:
        """Permite asignar o cambiar el cliente asociado a un modelo."""
        print("\n--- Modificar cliente de un modelo ---")
        modelo = input("Modelo a actualizar: ").upper()
        if modelo not in self.inventory.info_modelos:
            print(f"❌ El modelo {modelo} no existe en el inventario.")
            crear = input("¿Deseas crearlo ahora? (s/n): ").lower()
            if crear != "s":
                return
            descripcion = input("Descripción del modelo: ")
            color = input("Color del modelo: ")
            clientes_lista = self.clients.list_all()
            if clientes_lista:
                clientes_nombres = [c.nombre for c in clientes_lista]
                cliente = prompt_select_name("Cliente (prefijo/número o Enter si no aplica):", clientes_nombres, allow_empty=True)
            else:
                print("ℹ️ No hay clientes dados de alta.")
                cliente = None
            # Crear el modelo con una talla vacía y 0 unidades
            talla = norm_talla(input("Talla inicial (ej. 34): "))
            try:
                cantidad = int(input("Cantidad inicial para esa talla: "))
            except ValueError:
                cantidad = 0
            self.inventory.modify_stock(modelo, talla, cantidad, descripcion, color, cliente)
            return
        # Modelo existente
        clientes_lista = self.clients.list_all()
        if clientes_lista:
            clientes_nombres = [c.nombre for c in clientes_lista]
            cliente = prompt_select_name("Nuevo cliente (prefijo/número o Enter para eliminar):", clientes_nombres, allow_empty=True)
        else:
            print("ℹ️ No hay clientes dados de alta.")
            cliente = ""
        # Actualizar info_modelos
        self.inventory.update_model_info(modelo, cliente=cliente)

    # ------------------------------------------------------------------
    # Renombrar un modelo/artículo
    # ------------------------------------------------------------------
    def _menu_renombrar_modelo(self) -> None:
        """Permite cambiar el identificador de un modelo en todas las estructuras."""
        print("\n--- Renombrar modelo/artículo ---")
        antiguo = input("Código actual del modelo: ").upper().strip()
        nuevo = input("Nuevo código de modelo: ").upper().strip()

        if not antiguo or not nuevo or nuevo == antiguo:
            print("❌ Código no válido o igual al actual.")
            return

        # Comprobar si el nuevo ya existe en alguna estructura principal
        existe_nuevo = (
            nuevo in self.inventory.almacen or
            nuevo in self.inventory.info_modelos or
            nuevo in self.prevision.info_modelos or
            nuevo in self.prevision.pedidos_fabricacion
        )
        if existe_nuevo:
            print(f"❌ El modelo {nuevo} ya existe. Elige otro código.")
            return

        # Comprobar si el antiguo existe en alguna estructura (no solo en almacen)
        existe_antiguo = (
            antiguo in self.inventory.almacen or
            antiguo in self.inventory.info_modelos or
            antiguo in self.prevision.info_modelos or
            antiguo in self.prevision.pedidos_fabricacion or
            any(e.get("modelo") == antiguo for e in self.inventory.historial_entradas) or
            any(s.get("modelo") == antiguo for s in self.inventory.historial_salidas) or
            any(o.get("modelo") == antiguo for o in self.prevision.ordenes) or
            any(p.get("modelo") == antiguo for p in self.prevision.pedidos)
        )
        if not existe_antiguo:
            print(f"❌ No se encuentra el modelo {antiguo} en los datos.")
            return

        # Asegurar contenedor en almacen para renombrar, aunque esté vacío
        if antiguo in self.inventory.almacen:
            self.inventory.almacen[nuevo] = self.inventory.almacen.pop(antiguo)
        else:
            self.inventory.almacen.setdefault(nuevo, {})

        # Renombrar en info_modelos (inventario y previsión)
        if antiguo in self.inventory.info_modelos:
            self.inventory.info_modelos[nuevo] = self.inventory.info_modelos.pop(antiguo)
        if antiguo in self.prevision.info_modelos:
            self.prevision.info_modelos[nuevo] = self.prevision.info_modelos.pop(antiguo)

        # Renombrar claves de pedidos_fabricacion
        if antiguo in self.prevision.pedidos_fabricacion:
            self.prevision.pedidos_fabricacion[nuevo] = self.prevision.pedidos_fabricacion.pop(antiguo)

        # Historiales
        for entrada in self.inventory.historial_entradas:
            if entrada.get("modelo") == antiguo:
                entrada["modelo"] = nuevo
        for salida in self.inventory.historial_salidas:
            if salida.get("modelo") == antiguo:
                salida["modelo"] = nuevo

        # Ordenes antiguas (si aún quedan) y pedidos pendientes
        for orden in self.prevision.ordenes:
            if orden.get("modelo") == antiguo:
                orden["modelo"] = nuevo
        for pedido in self.prevision.pedidos:
            if pedido.get("modelo") == antiguo:
                pedido["modelo"] = nuevo

        # Guardar
        self.inventory.save()
        self.prevision.save()
        print(f"✅ Modelo {antiguo} renombrado como {nuevo} en todas las estructuras.")



if __name__ == "__main__":
    gestor = GestorStock()
    gestor.run()