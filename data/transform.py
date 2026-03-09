import numpy as np
from PIL import Image
import cairosvg
from rembg import remove
from typing import cast
import io
from PIL import Image as PILImage
from pathlib import Path

def load_image_as_png_bytes(image_path: str) -> bytes:
    """Load any image (including SVGs disguised as PNGs) as PNG bytes."""
    with open(image_path, "rb") as f:
        raw = f.read()

    # Detect SVG by content regardless of extension
    is_svg = (
        image_path.lower().endswith(".svg") or
        raw.lstrip()[:5] == b"<?xml" or
        b"<svg" in raw[:512]  # check first 512 bytes for SVG tag
    )

    if is_svg:
        return cast(bytes, cairosvg.svg2png(bytestring=raw))
    
    return raw

def to_grayscale(img: np.ndarray) -> np.ndarray:
    """Convert RGB to grayscale using luminance weights."""
    return (0.299 * img[:,:,0] + 0.587 * img[:,:,1] + 0.114 * img[:,:,2])

def gaussian_kernel(size: int = 3, sigma: float = 1.0) -> np.ndarray:
    """Build a Gaussian blur kernel from scratch."""
    k = size // 2
    x, y = np.mgrid[-k:k+1, -k:k+1]
    kernel = np.exp(-(x**2 + y**2) / (2 * sigma**2))
    return kernel / kernel.sum()

def convolve2d(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Apply a 2D convolution manually using numpy (no scipy)."""
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2

    # Pad image to handle borders
    padded = np.pad(img, ((ph, ph), (pw, pw)), mode='reflect')

    output = np.zeros_like(img, dtype=np.float32)
    for i in range(img.shape[0]):
        for j in range(img.shape[1]):
            output[i, j] = np.sum(padded[i:i+kh, j:j+kw] * kernel)
    return output

def threshold_otsu(gray: np.ndarray) -> np.ndarray:
    """Binarize image using Otsu's method, always returns logo as black on white."""
    pixel_counts, _ = np.histogram(gray.astype(np.uint8), bins=256, range=(0, 256))
    total = gray.size
    best_thresh, best_var = 0, 0

    for t in range(256):
        w0 = pixel_counts[:t].sum() / total
        w1 = pixel_counts[t:].sum() / total
        if w0 == 0 or w1 == 0:
            continue
        mu0 = np.dot(np.arange(t), pixel_counts[:t]) / (w0 * total)
        mu1 = np.dot(np.arange(t, 256), pixel_counts[t:]) / (w1 * total)
        variance = w0 * w1 * (mu0 - mu1) ** 2
        if variance > best_var:
            best_var, best_thresh = variance, t

    bw = (gray > best_thresh).astype(np.uint8) * 255

    # ← always make sure logo is black on white (majority should be background = white)
    if np.mean(bw) < 127:  # if image is mostly black, invert it
        bw = 255 - bw

    return bw

def compute_normalized_mse(img1: np.ndarray, img2: np.ndarray) -> float:
    """MSE normalized to 0-1 range."""
    return float(np.mean((img1.astype(np.float32) - img2.astype(np.float32)) ** 2) / (255 ** 2))


TARGET = (256, 256)

def resize_bw(bw: np.ndarray) -> np.ndarray:
    """Resize while preserving aspect ratio, pad with zeros."""
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
    """Perceptual hash using DCT from scratch."""
    # Resize to 32x32 for DCT
    from PIL import Image as PILImage
    small = np.array(PILImage.fromarray(gray.astype(np.uint8)).resize((32, 32)))

    # DCT (1D applied row then column)
    def dct1d(x):
        N = len(x)
        result = np.zeros(N)
        for k in range(N):
            result[k] = np.sum(x * np.cos(np.pi * k * (2 * np.arange(N) + 1) / (2 * N)))
        return result

    dct = np.apply_along_axis(dct1d, 1, small.astype(np.float32))
    dct = np.apply_along_axis(dct1d, 0, dct)

    # Take top-left hash_size x hash_size block
    dct_low = dct[:hash_size, :hash_size]
    median = np.median(dct_low)
    return (dct_low > median).flatten()

def hamming_distance(h1: np.ndarray, h2: np.ndarray) -> int:
    """Hamming distance between two binary hashes."""
    return int(np.sum(h1 != h2))

def remove_white_background(img: np.ndarray, tolerance: int = 20) -> np.ndarray:
    """Convert near-white pixels to transparent."""
    rgba = np.dstack([img, np.full(img.shape[:2], 255, dtype=np.uint8)])  # add alpha
    gray = to_grayscale(img)
    rgba[:, :, 3][gray > (255 - tolerance)] = 0  # make white pixels transparent
    return rgba


def has_white_background(img: np.ndarray, threshold: int = 240, ratio: float = 0.4) -> bool:
    """Check if image has a significant white background by counting near-white pixels."""
    gray = to_grayscale(img)
    white_pixel_ratio = np.sum(gray > threshold) / gray.size
    return bool(white_pixel_ratio > ratio)

def process_logo(image_path: str) -> dict:
    try:
        input_bytes = load_image_as_png_bytes(image_path)
        img = np.array(Image.open(io.BytesIO(input_bytes)).convert("RGBA"))
    except Exception as e:
        raise ValueError(f"Failed to load image: {e}")

    input_bytes = load_image_as_png_bytes(image_path)
    img = np.array(Image.open(io.BytesIO(input_bytes)).convert("RGBA"))

    rgb   = img[:, :, :3]
    alpha = img[:, :, 3]


    gray    = to_grayscale(rgb)

    kernel  = gaussian_kernel(size=3, sigma=1.0)
    blurred = convolve2d(gray, kernel)
    bw      = threshold_otsu(blurred)


    has_alpha = np.any(alpha < 255)
    if has_alpha:
        # Check if alpha=0 regions are the logo or the background
        # by comparing brightness of transparent vs opaque regions
        opaque_mean  = gray[alpha > 128].mean() if (alpha > 128).any() else 0
        transp_mean  = gray[alpha < 128].mean() if (alpha < 128).any() else 0

        if transp_mean > opaque_mean:
            # Transparent region is BRIGHTER = it's the background → normal case
            bw[alpha == 0] = 0
        else:
            # Transparent region is DARKER = it's the logo → invert the mask
            bw[alpha > 128] = 0

    phash = compute_phash(bw)
    return {"grayscale": gray, "blurred": blurred, "bw": bw, "alpha": alpha, "phash": phash}

def compare_logos(path1: str, path2: str) -> dict:
    p1 = process_logo(path1)
    p2 = process_logo(path2)

    # Resize to same shape for pixel comparison
    h = min(p1["bw"].shape[0], p2["bw"].shape[0])
    w = min(p1["bw"].shape[1], p2["bw"].shape[1])
    bw1 = p1["bw"][:h, :w]
    bw2 = p2["bw"][:h, :w]

    mse      = compute_normalized_mse(bw1, bw2)
    hamming  = hamming_distance(p1["phash"], p2["phash"])
    similar  = hamming < 10 and mse < 0.1

    return {
        "mse":           mse,
        "hamming":       hamming,
        "similar":       similar,
    }

def save_debug_masks(processed: dict, output_folder: Path, n: int = 10):
    for i, (name, data) in enumerate(processed.items()):
        if i >= n:
            break
        Image.fromarray(data["bw"].astype(np.uint8)).save(output_folder / f"{name}_mask.png")