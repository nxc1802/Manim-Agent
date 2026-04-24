import ast

def _validate_generated_scene_class(tree: ast.Module) -> None:
    for node in tree.body:
        print(f"Node: {type(node)}")
        if isinstance(node, ast.ClassDef):
             print(f"Class: {node.name}")
        if isinstance(node, ast.ClassDef) and node.name == "GeneratedScene":
            return
    raise ValueError("Generated code must define class GeneratedScene")

code = "class GeneratedScene:\n    pass"
tree = ast.parse(code)
_validate_generated_scene_class(tree)
print("OK")
