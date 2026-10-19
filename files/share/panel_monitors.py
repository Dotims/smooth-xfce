#!/usr/bin/env python3
# Pins the main panel to the primary monitor and adds a smaller copy (menu, dock, clock) on every
# other monitor. Usage: panel_monitors.py <xfce4-panel.xml> <panel plugin rc dir>
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

# plugins of the main panel repeated on the other monitors
COPY = ['1', '15', '2', '3', '8', '20']


def monitors():
    out = subprocess.run(['xrandr', '--listmonitors'], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines()[1:]:
        m = re.search(r'(\*?)(\d+)/\d+x(\d+)/\d+\+(\d+)\+(\d+)\s+(\S+)$', line.split(':', 1)[1])
        if m:
            found.append((m.group(1) == '*', m.group(6), *map(int, m.group(2, 3, 4, 5))))
    return sorted(found, key=lambda x: not x[0])  # primary first


def prop(parent, name, typ, value=None):
    p = ET.SubElement(parent, 'property', name=name, type=typ)
    if value is not None:
        p.set('value', str(value))
    return p


def main(path, rcdir):
    mons = monitors()
    tree = ET.parse(path)
    root = tree.getroot()
    panels = root.find("property[@name='panels']")
    plugins = root.find("property[@name='plugins']")
    main_panel = panels.find("property[@name='panel-1']")
    prop(main_panel, 'output-name', 'string', mons[0][1])
    if len(mons) < 2:
        tree.write(path, encoding='UTF-8', xml_declaration=True)
        return
    by_id = {p.get('name').split('-')[1]: p for p in plugins.findall('property')
             if p.get('name', '').startswith('plugin-')}
    next_id = max(map(int, by_id)) + 1
    rc = open(f'{rcdir}/docklike-2.rc').read().replace('onlyDisplayScreen=false', 'onlyDisplayScreen=true')
    open(f'{rcdir}/docklike-2.rc', 'w').write(rc)
    for n, (_, name, w, h, x, y) in enumerate(mons[1:], start=2):
        ET.SubElement(panels, 'value', type='int', value=str(n))
        panel = ET.fromstring(ET.tostring(main_panel))
        panel.set('name', f'panel-{n}')
        for p in panel.findall('property'):
            if p.get('name') in ('plugin-ids', 'output-name', 'position'):
                panel.remove(p)
        prop(panel, 'output-name', 'string', name)
        prop(panel, 'position', 'string', f'p=8;x={x + w // 2};y={y + h - 20}')
        ids = prop(panel, 'plugin-ids', 'array')
        for old in COPY:
            ET.SubElement(ids, 'value', type='int', value=str(next_id))
            plugin = ET.fromstring(ET.tostring(by_id[old]))
            plugin.set('name', f'plugin-{next_id}')
            plugins.append(plugin)
            if old == '2':
                open(f'{rcdir}/docklike-{next_id}.rc', 'w').write(rc)
            next_id += 1
        panels.append(panel)
    # array values must come before the panel-N properties
    values = [c for c in panels if c.tag == 'value']
    for c in values:
        panels.remove(c)
    for i, c in enumerate(values):
        panels.insert(i, c)
    ET.indent(tree, '  ')
    tree.write(path, encoding='UTF-8', xml_declaration=True)


if __name__ == '__main__':
    main(*sys.argv[1:3])
