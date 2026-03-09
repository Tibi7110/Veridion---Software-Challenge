from pathlib import Path

# Specifică calea către folder
path = Path("/home/tibi/Proiecte/Veridion/logos")

# Numără doar fișierele (excluzând subfolderele)
file_count = sum(1 for item in path.iterdir() if item.is_file())

print(f"Sunt {file_count} fișiere în folder.")