from data.pixel import Pixel
from data.read_logo import read_obj

class Logo:
    def __init__(self, width: int, height: int, data: list[list[Pixel]]) -> None:
        self._width = width
        self._height = height
        self._pixels = data

    def getWidth(self) -> int:
        return self._width
    
    def getHeight(self) -> int:
        return self._height
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Logo):
            return False
        return self._width == other._width and self._height == other._height

    def __repr__(self) -> str:
        return f"Width: {self._width}, height: {self._height}"
    
    def __str__(self) -> str:
        rezultat = [f"Width: {self._width}, height: {self._height}"]

        for i in range(self._width):
            for j in range(self._height):
                p = self._pixels[i][j]
                rezultat.append(f"Pixel[{i}][{j}]: x={p.x}, y={p.y}, z={p.z}")
            rezultat.append("----------")

        return "\n".join(rezultat)
    
    

if __name__ == "__main__":

    # Creăm obiectul Logo cu datele citite
    print(0)
'''
    matrice_pixeli, w, l = read_obj()
    logo_personalizat = Logo(w, l, matrice_pixeli)

    print("\nObiectul a fost creat cu succes!")
    print(logo_personalizat)

'''