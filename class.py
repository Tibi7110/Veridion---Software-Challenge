class Car:
    def __init__(self, colour:str) -> None:
        self.colour = colour

dacia: Car = Car("Alb")

print(dacia.colour)