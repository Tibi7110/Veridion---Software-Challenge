from data.transform import resize_bw, compute_normalized_mse, hamming_distance
from data.logs import logging

def comparePairs(processed):
    stems = list(processed.keys())
    results = []
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            name1, name2 = stems[i], stems[j]
            p1, p2 = processed[name1], processed[name2]
            bw1 = resize_bw(p1["bw"])
            bw2 = resize_bw(p2["bw"])
            mse     = compute_normalized_mse(bw1, bw2)
            hamming = hamming_distance(p1["phash"], p2["phash"])
            similar  = hamming < 10 and mse < 0.2
            if similar:
                results.append((name1, name2, hamming, mse))
                logging.info(f"SIMILAR: {name1} <-> {name2} | hamming={hamming} | mse={mse:.2f}")
    return results, stems