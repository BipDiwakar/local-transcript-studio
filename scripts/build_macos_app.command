#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="Local Transcript Studio.app"
APP_DIR="$BUILD_DIR/$APP_NAME"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
APP_RESOURCES="$RESOURCES_DIR/app"
INSTALL_DIR="$HOME/Applications"
SUPPORT_DIR="$HOME/Library/Application Support/Local Transcript Studio"
RUNTIME_DIR="$SUPPORT_DIR/runtime"

cd "$ROOT_DIR"

if [ ! -x ".venv/bin/python" ] && [ ! -x "$RUNTIME_DIR/bin/python" ]; then
  echo "Missing Python runtime. Run ./launch_desktop_app.command once first."
  exit 1
fi

rm -rf "$BUILD_DIR" "$DIST_DIR" "$ROOT_DIR/$APP_NAME"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_RESOURCES" "$INSTALL_DIR" "$SUPPORT_DIR"

if [ ! -x "$RUNTIME_DIR/bin/python" ]; then
  cp -cR "$ROOT_DIR/.venv" "$RUNTIME_DIR"
fi

clang mac_launcher.c -o "$APP_DIR/Contents/MacOS/LocalTranscriptStudio"
chmod +x "$APP_DIR/Contents/MacOS/LocalTranscriptStudio"

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>Local Transcript Studio</string>
  <key>CFBundleDisplayName</key>
  <string>Local Transcript Studio</string>
  <key>CFBundleIdentifier</key>
  <string>local.transcript.studio</string>
  <key>CFBundleVersion</key>
  <string>1.2</string>
  <key>CFBundleShortVersionString</key>
  <string>1.2</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleExecutable</key>
  <string>LocalTranscriptStudio</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

rsync -a --delete app.py desktop_launcher.py requirements.txt README.md transcribe_local .streamlit assets "$APP_RESOURCES/"
cp assets/AppIcon.icns "$APP_DIR/Contents/Resources/AppIcon.icns"

cat > "$RESOURCES_DIR/launch_app.command" <<'LAUNCH'
#!/bin/zsh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/app" && pwd)"
SUPPORT_DIR="$HOME/Library/Application Support/Local Transcript Studio"
RUNTIME_DIR="$SUPPORT_DIR/runtime"
PYTHON="$RUNTIME_DIR/bin/python"
cd "$APP_DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export BROWSER="none"

if [ ! -x "$PYTHON" ]; then
  mkdir -p "$SUPPORT_DIR"
  /opt/homebrew/bin/python3.12 -m venv "$RUNTIME_DIR"
  "$PYTHON" -m pip install -r requirements.txt
fi

exec "$PYTHON" desktop_launcher.py
LAUNCH
chmod +x "$RESOURCES_DIR/launch_app.command"

rm -rf "$INSTALL_DIR/$APP_NAME"
cp -R "$APP_DIR" "$INSTALL_DIR/$APP_NAME"

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$INSTALL_DIR/$APP_NAME"
fi

rm -rf "$BUILD_DIR"
echo "Installed: $INSTALL_DIR/$APP_NAME"
echo "Shared runtime: $RUNTIME_DIR"
