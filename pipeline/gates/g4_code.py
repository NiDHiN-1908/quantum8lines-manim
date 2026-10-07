"""
Quality Gate G4: Code Quality & AST Linter (SPEC.md Section 9).
Performs AST-level validation on scene.py:
- Rule a (G4a_numeric_literals): Only 0, 1, -1 numeric literals allowed.
- Rule b (G4b_no_raw_colors): Rejects Manim color names and raw hex color strings; must use core.tokens.
- Rule c (G4c_imports): Imports restricted to manim, math, and core.*.
- Rule d (G4d_forbidden_names): Rejects eval, exec, open, __import__, compile, subprocess, os, sys, and __ attributes.
- Rule e (G4e_basescene_subclass): Requires defining a class inheriting from BaseScene.
- Rule f (G4f_dry_run_construct): Scene constructs cleanly in both 16:9 and 9:16 layouts.
- Extension point for M2.2 character roster verification.
"""

import ast
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from manim import config as manim_config
from core.layout import LAYOUT_169, LAYOUT_916
from core.scene_base import BaseScene
from pipeline.gates.models import Check, GateConfig, GateResult

ALLOWED_NUMERICS: Set[Union[int, float]] = {0, 1, -1, 0.0, 1.0, -1.0}

FORBIDDEN_NAMES: Set[str] = {
    "eval",
    "exec",
    "open",
    "__import__",
    "compile",
    "subprocess",
    "os",
    "sys",
}

MANIM_COLOR_NAMES: Set[str] = {
    "BLUE",
    "BLUE_A",
    "BLUE_B",
    "BLUE_C",
    "BLUE_D",
    "BLUE_E",
    "PURE_BLUE",
    "DARK_BLUE",
    "TEAL",
    "TEAL_A",
    "TEAL_B",
    "TEAL_C",
    "TEAL_D",
    "TEAL_E",
    "GREEN",
    "GREEN_A",
    "GREEN_B",
    "GREEN_C",
    "GREEN_D",
    "GREEN_E",
    "PURE_GREEN",
    "YELLOW",
    "YELLOW_A",
    "YELLOW_B",
    "YELLOW_C",
    "YELLOW_D",
    "YELLOW_E",
    "GOLD",
    "GOLD_A",
    "GOLD_B",
    "GOLD_C",
    "GOLD_D",
    "GOLD_E",
    "RED",
    "RED_A",
    "RED_B",
    "RED_C",
    "RED_D",
    "RED_E",
    "PURE_RED",
    "MAROON",
    "MAROON_A",
    "MAROON_B",
    "MAROON_C",
    "MAROON_D",
    "MAROON_E",
    "PURPLE",
    "PURPLE_A",
    "PURPLE_B",
    "PURPLE_C",
    "PURPLE_D",
    "PURPLE_E",
    "PINK",
    "LIGHT_PINK",
    "ORANGE",
    "WHITE",
    "BLACK",
    "GRAY",
    "GRAY_A",
    "GRAY_B",
    "GRAY_C",
    "GRAY_D",
    "GRAY_E",
    "DARK_GRAY",
    "LIGHT_GRAY",
    "GREY",
    "GREY_A",
    "GREY_B",
    "GREY_C",
    "GREY_D",
    "GREY_E",
    "DARK_GREY",
    "LIGHT_GREY",
}

HEX_COLOR_REGEX = re.compile(
    r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
)


class SceneASTVisitor(ast.NodeVisitor):
    """AST Visitor checking rules G4a through G4e."""

    def __init__(self):
        self.numeric_errors: List[str] = []
        self.color_errors: List[str] = []
        self.import_errors: List[str] = []
        self.forbidden_name_errors: List[str] = []
        self.basescene_subclasses: List[str] = []
        self.handled_constants: Set[int] = set()

    def visit_UnaryOp(self, node: ast.UnaryOp):
        # Handle signed constants like -1, +1, -2.7
        if isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(
            node.operand, ast.Constant
        ):
            val = node.operand.value
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                signed_val = -val if isinstance(node.op, ast.USub) else val
                self.handled_constants.add(id(node.operand))
                if signed_val not in ALLOWED_NUMERICS:
                    self.numeric_errors.append(
                        f"Line {node.lineno}: Disallowed numeric literal {signed_val}. "
                        "Only 0, 1, -1 allowed; others must come from facts.json or core.*."
                    )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if id(node) in self.handled_constants:
            return

        val = node.value
        # Rule a: numeric constants
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if val not in ALLOWED_NUMERICS:
                self.numeric_errors.append(
                    f"Line {node.lineno}: Disallowed numeric literal {val}. "
                    "Only 0, 1, -1 allowed; others must come from facts.json or core.*."
                )

        # Rule b: hex color strings
        elif isinstance(val, str) and HEX_COLOR_REGEX.match(val.strip()):
            self.color_errors.append(
                f"Line {node.lineno}: Raw hex color string '{val}' found. Must use core.tokens."
            )

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        # Rule b: Manim color names
        if node.id in MANIM_COLOR_NAMES:
            self.color_errors.append(
                f"Line {node.lineno}: Raw Manim color name '{node.id}' found. Must use core.tokens."
            )

        # Rule d: Forbidden names
        if node.id in FORBIDDEN_NAMES:
            self.forbidden_name_errors.append(
                f"Line {node.lineno}: Use of forbidden name '{node.id}'."
            )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Rule d: Forbidden attributes and __ attributes
        if node.attr in FORBIDDEN_NAMES:
            self.forbidden_name_errors.append(
                f"Line {node.lineno}: Access to forbidden attribute '{node.attr}'."
            )
        elif node.attr.startswith("__"):
            self.forbidden_name_errors.append(
                f"Line {node.lineno}: Access to private/dunder attribute '{node.attr}'."
            )

        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        # Rule c: Imports restricted to manim, math, and core.*
        for alias in node.names:
            top_mod = alias.name.split(".")[0]
            if top_mod not in ("manim", "math", "core"):
                self.import_errors.append(
                    f"Line {node.lineno}: Disallowed import '{alias.name}'. Only manim, math, and core.* allowed."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        # Rule c: From imports
        if node.module:
            top_mod = node.module.split(".")[0]
            if top_mod not in ("manim", "math", "core"):
                self.import_errors.append(
                    f"Line {node.lineno}: Disallowed import from '{node.module}'. Only manim, math, and core.* allowed."
                )
        # Check imported aliases for Manim color names
        for alias in node.names:
            if alias.name in MANIM_COLOR_NAMES:
                self.color_errors.append(
                    f"Line {node.lineno}: Raw Manim color name '{alias.name}' imported. Must use core.tokens."
                )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        # Rule e: BaseScene subclass
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseScene":
                self.basescene_subclasses.append(node.name)
            elif isinstance(base, ast.Attribute) and base.attr == "BaseScene":
                self.basescene_subclasses.append(node.name)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Extension Point for M2.2: Character Roster Verification
# ---------------------------------------------------------------------------
def check_character_roster_extension(
    tree: ast.AST,
    roster_path: Optional[Path] = None,
) -> List[Check]:
    """
    Extension point for Milestone M2.2 (Character roster verification).
    Verifies that any character IDs, states, and slots referenced in scene.py
    exist in characters/roster.json.
    """
    # M2.2 will hook character asset validation here.
    return []


def run_g4_code(
    chapter_dir: Optional[Union[str, Path]] = None,
    scene_source: Optional[str] = None,
    scene_path: Optional[Union[str, Path]] = None,
    config: Optional[GateConfig] = None,
) -> GateResult:
    """
    Execute Quality Gate G4: Code Quality & AST Linter.
    """
    checks: List[Check] = []

    # 1. Resolve source code
    if scene_source is None:
        if scene_path is not None:
            target = Path(scene_path)
        elif chapter_dir is not None:
            target = Path(chapter_dir) / "scene.py"
        else:
            target = None

        if target and target.exists():
            with open(target, "r", encoding="utf-8") as f:
                scene_source = f.read()

    if scene_source is None:
        checks.append(
            Check(
                id="G4_syntax",
                passed=False,
                severity="error",
                message="No scene code provided and scene.py not found.",
            )
        )
        return GateResult.create("G4", checks)

    # 2. Parse AST
    try:
        tree = ast.parse(scene_source)
    except SyntaxError as e:
        checks.append(
            Check(
                id="G4_syntax",
                passed=False,
                severity="error",
                message=f"SyntaxError in scene code at line {e.lineno}: {e.msg}",
            )
        )
        return GateResult.create("G4", checks)

    # 3. Visit AST nodes
    visitor = SceneASTVisitor()
    visitor.visit(tree)

    # Rule a: G4a_numeric_literals
    checks.append(
        Check(
            id="G4a_numeric_literals",
            passed=len(visitor.numeric_errors) == 0,
            severity="error",
            message="Numeric literals adhere to allowed set {0, 1, -1}."
            if len(visitor.numeric_errors) == 0
            else f"Hard-coded numeric literals found: {'; '.join(visitor.numeric_errors[:3])}",
            details={"errors": visitor.numeric_errors}
            if visitor.numeric_errors
            else None,
        )
    )

    # Rule b: G4b_no_raw_colors
    checks.append(
        Check(
            id="G4b_no_raw_colors",
            passed=len(visitor.color_errors) == 0,
            severity="error",
            message="No raw colors found; tokens used consistently."
            if len(visitor.color_errors) == 0
            else f"Raw colors found: {'; '.join(visitor.color_errors[:3])}",
            details={"errors": visitor.color_errors}
            if visitor.color_errors
            else None,
        )
    )

    # Rule c: G4c_imports
    checks.append(
        Check(
            id="G4c_imports",
            passed=len(visitor.import_errors) == 0,
            severity="error",
            message="All imports are restricted to manim, math, and core.*."
            if len(visitor.import_errors) == 0
            else f"Disallowed imports: {'; '.join(visitor.import_errors[:3])}",
            details={"errors": visitor.import_errors}
            if visitor.import_errors
            else None,
        )
    )

    # Rule d: G4d_forbidden_names
    checks.append(
        Check(
            id="G4d_forbidden_names",
            passed=len(visitor.forbidden_name_errors) == 0,
            severity="error",
            message="No forbidden functions or dunder attributes used."
            if len(visitor.forbidden_name_errors) == 0
            else f"Forbidden names detected: {'; '.join(visitor.forbidden_name_errors[:3])}",
            details={"errors": visitor.forbidden_name_errors}
            if visitor.forbidden_name_errors
            else None,
        )
    )

    # Rule e: G4e_basescene_subclass
    has_subclass = len(visitor.basescene_subclasses) > 0
    checks.append(
        Check(
            id="G4e_basescene_subclass",
            passed=has_subclass,
            severity="error",
            message=f"Defines BaseScene subclass: {visitor.basescene_subclasses}."
            if has_subclass
            else "No class inheriting from BaseScene defined in scene.py.",
            details={"subclasses": visitor.basescene_subclasses}
            if has_subclass
            else None,
        )
    )

    # Extension point checks
    roster_path = (
        Path(chapter_dir).parents[1] / "characters" / "roster.json"
        if chapter_dir
        else None
    )
    checks.extend(check_character_roster_extension(tree, roster_path))

    # Rule f: G4f_dry_run_construct
    # Only execute code if lint rules a-e pass
    lint_passed = all(
        c.passed
        for c in checks
        if c.id
        in (
            "G4a_numeric_literals",
            "G4b_no_raw_colors",
            "G4c_imports",
            "G4d_forbidden_names",
            "G4e_basescene_subclass",
        )
    )

    if not lint_passed:
        checks.append(
            Check(
                id="G4f_dry_run_construct",
                passed=False,
                severity="error",
                message="Dry-run construction skipped because AST lint checks failed.",
            )
        )
        return GateResult.create("G4", checks)

    # Execute dry-run construct in 16:9 and 9:16
    construct_errs = []
    old_dry_run = manim_config.dry_run
    old_verbosity = manim_config.verbosity
    manim_config.dry_run = True
    manim_config.verbosity = "ERROR"

    try:
        compiled = compile(scene_source, "<scene>", "exec")
        exec_namespace: Dict[str, Any] = {}
        exec(compiled, exec_namespace)

        scene_cls = None
        for name in visitor.basescene_subclasses:
            cand = exec_namespace.get(name)
            if cand and isinstance(cand, type) and issubclass(cand, BaseScene):
                scene_cls = cand
                break

        if not scene_cls:
            construct_errs.append("Could not locate instantiated BaseScene subclass.")
        else:
            for layout in (LAYOUT_169, LAYOUT_916):
                try:
                    scene_inst = scene_cls(
                        layout=layout,
                        chapter_dir=chapter_dir,
                    )
                    scene_inst.render()
                except Exception as ex:
                    construct_errs.append(
                        f"Failed during construct in {layout.name}: {type(ex).__name__}: {str(ex)}"
                    )

    except Exception as ex:
        construct_errs.append(f"Execution failed: {type(ex).__name__}: {str(ex)}")
    finally:
        manim_config.dry_run = old_dry_run
        manim_config.verbosity = old_verbosity

    checks.append(
        Check(
            id="G4f_dry_run_construct",
            passed=len(construct_errs) == 0,
            severity="error",
            message="Scene constructed cleanly in both 16:9 and 9:16."
            if len(construct_errs) == 0
            else f"Construct failed: {'; '.join(construct_errs)}",
            details={"errors": construct_errs} if construct_errs else None,
        )
    )

    return GateResult.create("G4", checks)
