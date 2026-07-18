import json
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

base = r'C:\Users\jordi\AppData\Roaming\Code\User\workspaceStorage'
results = []

for ws_id in os.listdir(base):
    chat_dir = os.path.join(base, ws_id, 'chatSessions')
    if not os.path.isdir(chat_dir):
        continue
    
    # Lire workspace.json pour avoir le nom du projet
    ws_json = os.path.join(base, ws_id, 'workspace.json')
    ws_name = ws_id[:12]
    if os.path.exists(ws_json):
        try:
            with open(ws_json, 'r', encoding='utf-8') as f:
                wdata = json.load(f)
            folder = wdata.get('folder', wdata.get('folders', ['?'])[0] if isinstance(wdata.get('folders'), list) else '?')
            ws_name = folder.replace('file:///', '').replace('%3A', ':').split('/')[-1]
        except:
            pass
    
    for fname in os.listdir(chat_dir):
        if not fname.endswith('.jsonl'):
            continue
        fpath = os.path.join(chat_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                first_line = f.readline()
            obj = json.loads(first_line)
            ts = obj.get('v', {}).get('creationDate', 0)
            if ts:
                dt = datetime.fromtimestamp(ts / 1000)
                size = os.path.getsize(fpath)
                results.append((dt, ws_name, fname[:20], size, fpath))
        except:
            pass

results.sort()

print("=== TOUTES LES SESSIONS CHAT ===\n")
for dt, ws, fname, size, fpath in results:
    marker = " <<< 6 JUILLET" if dt.date().isoformat() == '2026-07-06' else ""
    print(f"{dt.strftime('%Y-%m-%d %H:%M')} | {ws:<30} | {size:>8} octets{marker}")

print(f"\nTotal: {len(results)} sessions")

# Focus sur 6 juillet
print("\n=== SESSIONS DU 6 JUILLET 2026 ===")
for dt, ws, fname, size, fpath in results:
    if dt.date().isoformat() == '2026-07-06':
        print(f"\n  {dt.strftime('%H:%M:%S')} | {ws} | {size} octets")
        print(f"  Fichier: {fpath}")
