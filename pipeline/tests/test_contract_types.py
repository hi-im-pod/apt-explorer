"""site/src/lib/data/types.ts must mirror the JSON Schemas field for field.

The site's TypeScript types are written by hand. When a schema gains, loses or
renames a field, nothing else notices that the types did not follow until a page
renders "undefined". Each interface and union in types.ts names the schema node
it mirrors in an @schema tag, and these tests pair the two through that tag.
"""
import re
from pathlib import Path

import pytest

from aptx.build.contract import SCHEMA_DIR, load_schema

ROOT = Path(__file__).resolve().parents[2]
TYPES = ROOT / "site" / "src" / "lib" / "data" / "types.ts"
SCHEMA_FILES = sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json"))

# A doc comment directly followed by an exported interface or type alias. The
# site file keeps each interface's closing brace on its own line and uses no
# inline object types, so a non-greedy match up to "\n}" is exact.
_DECL = re.compile(r"/\*\*((?:(?!\*/).)*)\*/\s*export\s+(interface|type)\s+(\w+)\s*"
                   r"(?:=\s*([^;]+);|\{(.*?)\n\})", re.S)
_TAG = re.compile(r"@schema\s+(\S+)")
_FIELD = re.compile(r"^\s*(\w+)(\??)\s*:\s*([^;]+);", re.M)
_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_NULL = re.compile(r"\s*\|\s*null\b")


class Decl:
    def __init__(self, name, kind, tags, rhs, fields):
        self.name, self.kind, self.tags, self.rhs, self.fields = name, kind, tags, rhs, fields


def _parse(text: str) -> dict[str, Decl]:
    decls = {}
    for doc, kind, name, rhs, body in _DECL.findall(text):
        fields = {}
        if kind == "interface":
            for field, optional, type_text in _FIELD.findall(_COMMENT.sub("", body)):
                fields[field] = (optional == "?", type_text.strip())
        decls[name] = Decl(name, kind, _TAG.findall(doc), rhs.strip(), fields)
    return decls


@pytest.fixture(scope="module")
def decls() -> dict[str, Decl]:
    assert TYPES.is_file(), f"{TYPES} is missing"
    return _parse(TYPES.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tagged(decls) -> dict[str, Decl]:
    out = {}
    for decl in decls.values():
        for tag in decl.tags:
            assert tag not in out, f"{tag} is tagged on both {out[tag].name} and {decl.name}"
            out[tag] = decl
    return out


def _node(schema: dict, pointer: str):
    node = schema
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _follow(schema: dict, pointer: str, node: dict) -> tuple[str, dict]:
    """Follow $ref from node to the node that actually says what the value is."""
    while "$ref" in node:
        pointer = node["$ref"].removeprefix("#")
        node = _node(schema, pointer)
    return pointer, node


def _types(node: dict) -> set[str]:
    if "type" in node:
        return set(node["type"]) if isinstance(node["type"], list) else {node["type"]}
    return {"null" if v is None else "string" for v in node.get("enum", [])}


def _is_object(node) -> bool:
    # An object that may also be null, such as guesses.json's evaluation, counts as an object:
    # its TypeScript interface is tagged, and the null shows up as "| null" at the use site.
    return isinstance(node, dict) and "object" in _types(node) and "properties" in node


def _is_enum(node) -> bool:
    return isinstance(node, dict) and isinstance(node.get("enum"), list)


def _walk(node, pointer=""):
    if isinstance(node, dict):
        yield pointer, node
        for key, value in node.items():
            yield from _walk(value, f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{pointer}/{i}")


def _string_aliases(decls: dict[str, Decl]) -> set[str]:
    return {"string"} | {d.name for d in decls.values() if d.kind == "type" and d.rhs == "string"}


def _check_value(file, schema, pointer, node, ts_type, decls, tagged, where) -> None:
    """Check one TypeScript type expression against the schema node it mirrors."""
    pointer, node = _follow(schema, pointer, node)
    types = _types(node)
    # An array whose elements may be null is written (Item | null)[], and the null belongs to the
    # elements, not to the array, so the elements are checked on their own.
    element = re.fullmatch(r"\((.+)\)\[\]", ts_type.strip())
    if element and "array" in types:
        _check_value(file, schema, f"{pointer}/items", node["items"], element.group(1), decls, tagged, where)
        return
    assert bool(_NULL.search(ts_type)) == ("null" in types), f"{where}: nullability differs from the schema"
    base = _NULL.sub("", ts_type).strip()
    if "array" in types:
        assert base.endswith("[]"), f"{where}: the schema has an array, TypeScript has {ts_type}"
        _check_value(file, schema, f"{pointer}/items", node["items"], base[:-2], decls, tagged, where)
        return
    assert not base.endswith("[]"), f"{where}: TypeScript has an array, the schema does not"
    if _is_object(node) or _is_enum(node):
        want = tagged.get(f"{file}#{pointer}")
        assert want is not None, f"{where}: no TypeScript type is tagged {file}#{pointer}"
        assert base == want.name, f"{where}: {base} used where the schema node is mirrored by {want.name}"
    elif types - {"null"} == {"boolean"}:
        assert base == "boolean", f"{where}: {base} for a boolean"
    elif types - {"null"} <= {"integer", "number"}:
        assert base == "number", f"{where}: {base} for a number"
    else:
        assert types - {"null"} == {"string"}, f"{where}: unexpected schema type {types}"
        assert base in _string_aliases(decls), f"{where}: {base} for a string"


@pytest.mark.parametrize("file", SCHEMA_FILES)
def test_every_schema_object_and_enum_has_a_tagged_type(file, tagged):
    missing = [f"{file}#{pointer}" for pointer, node in _walk(load_schema(file.removesuffix(".schema.json")))
               if (_is_object(node) or _is_enum(node)) and f"{file}#{pointer}" not in tagged]
    assert missing == []


def test_every_tag_points_at_a_schema_node(tagged):
    for tag in tagged:
        file, _, pointer = tag.partition("#")
        assert file in SCHEMA_FILES, f"{tag}: no such schema"
        _node(load_schema(file.removesuffix(".schema.json")), pointer)


def test_tagged_interfaces_match_their_schema_objects(decls, tagged):
    checked = 0
    for tag, decl in tagged.items():
        file, _, pointer = tag.partition("#")
        schema = load_schema(file.removesuffix(".schema.json"))
        node = _node(schema, pointer)
        if decl.kind != "interface":
            continue
        assert _is_object(node), f"{decl.name} is tagged {tag}, which is not an object"
        props = node["properties"]
        assert sorted(decl.fields) == sorted(props), f"{decl.name} fields differ from {tag}"
        for field, (optional, ts_type) in decl.fields.items():
            # Every schema field is required, so an optional TypeScript field
            # would let the site treat a present key as possibly missing.
            assert not optional, f"{decl.name}.{field} is optional, but the schema requires it"
            _check_value(file, schema, f"{pointer}/properties/{field}", props[field], ts_type,
                         decls, tagged, f"{decl.name}.{field}")
            checked += 1
    assert checked > 50


def test_tagged_type_aliases_match_their_schema_nodes(decls, tagged):
    for tag, decl in tagged.items():
        if decl.kind != "type":
            continue
        file, _, pointer = tag.partition("#")
        schema = load_schema(file.removesuffix(".schema.json"))
        node = _node(schema, pointer)
        if _is_enum(node):
            literals = re.findall(r"'([^']*)'", decl.rhs)
            # Prettier writes a long union with a leading "|", so allow one.
            assert re.fullmatch(r"\s*(\|\s*)?'[^']*'(\s*\|\s*'[^']*')*\s*", decl.rhs), \
                f"{decl.name} is not a union of literals"
            assert sorted(literals) == sorted(v for v in node["enum"] if v is not None), \
                f"{decl.name} values differ from {tag}"
        else:
            _check_value(file, schema, pointer, node, decl.rhs, decls, tagged, decl.name)
