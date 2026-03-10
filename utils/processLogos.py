from data.transform import process_logo

def processLogos(p):
    print(f"Processing {p.name}...")
    try:
        result = process_logo(str(p))
        return (p.stem, result, None)
    except Exception as e:
        return (p.stem, None, e)