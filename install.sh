#!/usr/bin/env bash
# Restores the desktop look from files/ on Arch + XFCE 4.20.
# Usage: ./install.sh [--panel] [--boot]
#   --panel  also replaces the whole panel layout
#   --boot   also installs the GRUB theme and Plymouth splash (systemd initramfs, GRUB)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
F="$HERE/files"
command -v pacman >/dev/null && command -v xfconf-query >/dev/null || { echo "needs Arch + XFCE"; exit 1; }
# files/ stores home paths as @HOME@, render them for this user first
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cp -a "$HERE/files" "$T/" && F="$T/files"
grep -rIl '@HOME@' "$F" | xargs -r sed -i "s|@HOME@|$HOME|g"

echo "==> packages"
sudo pacman -S --needed --noconfirm picom rofi starship xsecurelock mpv inter-font \
  ttf-jetbrains-mono-nerd papirus-icon-theme xfce4-docklike-plugin python-pillow xdotool plymouth \
  touchegg rofi-emoji rofi-calc playerctl wmctrl clipmenu xfce4-genmon-plugin xclip python-gobject
pacman -Q bibata-cursor-theme-bin >/dev/null 2>&1 || pacman -Q bibata-cursor-theme >/dev/null 2>&1 || \
  echo "!! install bibata-cursor-theme-bin from AUR for the cursor"

echo "==> backup to ~/.config/desktop-look-backup-$(date +%Y%m%d-%H%M%S)"
BK="$HOME/.config/desktop-look-backup-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$BK"
(cd "$F/config" && find . -type f) | while read -r f; do
  [ -e "$HOME/.config/$f" ] && mkdir -p "$BK/$(dirname "$f")" && cp -a "$HOME/.config/$f" "$BK/$f"; done
for c in xfwm4 xsettings xfce4-terminal xfce4-panel xfce4-notifyd xfce4-keyboard-shortcuts; do
  xfconf-query -c "$c" -lv > "$BK/$c.dump" 2>/dev/null; done

echo "==> files"
cp -a "$F/config/." "$HOME/.config/"
mkdir -p "$HOME/.themes" "$HOME/.icons/default" "$HOME/.local/bin" "$HOME/Pictures/Wallpapers"
tar -C "$HOME/.themes" -xzf "$F/themes/themes.tar.gz"
cp -a "$F/themes/cursor-index.theme" "$HOME/.icons/default/index.theme"
cp -a "$F/bin/." "$HOME/.local/bin/"
cp -a "$F/wallpapers/." "$HOME/Pictures/Wallpapers/"
mkdir -p "$HOME/.local/share/desktop-look" && cp -a "$F/share/." "$HOME/.local/share/desktop-look/"
mkdir -p "$HOME/.local/share/icons" && cp -a "$F/icons/." "$HOME/.local/share/icons/"
if [ ! -d "$HOME/.icons/Qogir-Dark" ] && [ ! -d /usr/share/icons/Qogir-Dark ]; then
  echo "==> Qogir icons (github)"
  T=$(mktemp -d) && git clone -q --depth 1 https://github.com/vinceliuice/Qogir-icon-theme "$T/q" && \
    (cd "$T/q" && ./install.sh -d "$HOME/.icons" >/dev/null) ; rm -rf "$T"
fi
fc-cache -f >/dev/null

echo "==> xfconf"
while IFS='|' read -r ch p v; do
  [ -z "$ch" ] && continue
  xfconf-query -c "$ch" -p "$p" -s "$v" 2>/dev/null && continue
  case "$v" in true|false) t=bool;; ''|*[!0-9]*) t=string;; *) t=int;; esac
  xfconf-query -c "$ch" -p "$p" -n -t "$t" -s "$v"
done < "$F/xfconf/settings.txt"
for k in $(xfconf-query -c xfce4-desktop -l | grep last-image); do
  xfconf-query -c xfce4-desktop -p "$k" -s "$HOME/Pictures/Wallpapers/black-sand-beach.jpg"; done

echo "==> workspaces, gestures, clipboard history"
xfconf-query -c xfwm4 -p /general/workspace_count -s 3
xfconf-query -c xfwm4 -p /general/workspace_names -n -t string -t string -t string -s Praca -s Nauka -s Prywatne 2>/dev/null || \
  xfconf-query -c xfwm4 -p /general/workspace_names -t string -t string -t string -s Praca -s Nauka -s Prywatne
sudo systemctl enable --now touchegg.service
systemctl --user daemon-reload && systemctl --user enable --now clipmenud.service

echo "==> login screen + lock background"
sudo install -D -m 644 "$F/system/login-bg.png" /usr/share/backgrounds/radek/login-bg.png
sudo cp "$F/system/lightdm-gtk-greeter.conf" /etc/lightdm/lightdm-gtk-greeter.conf
"$HOME/.local/bin/lock-bg-make" >/dev/null
xfconf-query -c xfce4-keyboard-shortcuts -p '/xfwm4/custom/<Super>Tab' -r 2>/dev/null
command -v skippy-xd >/dev/null || echo "!! install skippy-xd-git from AUR for the Super+Tab overview"

if [ "${1:-}" = "--boot" ] || [ "${2:-}" = "--boot" ]; then
  echo "==> GRUB theme + Plymouth splash (keeps a fallback initramfs without it)"
  sudo cp /boot/initramfs-linux.img /boot/initramfs-linux-fallback.img
  sudo mkdir -p /boot/grub/themes && sudo tar -C /boot/grub/themes -xzf "$F/system/grub-theme.tar.gz"
  grep -q 'plymouth' /etc/mkinitcpio.conf || sudo sed -i 's/^HOOKS=(base systemd /HOOKS=(base systemd plymouth /' /etc/mkinitcpio.conf
  grep -q 'splash' /etc/default/grub || sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\) quiet /GRUB_CMDLINE_LINUX_DEFAULT="\1 quiet splash /' /etc/default/grub
  sudo sed -i '/^GRUB_THEME=/d' /etc/default/grub
  echo 'GRUB_THEME="/boot/grub/themes/tokyo-night-radek/theme.txt"' | sudo tee -a /etc/default/grub >/dev/null
  sudo plymouth-set-default-theme bgrt && sudo mkinitcpio -P && sudo grub-mkconfig -o /boot/grub/grub.cfg
fi

if [ "${1:-}" = "--panel" ]; then
  echo "==> panel layout"
  xfce4-panel -q; sleep 1
  cp "$F/xfconf/xfce4-panel.xml" "$HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
  setsid xfce4-panel >/dev/null 2>&1 &
else
  xfce4-panel -r
fi

echo "==> compositor"
pkill -x picom; sleep 1; setsid picom --config "$HOME/.config/picom/picom.conf" >/dev/null 2>&1 < /dev/null &

echo "==> calendar popup, screenshot daemon"
pkill -f '^python3 [^ ]*desktop-look/calendar.py'; sleep 0.5
setsid "$HOME/.local/bin/calendar-popup" --daemon >/dev/null 2>&1 < /dev/null &
if pgrep -x flameshot >/dev/null; then pkill -x flameshot; sleep 1; setsid flameshot >/dev/null 2>&1 < /dev/null & fi

if [ -x "$HOME/Applications/Handy.AppImage" ]; then
  "$HOME/.local/bin/handy-mono-tray"
  d="$HOME/.local/share/applications/handy.desktop"
  [ -f "$d" ] && sed -i "s|^Exec=.*|Exec=$HOME/Applications/Handy-app/AppRun|" "$d"
  # Handy's own autostart rewrites Exec to usr/bin/handy, which crashes outside AppRun
  S="$HOME/.local/share/com.pais.handy/settings_store.json"
  [ -f "$S" ] && sed -i 's/"autostart_enabled": *true/"autostart_enabled": false/' "$S"
  rm -f "$HOME/.config/autostart/Handy.desktop"
  printf '[Desktop Entry]\nType=Application\nName=Handy\nExec=%s\nStartupNotify=false\nTerminal=false\n' \
    "$HOME/Applications/Handy-app/AppRun" > "$HOME/.config/autostart/handy-apprun.desktop"
fi
echo "done. Log out and back in once so every app picks up fonts, cursor and the thunar style."
echo "backup: $BK"
