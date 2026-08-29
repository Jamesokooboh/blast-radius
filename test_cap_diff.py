"""One check for the diff size guard: python test_cap_diff.py"""
from review import cap_diff

small = "@@ -1 +1 @@\n+resource\n"
assert cap_diff(small, 1000) is small

big = "".join(f"@@ -{i} +{i} @@\n+line {i}\n" for i in range(200))
out = cap_diff(big, 300)
assert out.startswith("@@ -0 +0 @@")
assert "[diff truncated:" in out
assert out.count("@@ -") < 40 and len(out) < 500
# cut on a hunk boundary, so the model never sees half a hunk
assert out.split("\n\n[diff truncated")[0].endswith(f"+line {out.count('@@ -') - 1}")

no_hunks = "x" * 1000
out2 = cap_diff(no_hunks, 100)
assert out2.startswith("x" * 100) and "[diff truncated: 100 of 1000" in out2
print("ok")
