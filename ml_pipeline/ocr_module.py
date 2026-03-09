import os
import re
import sys
import cv2
import numpy as np
import easyocr

# Lazily initialised on first OCR call — avoids the ~10s startup
# cost and ~200MB RAM load when no vehicles are ever detected.
_reader = None

def _get_reader():
    global _reader
    if _reader is None:
        print("[OCR] Initialising EasyOCR reader (first vehicle detected)...")
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        print("[OCR] EasyOCR ready.")
    return _reader


def clean_text(text: str) -> str:
    # Aggressively remove anything that isn't alphanumeric
    return re.sub(r'[^A-Z0-9]', '', text.upper()).strip()


def check_valid_indian_format(plate: str) -> bool:
    # Indian plates generally follow standard XX 00 XX 0000 format
    # Often BH series or fancy numbers break the mould.
    # We enforce length and basic alphanumeric ratio.
    if not (6 <= len(plate) <= 12):
        return False
    
    # Must have at least a few letters and a few numbers
    letters = sum(c.isalpha() for c in plate)
    numbers = sum(c.isdigit() for c in plate)
    
    if letters < 2 or numbers < 1:
        return False
        
    return True


def apply_soft_correction(text: str) -> str:
    """
    Applies non-destructive character mapping where strictly ambiguous
    e.g. if we know Indian plates rarely start with '0', change leading '0' to 'O'.
    We avoid the strict position-based mutation of the old function.
    """
    if len(text) < 6:
        return text

    corrected = list(text)

    # State codes (first 2 chars) are always letters (e.g., MH, DL, KA)
    for i in range(min(2, len(corrected))):
        if corrected[i] == '0': corrected[i] = 'O'
        elif corrected[i] == '1': corrected[i] = 'I'
        elif corrected[i] == '5': corrected[i] = 'S'
        elif corrected[i] == '8': corrected[i] = 'B'

    # The next two are usually digits (RTO code)
    for i in range(2, min(4, len(corrected))):
        if corrected[i] == 'O': corrected[i] = '0'
        elif corrected[i] == 'I': corrected[i] = '1'
        elif corrected[i] == 'S': corrected[i] = '5'
        elif corrected[i] == 'B': corrected[i] = '8'
        elif corrected[i] == 'Z': corrected[i] = '2'

    # The last 4 are almost always digits
    for i in range(max(4, len(corrected) - 4), len(corrected)):
        if corrected[i] == 'O': corrected[i] = '0'
        elif corrected[i] == 'I': corrected[i] = '1'
        elif corrected[i] == 'S': corrected[i] = '5'
        elif corrected[i] == 'B': corrected[i] = '8'
        elif corrected[i] == 'Z': corrected[i] = '2'

    return ''.join(corrected)


def preprocess_plate_crop(crop):
    """
    Enhance the crop for better OCR results.
    - Grayscale
    - Bilateral Filter to reduce noise while keeping edges sharp
    - CLAHE to improve contrast (especially useful for shadowed plates)
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Noise reduction keeping edges sharp
    bfilter = cv2.bilateralFilter(gray, 11, 17, 17)
    
    # Improve contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(bfilter)
    
    return enhanced


def read_license_plate_from_crop(crop):
    if crop is None or crop.size == 0:
        print("[OCR] Empty crop")
        return None

    h, w = crop.shape[:2]
    if h < 64:
        scale = 64 / h
        crop  = cv2.resize(crop, (int(w * scale), 64),
                           interpolation=cv2.INTER_CUBIC)

    # Preprocess image
    processed_crop = preprocess_plate_crop(crop)

    try:
        # Returns list of (bbox, text, confidence)
        results = _get_reader().readtext(
            processed_crop,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            detail=1
        )
    except Exception as e:
        print(f"[OCR] Error: {e}")
        return None

    if not results:
        print("[OCR] No text detected")
        return None

    candidates = []
    for (bbox, text, conf) in results:
        cleaned = clean_text(text)
        print(f"[OCR] Raw: '{text}' → '{cleaned}' (conf: {conf:.2f})")
        if len(cleaned) >= 4:
            candidates.append((cleaned, conf))

    if not candidates:
        return None

    best_text, best_conf = max(candidates, key=lambda x: x[1])

    if best_conf < 0.35:
        print(f"[OCR] Confidence {best_conf:.2f} too low")
        return None

    corrected = apply_soft_correction(best_text)

    if check_valid_indian_format(corrected):
        print(f"[OCR] ✓ Final plate: {corrected} (conf: {best_conf:.2f})")
        return corrected

    print(f"[OCR] '{corrected}' failed validation (len={len(corrected)})")
    return None


def read_license_plate_from_image(image_path: str):
    if not os.path.exists(image_path):
        print(f"[OCR] File not found: {image_path}")
        return None
    img = cv2.imread(image_path)
    if img is None:
        print(f"[OCR] Could not load: {image_path}")
        return None
    return read_license_plate_from_crop(img)


def read_license_plate_from_frame(frame, vehicle_box):
    h, w    = frame.shape[:2]
    padding = 10
    x1 = max(0, int(vehicle_box[0]) - padding)
    y1 = max(0, int(vehicle_box[1]) - padding)
    x2 = min(w, int(vehicle_box[2]) + padding)
    y2 = min(h, int(vehicle_box[3]) + padding)
    crop = frame[y1:y2, x1:x2]
    return read_license_plate_from_crop(crop)