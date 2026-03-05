from typing import Tuple

from data.pixel import Pixel

def read_obj() -> Tuple[list[list[Pixel]], int, int]:
    w = int(input("Introdu width: "))
    l = int(input("Introdu height: "))
    matrice_pixeli = []
    print(f"\nIntrodu coordonatele pentru {w * l} pixeli:")
    for i in range(w):
        rand_curent = []
        for j in range(l):
            print(f" Pixel [{i}][{j}]")
            x = int(input(" x: "))
            y = int(input(" y: "))
            z = int(input(" z: "))
            rand_curent.append(Pixel(x, y, z)) 
        matrice_pixeli.append(rand_curent)

    return matrice_pixeli, w, l