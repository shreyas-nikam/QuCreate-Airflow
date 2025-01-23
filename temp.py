from pathlib import Path

s1 = "output"
s2 = Path("output")
s3 = s2 / "Path"
s4 = Path(s2 / "Path")
s5 = Path(f"{s2}/Path")

print(s1, s2, s3, s4, s5)