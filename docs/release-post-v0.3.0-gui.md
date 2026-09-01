# PEROVOWL DFT Monitor 0.3.0

Este release deja lista la interfaz grafica del monitor DFT para distribucion:

- **Windows GUI**: `dft-monitor-desktop-0.3.0-windows-x64.zip`
- **Linux Debian/Ubuntu GUI**: `perovowl-dft-monitor-0.3.0-linux-amd64.deb`
- **Linux portable GUI**: `dft-monitor-desktop-0.3.0-linux-x86_64.tar.gz`
- **Linux web/servidor**: `dft-monitor-web-0.3.0-linux-x86_64.tar.gz`

La aplicacion de escritorio incluye el motor local congelado y los recursos del
monitor, por lo que no requiere instalar Python, Node, Flutter ni clonar el
repositorio para uso normal.

## Descargar

Ve a:

<https://github.com/RxWhizz/PEROVOWL/releases/tag/v0.3.0>

Abre la seccion **Assets** y descarga el archivo correspondiente a tu sistema.
Para verificar integridad, descarga tambien `SHA256SUMS-gui-deliverables.txt`
o `SHA256SUMS`.

## Windows

1. Descarga `dft-monitor-desktop-0.3.0-windows-x64.zip`.
2. Descomprime el archivo.
3. Ejecuta la aplicacion:

```powershell
Expand-Archive .\dft-monitor-desktop-0.3.0-windows-x64.zip
.\dft-monitor-desktop-0.3.0-windows-x64\dft_monitor_flutter.exe
```

## Debian/Ubuntu

1. Descarga `perovowl-dft-monitor-0.3.0-linux-amd64.deb`.
2. Instalalo.
3. Abre la aplicacion desde el menu o desde terminal:

```bash
sudo apt install ./perovowl-dft-monitor-0.3.0-linux-amd64.deb
perovowl-dft-monitor
```

## Linux portable

```bash
tar xzf dft-monitor-desktop-0.3.0-linux-x86_64.tar.gz
./dft-monitor-desktop-0.3.0-linux-x86_64/dft_monitor_flutter
```

## Linux web/servidor

```bash
tar xzf dft-monitor-web-0.3.0-linux-x86_64.tar.gz
./dft-monitor-web/dft-monitor-web --data-root /ruta/a/tus/datos
```

La interfaz abre en `http://127.0.0.1:8000`. Para acceso en red, usa
`--host 0.0.0.0` y configura un token en `monitor.auth.token`.

## Verificacion

Windows:

```powershell
Get-FileHash .\dft-monitor-desktop-0.3.0-windows-x64.zip -Algorithm SHA256
Get-FileHash .\perovowl-dft-monitor-0.3.0-linux-amd64.deb -Algorithm SHA256
```

Linux:

```bash
sha256sum -c SHA256SUMS
sha256sum -c SHA256SUMS-gui-deliverables.txt
```
