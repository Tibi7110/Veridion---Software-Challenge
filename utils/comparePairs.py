from scripts.transform import resize_bw, normalized_mse, hamming_distance
from utils.logs import logging
from pathlib import Path
import shutil

LOGO_EXTENSIONS = [".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"]

def find_logo_file(folder: Path, stem: str):
    "Find a logo file by stem, trying all known extensions"
    
    clean_stem = Path(stem).stem  # strips last
    for ext in LOGO_EXTENSIONS:
        p = folder / f"{clean_stem}{ext}"
        if p.exists():
            return p
    return None

def comparePairs(processed, extract_folder: Path):
    "Compare all logos, pair them together and create a new directory"

    stems = list(processed.keys())
    path = Path("/home/tibi/Proiecte/Veridion/tmp/load")
    path.mkdir(parents=True, exist_ok=True)
    results = []
    
    for i in range(len(stems)):
        name1 = stems[i]
        file1 = find_logo_file(extract_folder, name1)
        if not file1: 
            continue

        l = [str(file1)]

        for j in range(i + 1, len(stems)):
            name2 = stems[j]
            p1, p2 = processed[name1], processed[name2]

            # Resize both to 256x256 before comparing
            bw1 = resize_bw(p1["bw"])
            bw2 = resize_bw(p2["bw"])
            mse = normalized_mse(bw1, bw2)
            hamming = hamming_distance(p1["phash"], p2["phash"])
            
            # Logos are considered similar if both scores are below threshold
            similar = hamming < 10 and mse < 0.2
            if similar:
                file2 = find_logo_file(extract_folder, name2)
                if file1 and file2:
                    results.append((str(file1), str(file2), hamming, mse))
                    l.append(str(file2))
                    logging.info(f"SIMILAR: {file1} <-> {file2} | hamming={hamming} | mse={mse:.2f}")

        # Copy all logos in this similarity group into a named subdirectory
        if len(l) > 1:
            
            group_name = Path(l[0]).stem
            group_dir = path / group_name
            group_dir.mkdir(parents=True, exist_ok=True)

            for logo_path in l:
                src = Path(logo_path)
                if src.exists():
                    shutil.copy2(src, group_dir / src.name)
                else:
                    logging.warning(f"MISSING FILE: {src}")

    return results, stems