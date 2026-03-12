from scripts.transform import process_logo

def processLogos(p):
    "Wrapper for processing"
    try:
        result = process_logo(str(p))
        return (p.stem, result, None)
    except Exception as e:
        return (p.stem, None, str(e))