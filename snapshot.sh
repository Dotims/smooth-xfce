#!/usr/bin/env bash
# Copies the current desktop look from this machine into files/. Run after any tweak, then commit.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
F="$HERE/files"
rm -rf "$F" && mkdir -p "$F"/{config,themes,bin,xfconf,wallpapers,system,icons,libexec}

cp_rel() { mkdir -p "$F/config/$(dirname "$1")"; cp -a "$HOME/.config/$1" "$F/config/$1"; }
cp_rel gtk-3.0/gtk.css
cp_rel picom/picom.conf
cp_rel autostart/picom.desktop
cp_rel rofi/config.rasi
cp_rel rofi/spotlight.rasi
cp_rel starship.toml
cp_rel fontconfig/fonts.conf
cp_rel xfce4/panel/docklike-2.rc
cp_rel skippy-xd/skippy-xd.rc
cp_rel touchegg/touchegg.conf
cp_rel autostart/pinch-zoom.desktop
cp_rel systemd/user/clipmenud.service.d/override.conf
cp_rel autostart/skippy-xd.desktop
cp_rel autostart/calendar-popup.desktop
cp_rel autostart/quick-settings.desktop
cp_rel autostart/nm-applet.desktop
cp_rel autostart/blueman.desktop
cp_rel fastfetch/config.jsonc
cp_rel btop/btop.conf
cp_rel flameshot/flameshot.ini

tar -C "$HOME/.themes" -czf "$F/themes/themes.tar.gz" Qogir-Dark Qogir-Dark-Night Night-Glass
cp -a "$HOME/.icons/default/index.theme" "$F/themes/cursor-index.theme"

for b in lock-now lock-saver lock-bg-make handy-mono-tray ws grid-windows clipboard-menu rofi-power now-playing cheatsheet calendar-popup quick-settings status-icons volume after-tray; do cp -a "$HOME/.local/bin/$b" "$F/bin/"; done
cp -a "$HOME"/Pictures/Wallpapers/* "$F/wallpapers/"
mkdir -p "$F/share" && cp -a "$HOME"/.local/share/desktop-look/*.py "$HOME"/.local/share/desktop-look/blank.png "$F/share/"
cp -a "$HOME/.local/src/pinch-zoom/pinch-zoom.c" "$F/share/"
cp -a "$HOME/.local/share/icons/arch-menu.svg" "$F/icons/"
cp -a "$HOME/.local/libexec/xsecurelock" "$F/libexec/"
cp -a /etc/lightdm/lightdm-gtk-greeter.conf "$F/system/"
cp -a /usr/share/backgrounds/radek/login-bg.png "$F/system/"
tar -C /boot/grub/themes -czf "$F/system/grub-theme.tar.gz" tokyo-night-radek

# xfconf values that make up the look (property list keeps it reviewable in git)
dump() { xfconf-query -c "$1" -p "$2" 2>/dev/null; }
{
  for p in /general/theme /general/use_compositing /general/cycle_hidden /general/title_font /general/button_layout; do
    echo "xfwm4|$p|$(dump xfwm4 $p)"; done
  for p in /Net/ThemeName /Net/IconThemeName /Gtk/CursorThemeName /Gtk/CursorThemeSize /Gtk/FontName /Gtk/MonospaceFontName /Xft/HintStyle /Xft/RGBA; do
    echo "xsettings|$p|$(dump xsettings $p)"; done
  for p in $(xfconf-query -c xfce4-terminal -l); do echo "xfce4-terminal|$p|$(dump xfce4-terminal $p)"; done
  echo "xfce4-panel|/plugins/plugin-1/button-icon|$(dump xfce4-panel /plugins/plugin-1/button-icon)"
  for p in $(xfconf-query -c xfce4-panel -l | grep '^/plugins/plugin-8/'); do echo "xfce4-panel|$p|$(dump xfce4-panel $p)"; done
  echo "xfce4-notifyd|/theme|$(dump xfce4-notifyd /theme)"
  echo "xfce4-keyboard-shortcuts|/commands/custom/<Super>space|$(dump xfce4-keyboard-shortcuts '/commands/custom/<Super>space')"
  # every custom shortcut (commands + window manager), so new ones travel too
  xfconf-query -c xfce4-keyboard-shortcuts -l | grep -E '^/(commands|xfwm4)/custom/' | while read -r k; do
    echo "xfce4-keyboard-shortcuts|$k|$(dump xfce4-keyboard-shortcuts "$k")"; done
  for p in /plugins/plugin-16/enable-mpris /plugins/plugin-16/enable-multimedia-keys; do
    echo "xfce4-panel|$p|$(dump xfce4-panel $p)"; done
} > "$F/xfconf/settings.txt"
# full panel layout (plugins + order), only applied with install.sh --panel
cp -a "$HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml" "$F/xfconf/xfce4-panel.xml"
# drop caches that leak Wi-Fi names and recently used apps
python3 - "$F/xfconf/xfce4-panel.xml" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
s = re.sub(r'\n\s*<property name="(known-items|known-legacy-items|recent)" type="array">.*?</property>', '', s, flags=re.S)
open(p, 'w').write(s)
PY
# home paths become @HOME@; install.sh puts the real one back
grep -rIl "$HOME" "$F" | xargs -r sed -i "s|$HOME|@HOME@|g"
echo "snapshot ok: $F"
