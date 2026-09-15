import json

with open("sample_outputs/cyoa_c_notebook_fixed.ipynb", "r") as f:
    nb = json.load(f)

for cell in nb["cells"]:
    src = "".join(cell.get("source", []))
    if "def apply_choice_node(" in src:
        lines = cell["source"]
        print("FOUND APPLY_CHOICE_NODE")
        for i, line in enumerate(lines):
            print(f"{i}: {line}")
