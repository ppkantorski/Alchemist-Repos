#!/usr/bin/env python3
"""
All-in-one processor for KeatonTheBot's switch-pchtxt-mods repo.
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

# ---------------- KeatonTheBot specific processing ----------------
def transform_game_name(game_name):
    """
    1) Move ", The" to front, if present.
    2) Remove any " - " substring.
    """
    if ', The' in game_name:
        parts = game_name.split(', The')
        # e.g., "Zelda, The" → "The Zelda"
        game_name = f"The {parts[0]}{parts[1]}"
    # Remove " - " exactly
    game_name = game_name.replace(' - ', ' ')
    return game_name

def get_game_name_and_mod_name(path, root_dir):
    """
    Given `path` (where a .pchtxt file lives) and the `root_dir`,
    derive:
      • game_name  (with country if present, then sanitized+title‐cased)
      • mod_name   (sanitized+title‐cased), handling Aspect Ratio and version suffix.
    """
    relative_path = os.path.relpath(path, root_dir)
    parts = relative_path.split(os.sep)

    # The first part is the raw game folder name
    raw_game = parts[0]
    # Strip out any bracketed tags, then transform
    raw_game = re.sub(r'\[.*?\]', '', raw_game).strip()
    raw_game = transform_game_name(raw_game)

    # Check for country‐specific folders (look for something like "[USA]" or "[JP]" etc.)
    country = None
    for part in parts[1:]:
        if re.search(r'\[.*?\]', part):
            country = re.sub(r'\[.*?\]', '', part).strip()
            break

    if country:
        raw_game = f"{raw_game} ({country})"

    # Now sanitize + title‐case the game name exactly as in other repos:
    game_name = clean_title(raw_game)

    # Determine mod_name
    # If path contains "Aspect Ratio", then:
    if 'Aspect Ratio' in relative_path:
        # e.g. "<...>/Aspect Ratio/16:9/[files]"
        aspect_ratio = os.path.basename(os.path.dirname(path)).replace("'", ".")
        raw_mod = f"Aspect Ratio {aspect_ratio}"
    else:
        # If the last folder has a version suffix " v\d+", attach it to the previous part
        last_part = parts[-1]
        if re.search(r' v\d+', last_part):
            # e.g. .../SomeMod/Disable Fog v1/file.pchtxt → mod = "Disable Fog v1"
            raw_mod = parts[-2] + " " + last_part
        else:
            # Otherwise just take the immediate parent folder name
            if len(parts) >= 2:
                raw_mod = parts[-2]
            else:
                raw_mod = "Mods"  # fallback

    # Sanitize + title‐case mod_name as well
    mod_name = clean_title(raw_mod)

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

        for file in files:
            if not file.lower().endswith('.pchtxt'):
                continue

            # Derive game_name and mod_name
            game_name, mod_name = get_game_name_and_mod_name(root, folder_path)

            version = file[:-len('.pchtxt')].strip()  # strip the ".pchtxt"
            new_dir = os.path.join(output_path, f"{game_name} - {mod_name}")
            os.makedirs(new_dir, exist_ok=True)

            src = os.path.join(root, file)
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

    zip_url = "https://github.com/KeatonTheBot/switch-pchtxt-mods/archive/refs/heads/main.zip"
    zip_path = "switch-pchtxt-mods-main.zip"
    unzip_dir = "switch-pchtxt-mods-main"

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
    output_pchtxt = os.path.join(".", "pchtxts/KeatonTheBot")
    
    # Process the pchtxt repository
    create_formatted_structure(root, output_pchtxt)
    
    print("✅ Done processing KeatonTheBot pchtxt mods.")

if __name__ == '__main__':
    main()