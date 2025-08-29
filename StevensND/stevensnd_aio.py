#!/usr/bin/env python3
"""
All-in-one processor for StevensND's switch-port-mods repo.
Downloads, extracts, and formats pchtxt files with proper naming and title ID flags.
"""
import os, re, sys, shutil, unicodedata, urllib.request, zipfile

# ---------------- Config ----------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------- Helpers (naming/title) ----------------
def sanitize_name(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    for ch in ("'", "'", "`", '"'):
        n = n.replace(ch, "")
    n = n.replace(" - ", " ")
    # replace any case of "Bros. " with "Bros " (case-insensitive)
    n = re.sub(r'\bBros\.\s', 'Bros ', n, flags=re.IGNORECASE)
    return " ".join(n.split()).strip()

def capitalize_hyphenated(word):
    parts = word.split("-")
    out = []
    for p in parts:
        if not p:
            out.append("")
        elif len(p) == 1:
            out.append(p.upper())
        else:
            out.append(p[0].upper() + p[1:].lower())
    return "-".join(out)

ROMAN_NUMERAL_PATTERN = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", re.IGNORECASE)
ACRONYMS = {"HD","2D","3D","4K","VR","AI","API","USB","CPU","GPU","DVD","CD",
            "RPG","FPS","MMO","MMORPG","LAN","GUI","NPC",
            "FFVII","FFVIII","FFIX","FFX","FFXII","FX","2K","5K","8K","V1","V2","V3","V4","DOF"}

def is_roman_numeral(w): return bool(ROMAN_NUMERAL_PATTERN.match(w))

def title_case_preserve_numbers(name):
    lowercase_exceptions = {"a","an","and","as","at","but","by","for","from","in","nor","of","on","or","so","the","to","with","yet"}
    subtitle_markers = {":","~","-","–","—"}
    words = name.split()
    result = []
    force_cap = False
    for idx, word in enumerate(words):
        contains_marker = any(m in word for m in subtitle_markers)
        parts = re.split(r'([:~\-–—])', word)
        out_parts = []
        for part in parts:
            if part in subtitle_markers:
                out_parts.append(part)
                force_cap = True
                continue
            lp = part.lower()
            is_first = idx == 0
            is_last = idx == len(words) - 1
            def cap_special(w):
                if w.upper() in ACRONYMS: return w.upper()
                if is_roman_numeral(w): return w.upper()
                for sep in ('&','+','|'):
                    if sep in w:
                        sub = w.split(sep)
                        if all(is_roman_numeral(x) for x in sub):
                            return sep.join(x.upper() for x in sub)
                return capitalize_hyphenated(w)
            if force_cap or is_first or is_last or (lp not in lowercase_exceptions):
                out_parts.append('-'.join(cap_special(sp) for sp in part.split('-')))
            else:
                out_parts.append(lp)
        result.append(''.join(out_parts))
        if not contains_marker:
            force_cap = False
    if result:
        result[0] = '-'.join(sp.upper() if (sp.upper() in ACRONYMS or is_roman_numeral(sp)) else capitalize_hyphenated(sp) for sp in result[0].split('-'))
        result[-1] = '-'.join(sp.upper() if (sp.upper() in ACRONYMS or is_roman_numeral(sp)) else capitalize_hyphenated(sp) for sp in result[-1].split('-'))
    return ' '.join(result)

def clean_title(name):
    return title_case_preserve_numbers(sanitize_name(name))

# ---------------- StevensND specific processing ----------------
def strip_versions(text):
    """
    Remove any substrings that look like version numbers, e.g.:
      - 1.0, 1.2.3
      - v1.0, v2.3.4
    """
    return re.sub(r'\b(v?\d+(?:\.\d+){1,2})\b', '', text, flags=re.IGNORECASE).strip()

def get_game_name_and_mod_name(path, root_dir):
    relative_path = os.path.relpath(path, root_dir)
    parts = relative_path.split(os.sep)

    raw_game = parts[0]
    raw_game = re.sub(r'\[.*?\]', '', raw_game).strip()
    if ", The" in raw_game:
        p = raw_game.split(", The")
        raw_game = f"The {p[0]}{p[1]}"
    raw_game = raw_game.replace(" - ", " ")

    country = None
    for p in parts[1:]:
        if re.search(r'\[.*?\]', p):
            country = re.sub(r'\[.*?\]', '', p).strip()
            break
    if country:
        raw_game = f"{raw_game} ({country})"
    game_name = clean_title(raw_game)

    sub_folders = [re.sub(r'\[.*?\]', '', p).strip() for p in parts[1:]]
    sub_folders = [sf for sf in sub_folders if sf.lower() != "pchtxt"]

    if "Aspect Ratio" in relative_path:
        aspect_folder = os.path.basename(path)
        raw_mod = f"Aspect Ratio {aspect_folder}"
    else:
        if sub_folders:
            m = re.match(r'^([0-9]+(?:\.[0-9]+)*)\s*(.*)$', sub_folders[0])
            if m:
                trailing = m.group(2).strip()
                if trailing:
                    sub_folders[0] = trailing
                else:
                    sub_folders = sub_folders[1:]

        if country and sub_folders:
            prefix = country.lower()
            candidate = sub_folders[0].lower()
            if candidate.startswith(prefix):
                sub_folders[0] = sub_folders[0][len(country):].lstrip()

        if sub_folders:
            raw_mod = " ".join(sub_folders).strip()
        else:
            raw_mod = "Port Mods"  # default for StevensND repo

        raw_mod = strip_versions(raw_mod)
        m2 = re.match(r'^(.*)\s+v[0-9.]+$', raw_mod, re.IGNORECASE)
        if m2:
            raw_mod = m2.group(1).strip()

    mod_name = clean_title(raw_mod) if raw_mod else "Port Mods"
    return game_name, mod_name

def create_formatted_structure(folder_path, output_path):
    """
    Walk `folder_path` for all .pchtxt files. For each one:
      1) Derive (game_name, mod_name) via get_game_name_and_mod_name.
      2) Sanitize and title‐case those exactly the same as other repos.
      3) Copy <…>.pchtxt into output_path/<Game Name> - <Mod Name>/<version>.pchtxt.
      4) Create title ID flag files.
    """
    os.makedirs(output_path, exist_ok=True)
    print(f"Creating formatted structure at: {output_path}\n")

    for root, dirs, files in os.walk(folder_path):
        # Skip any already formatted directories and common non-content dirs
        if any(skip in root.lower() for skip in ['formatted', '.git', '__pycache__']):
            continue

        for filename in files:
            if not filename.lower().endswith(".pchtxt"):
                continue

            game_name, mod_name = get_game_name_and_mod_name(root, folder_path)
            version = filename[:-len(".pchtxt")].strip()
            combined_dir = f"{game_name} - {mod_name}".rstrip()
            new_dir = os.path.join(output_path, combined_dir)
            os.makedirs(new_dir, exist_ok=True)

            src = os.path.join(root, filename)
            dst = os.path.join(new_dir, f"{version}.pchtxt")
            shutil.copy2(src, dst)
            
            # Extract Title ID from pchtxt and create flag file
            try:
                with open(src, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    # Look for Title ID in format [XXXXXXXXXXXXXXXX]
                    title_id_match = re.search(r'\[([0-9A-Fa-f]{16})\]', content)
                    if title_id_match:
                        title_id = title_id_match.group(1)
                        # Create empty file with .pchtxt-TITLE_ID extension
                        title_id_file_path = os.path.join(new_dir, f"{version}.pchtxt-{title_id}")
                        with open(title_id_file_path, 'w') as title_file:
                            pass  # Create empty file
                        print(f"✅ Copied {os.path.relpath(src, folder_path)} → {os.path.join(os.path.basename(new_dir), f'{version}.pchtxt')} (TitleID: {title_id})")
                    else:
                        print(f"✅ Copied {os.path.relpath(src, folder_path)} → {os.path.join(os.path.basename(new_dir), f'{version}.pchtxt')} (No TitleID found)")
            except Exception as e:
                print(f"❌ Error processing Title ID for {src}: {e}")
                print(f"✅ Copied {os.path.relpath(src, folder_path)} → {os.path.join(os.path.basename(new_dir), f'{version}.pchtxt')} (TitleID error)")

    print("\n✅ Done processing pchtxt files!")

# ---------------- main ----------------
def main():
    # refuse to run as root
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Refusing to run as root. Run this script as your normal user (no sudo).")
        sys.exit(1)

    zip_url = "https://github.com/StevensND/switch-port-mods/archive/refs/heads/main.zip"
    zip_path = "switch-port-mods-main.zip"
    unzip_dir = "switch-port-mods-main"

    if not os.path.exists(unzip_dir):
        if not os.path.exists(zip_path):
            print("Downloading repo zip...")
            urllib.request.urlretrieve(zip_url, zip_path)
            print("Download complete.")
        print("Unzipping repo...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        print("Unzip complete.")

    root = unzip_dir
    output_pchtxt = os.path.join(".", "pchtxts/StevensND")
    
    # Process the pchtxt repository
    create_formatted_structure(root, output_pchtxt)
    
    print("✅ Done processing StevensND port mods.")

if __name__ == '__main__':
    main()