# launch.py — abre SOLO la URL correcta (8501..)
import os, sys, time, socket, webbrowser
from streamlit.web import bootstrap

BASE = os.path.dirname(os.path.abspath(sys.argv[0]))
os.chdir(BASE)

# Desactivar auto-open y watcher
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
os.environ["BROWSER"] = "none"

SCRIPT = os.path.join(BASE, "st_app_final.py")

def port_free(p: int) -> bool:
    s = socket.socket(); s.settimeout(0.2)
    ok = s.connect_ex(("127.0.0.1", p)) != 0
    s.close(); return ok

PORT = next(p for p in range(8501, 8600) if port_free(p))

bootstrap.run(
    SCRIPT,
    "", [],  # cmd name, argv
    flag_options={
        "server.port": PORT,
        "server.headless": True,
        "server.address": "127.0.0.1",   # fuerza loopback
    },
)

# Espera a que el backend (8501) esté arriba
for _ in range(120):  # ~24s
    if not port_free(PORT):
        break
    time.sleep(0.25)

url = f"http://127.0.0.1:{PORT}"
if port_free(PORT):
    input(f"[ERROR] Streamlit no arrancó. Abre {url} manualmente o revisa el firewall. ENTER para salir…")
    sys.exit(1)

webbrowser.open(url)
print(f"[OK] Abierto {url}. Ctrl+C para cerrar.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
