# Contribuir

## Flujo de trabajo
1. Crea rama desde `main`:
2. Commits pequeños y claros.
3. Abre Pull Request hacia `main` (usa la plantilla).
4. Merge por PR (no push directo a `main`).
5. Tag cuando haya hito:

## Convención de commits
- `feat:` nueva funcionalidad
- `fix:` corrección de bug
- `chore:` tareas de mantenimiento
- `docs:` docs/README/plantillas
- `refactor:` cambios internos sin funcionalidad nueva

## Estándares
- `.gitignore` mantiene fuera `last_update.json`, CSV/Excel, `__pycache__/`, `.vscode/`
- `.gitattributes` normaliza EOL (LF para Python/JSON/SH, CRLF para `.bat`)

## QA rápido antes del PR
- Ejecuta la app y verifica:
- Importar albaranes/pedidos (simular y real)
- Entradas/Salidas
- Restaurar backup
- Exportaciones
- Banner “Última actualización” actualizado
