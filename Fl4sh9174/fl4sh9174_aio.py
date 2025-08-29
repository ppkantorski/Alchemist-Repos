#!/usr/bin/env python3
"""
All-in-one processor for Fl4sh9174's Switch-Ultrawide-Mods repo.
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

# ---------------- Processing functions ----------------
def unzip_files(folder_path):
    print("Unzipping files...\n")
    for item in os.listdir(folder_path):
        if item.lower().endswith('.zip'):
            file_path = os.path.join(folder_path, item)
            # Remove any bracketed tags (e.g. "[something]") then strip ".zip"
            raw_game_name = re.sub(r'\[.*?\]', '', item).replace('.zip', '').strip()
            cleaned_game_name = clean_title(raw_game_name)
            extract_to = os.path.join(folder_path, cleaned_game_name)
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            print(f"✅ Unzipped: {file_path} → {extract_to}")
            # Remove the original zip file
            os.remove(file_path)

def create_formatted_structure(folder_path):
    formatted_path = os.path.join(folder_path, 'formatted')
    os.makedirs(formatted_path, exist_ok=True)
    print(f"\nOrganizing into: {formatted_path}\n")

    for game_dir in os.listdir(folder_path):
        game_dir_path = os.path.join(folder_path, game_dir)
        # Skip the "formatted" folder itself and non-directories
        if not os.path.isdir(game_dir_path) or game_dir == 'formatted':
            continue

        # Compute the cleaned, title-cased game name once:
        cleaned_game_name = clean_title(game_dir)

        for root, dirs, files in os.walk(game_dir_path):
            for file in files:
                if file.lower().endswith('.pchtxt'):
                    # Look for a [mod_name vX.Y] segment in the path
                    relative_path = os.path.relpath(root, folder_path)
                    mod_match = re.search(r'\[(.*?)\]', relative_path)
                    if not mod_match:
                        # If no bracketed mod name found, use "Ultrawide Mods" as default
                        mod_name_clean = "Ultrawide Mods"
                    else:
                        raw_mod_name = mod_match.group(1)
                        # Strip off any trailing " v<digits>" from the bracketed part
                        mod_name_no_version = re.sub(r' v[0-9.]+$', '', raw_mod_name).strip()
                        mod_name_clean = clean_title(mod_name_no_version)

                    version = file[:-len('.pchtxt')].strip()

                    target_dir = os.path.join(
                        formatted_path,
                        f"{cleaned_game_name} - {mod_name_clean}"
                    )
                    os.makedirs(target_dir, exist_ok=True)

                    source_file = os.path.join(root, file)
                    dest_file = os.path.join(target_dir, f"{version}.pchtxt")
                    
                    # Copy the file instead of moving so we can process title ID
                    shutil.copy2(source_file, dest_file)
                    
                    # Extract Title ID from pchtxt and create flag file
                    try:
                        with open(source_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # Look for Title ID in format [XXXXXXXXXXXXXXXX]
                            title_id_match = re.search(r'\[([0-9A-Fa-f]{16})\]', content)
                            if title_id_match:
                                title_id = title_id_match.group(1)
                                # Create empty file with .pchtxt-TITLE_ID extension
                                title_id_file_path = os.path.join(target_dir, f"{version}.pchtxt-{title_id}")
                                with open(title_id_file_path, 'w') as title_file:
                                    pass  # Create empty file
                                print(f"📦 Processed {file} → {os.path.join(target_dir, f'{version}.pchtxt')} (TitleID: {title_id})")
                            else:
                                print(f"📦 Processed {file} → {os.path.join(target_dir, f'{version}.pchtxt')} (No TitleID found)")
                    except Exception as e:
                        print(f"❌ Error processing Title ID for {source_file}: {e}")
                        print(f"📦 Processed {file} → {os.path.join(target_dir, f'{version}.pchtxt')} (TitleID error)")

        # Once done walking this game's directory, remove it entirely
        shutil.rmtree(game_dir_path)
        print(f"🗑️ Removed temporary folder: {game_dir_path}")

    print("\n✅ All files organized successfully.")

def process_pchtxt_repo(repo_path, output_path):
    """
    Process the extracted repo to create formatted pchtxt structure.
    """
    os.makedirs(output_path, exist_ok=True)
    print(f"Creating formatted pchtxt structure at: {output_path}\n")
    
    # First unzip any zip files in the repo
    unzip_files(repo_path)
    
    # Then create the formatted structure
    create_formatted_structure(repo_path)
    
    # Move the formatted folder to the output location
    formatted_source = os.path.join(repo_path, 'formatted')
    if os.path.exists(formatted_source):
        # Copy contents of formatted folder to output path
        for item in os.listdir(formatted_source):
            source_item = os.path.join(formatted_source, item)
            dest_item = os.path.join(output_path, item)
            if os.path.isdir(source_item):
                shutil.copytree(source_item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(source_item, dest_item)
        print(f"✅ Moved formatted structure to {output_path}")

# ---------------- main ----------------
def main():
    # refuse to run as root
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Refusing to run as root. Run this script as your normal user (no sudo).")
        sys.exit(1)

    zip_url = "https://github.com/Fl4sh9174/Switch-Ultrawide-Mods/archive/refs/heads/main.zip"
    zip_path = "Switch-Ultrawide-Mods-main.zip"
    unzip_dir = "Switch-Ultrawide-Mods-main"

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
    output_pchtxt = os.path.join(".", "pchtxts/fl4sh9174")
    
    # Process the pchtxt repository
    process_pchtxt_repo(root, output_pchtxt)
    
    print("✅ Done processing Fl4sh9174 pchtxt mods.")

if __name__ == '__main__':
    main()