#!/usr/bin/env python3
"""
All-in-one processor for theboy181's switch-ptchtxt-mods repo.
Downloads, extracts, and formats pchtxt files with proper naming and title ID flags.
"""
import os, re, sys, shutil, unicodedata, urllib.request, zipfile, rarfile

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

def transform_game_name_raw(raw_game):
    """
    Move ", The" to the front and remove any stray colons:
      e.g. "Skyrim, The" → "The Skyrim"
    """
    if ", The" in raw_game:
        parts = raw_game.split(", The")
        raw_game = f"The {parts[0]}{parts[1]}"
    raw_game = raw_game.replace(":", "")     # strip out colons
    raw_game = raw_game.replace(" - ", " ")   # remove literal " - "
    return raw_game

# ---------------- theboy181 specific processing ----------------
def extract_rar_files(folder_path):
    """
    Extract all .rar files in the root folder_path.
    Look for any .rar files, not just "release_*.rar" pattern.
    """
    print("Looking for RAR files to extract...")
    extracted_any = False

    for root, dirs, files in os.walk(folder_path):
        for item in files:
            if item.lower().endswith(".rar"):
                full = os.path.join(root, item)
                try:
                    with rarfile.RarFile(full) as rf:
                        rf.extractall(root)
                    print(f"✅ Extracted archive: {full}")
                    extracted_any = True
                    os.remove(full)
                    print(f"🗑️ Removed archive: {full}")
                except rarfile.Error as e:
                    print(f"❌ Failed to extract {full}: {e}")
                except Exception as e:
                    print(f"❌ Error with {full}: {e}")

    if not extracted_any:
        print("No RAR files found to extract.")

def get_game_name_and_mod_name(path, root_dir):
    """
    Given a folder `path` containing a .pchtxt, return (game_name, mod_name).
    1) game_name ← first‐level folder under root_dir, strip bracketed tags, move ", The", 
       remove colons, possibly append "(Country)", then run clean_title(...).
    2) mod_name ← if 'Aspect Ratio' in path → "Aspect Ratio <foldername>"; 
       else if last folder ends in " v<digits>" → "<parent> <lastFolder>";
       else immediate parent folder.  
       Afterwards, replace ' / ` → ".", "21-9" → "21.9", remove colons, 
       handle "Trailblazers" → "4K", then run clean_title(...).
    """
    relative = os.path.relpath(path, root_dir)
    parts = relative.split(os.sep)

    # --- raw_game_name logic ---
    raw_game = parts[0]
    raw_game = re.sub(r'\[.*?\]', '', raw_game).strip()
    raw_game = transform_game_name_raw(raw_game)

    # check for country code deeper in path
    country = None
    for p in parts[1:]:
        if re.search(r'\[.*?\]', p):
            country = re.sub(r'\[.*?\]', '', p).strip()
            break
    if country:
        raw_game = f"{raw_game} ({country})"

    game_name = clean_title(raw_game)

    # --- raw_mod_name logic ---
    if "Aspect Ratio" in relative:
        aspect_folder = os.path.basename(path)
        raw_mod = f"Aspect Ratio {aspect_folder}"
    else:
        last_folder = parts[-1]
        if re.search(r' v\d+', last_folder):
            parent_folder = parts[-2] if len(parts) > 2 else ""
            raw_mod = f"{parent_folder} {last_folder}".strip()
        else:
            raw_mod = parts[-2] if len(parts) > 1 else ""

    raw_mod = raw_mod.strip()
    raw_mod = raw_mod.replace("'", ".").replace("`", ".")
    raw_mod = raw_mod.replace("21-9", "21.9")
    raw_mod = raw_mod.replace(":", "")
    if raw_mod == "Trailblazers":
        raw_mod = "4K"

    mod_name = clean_title(raw_mod) if raw_mod else "Mods"
    return game_name, mod_name

def create_formatted_structure(folder_path, output_path):
    """
    1) extract_rar_files(folder_path)  # extract all .rar files
    2) walk every subfolder for .pchtxt
    3) for each .pchtxt, compute (game_name, mod_name) with get_game_name_and_mod_name
    4) copy into output_path/"<Game Name> - <Mod Name>"/"<version>.pchtxt"
    5) Create title ID flag files
    """
    # Extract any RAR files first
    extract_rar_files(folder_path)
    
    os.makedirs(output_path, exist_ok=True)
    print(f"Creating formatted structure at: {output_path}\n")

    pchtxt_count = 0
    
    for root, dirs, files in os.walk(folder_path):
        # Skip any already formatted directories and common non-content dirs
        if any(skip in root.lower() for skip in ['formatted', '.git', '__pycache__']):
            continue

        for filename in files:
            if not filename.lower().endswith(".pchtxt"):
                continue

            pchtxt_count += 1
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

    print(f"\n✅ Done processing {pchtxt_count} pchtxt files!")

# ---------------- main ----------------
def main():
    # refuse to run as root
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Refusing to run as root. Run this script as your normal user (no sudo).")
        sys.exit(1)

    zip_url = "https://github.com/theboy181/switch-ptchtxt-mods/archive/refs/heads/main.zip"
    zip_path = "switch-ptchtxt-mods-main.zip"
    unzip_dir = "switch-ptchtxt-mods-main"

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
    output_pchtxt = os.path.join(".", "pchtxts/theboy181")
    
    # Process the pchtxt repository
    create_formatted_structure(root, output_pchtxt)
    
    print("✅ Done processing theboy181 pchtxt mods.")

if __name__ == '__main__':
    main()