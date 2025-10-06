# Gestor de Uniformes (Streamlit)

[![Version](https://img.shields.io/badge/version-v1.1.0-black)](../../releases)
[![Python](https://img.shields.io/badge/python-3.13+-black)](#)
[![Streamlit](https://img.shields.io/badge/streamlit-app-black)](#)

Gestor de stock y previsión para uniformidad (entradas, salidas, pendientes, importación de albaranes/pedidos, backups y exportaciones).

## Quick Start

```bash
# 1) Crear/activar entorno
conda create -n gestor_env python=3.13 -y
conda activate gestor_env
pip install streamlit pandas openpyxl

# 2) Ejecutar
streamlit run st_app_final.py


Características

Movimientos (Entradas/Salidas) con histórico

Importar albaranes servidos y pedidos pendientes (xlsx)

Pendientes y órdenes de fabricación

Backups y restauración

Exportaciones CSV

Banner “Última actualización” en cabecera (persistente)

Contribución

Lee CONTRIBUTING.md
 y usa Pull Requests (plantilla en .github/pull_request_template.md).

Licencia

Uso interno.
