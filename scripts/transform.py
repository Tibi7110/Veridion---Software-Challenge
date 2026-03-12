import cairosvg
import cv2
import io
from pathlib import Path
from PIL import Image
import numpy as np
import warnings

warnings.filterwarnings("ignore")

def normalized_mse(img1: np.ndarray, img2: np.ndarray) -> float:
    "MSE normalized to 0-1 range."
    return float(np.mean((img1.astype(np.float32) - img2.astype(np.float32)) ** 2) / (255 ** 2))


def resize_bw(bw: np.ndarray) -> np.ndarray:
    "Resize to 256 x 256 while preserving aspect ratio, pad with black pixels."

    TARGET = (256, 256)
    h, w = bw.shape
    scale = min(TARGET[0] / h, TARGET[1] / w)
    new_h, new_w = int(h * scale), int(w * scale)

    resized = np.array(
        Image.fromarray(bw.astype(np.uint8)).resize((new_w, new_h), Image.Resampling.LANCZOS)
    )

    # Pad to TARGET size with zeros (black = background)
    canvas = np.zeros(TARGET, dtype=np.uint8)
    pad_h = (TARGET[0] - new_h) // 2
    pad_w = (TARGET[1] - new_w) // 2
    canvas[pad_h:pad_h + new_h, pad_w:pad_w + new_w] = resized
    return canvas

def compute_phash(gray: np.ndarray, hash_size: int = 8) -> np.ndarray:
    "Compute phash"

    hash_mat = cv2.img_hash.pHash(gray)
    return np.unpackbits(hash_mat.astype(np.uint8))

def hamming_distance(h1: np.ndarray, h2: np.ndarray) -> int:
    return int(np.sum(h1 != h2))

def process_logo(path: str):
    "Load a logo, convert to a normalised black and white mask, and compute its phash."

    raw = Path(path).read_bytes()
    if path.lower().endswith(".svg") or b"<svg" in raw[:1024]: # SVGs are reinstated via cairosvg
        raw = cairosvg.svg2png(bytestring=raw)

    if not raw:
        raise ValueError(f"Wrong path: {path}")
    
    gray = np.array(Image.open(io.BytesIO(raw)).convert("L"))
    # blur + otsu => black and white mask
    blurred = cv2.GaussianBlur(gray, (3, 3), 1.0)
    _, bw = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Polarity is normalised 
    if bw.mean() < 128:
        bw = 255 - bw

    ph = compute_phash(bw)
    return {"bw": bw.astype(np.uint8), "phash": ph}

def save_debug_masks(processed: dict, output_folder: Path, n: int = 10):
    
    for i, (name, data) in enumerate(processed.items()):
        if i >= n:
            break
        stem = Path(name).stem
        Image.fromarray(data["bw"].astype(np.uint8)).save(output_folder / f"{stem}_mask.png")
