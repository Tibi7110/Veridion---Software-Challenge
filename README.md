<h1 align="center"><b>Proiect Veridion</b></h1>

# Cum se foloseste?

 - git clone https://github.com/Tibi7110/Veridion---Software-Challenge.git
 - pip install -r requirements.txt
 - python3 main.py

 ## SAU

 - docker pull tibi7110/veridion-logo-scraper
 - docker run tibi7110/veridion-logo-scraper


# Ideea Proiectului:

- Proiectul consta intr-un web scraper ce grupeaza logo-urile similare, fara sa se foloseasca algoritmi de ML.

# Legenda:

```
/data contine fisierul primit cu url-uri si /logs care detaliaza
      functionarea scripturilor de scraping si transform

/etc contine un fisier yaml cu basic config

/scripts cele 2 scripturi de baza ale programului

/tmp datele intermediare pentru a se putea verifica functionalitatea programului

    - /tmp/extract: logo-urile extrase
    - /tmp/load: datele finale
    - /tmp/transform: imaginile prelucrate

/utils contine diferite module si packete care sunt folosite in program

main.py: entry point-ul
```

# Cum a fost implementata ideea?

Am inceput prin a face un script de scraping ce se poate regasi in /scripts/scraping.py,
ca mai apoi sa aplic diferite filtre pe imagini precum conversie in alb-negru,redimensionare,
normalizari, metoda Otsu, gaussian blur si sa calculez un hash al imaginii folosind algoritmul pHash. Imaginile
dupa fiind sortate cat de similare sunt dupa hamming distance si MSE.

Programul este optimizat folosind multi-threading si multi-processing.

Pentru scraping, logica e una relativ simpla, avem un algoritm euristic care ia imaginea
de pe pagina cu cel mai bun scor, acesta fiind atribuit in functie de unde pe pagina se gasesc acestea.

Tiberiu Chirila