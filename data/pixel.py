class Pixel:
    def __init__(self, x=0, y=0, z=0):
        self.x = x
        self.y = y
        self.z = z
    
    def update(self, x: int, y: int, z: int):
        self.x = x
        self.y = y
        self.z = z

    def __set_x(self, x: int):
        self.x = x

    def __set_y(self, y: int):
        self.y = y

    def __set_z(self, z: int):
        self.z = z

    def __getitem__(self, key):
        if key == 'x': 
            return self.x
        if key == 'y': 
            return self.y
        if key == 'z': 
            return self.z
        raise KeyError(f"Cheia {key} nu există în Pixel")
        