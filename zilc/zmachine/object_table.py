"""
Z-machine object table builder.

Builds the object table with property defaults, object tree, and property tables.
"""

from typing import List, Dict, Any
import struct


class ObjectTable:
    """Builds Z-machine object table."""

    def __init__(self, version: int = 3):
        self.version = version
        self.objects: List[Dict[str, Any]] = []
        self.property_defaults = [0] * (31 if version <= 3 else 63)

    def add_object(self, name: str, parent: int = 0, sibling: int = 0,
                   child: int = 0, attributes: int = 0,
                   properties: Dict[int, Any] = None):
        """Add an object to the table."""
        self.objects.append({
            'name': name,
            'parent': parent,
            'sibling': sibling,
            'child': child,
            'attributes': attributes,
            'properties': properties or {}
        })

    def build(self) -> bytes:
        """Build object table bytes."""
        result = bytearray()

        # Property defaults table
        for default in self.property_defaults:
            result.extend(struct.pack('>H', default))

        # Object tree
        for obj in self.objects:
            if self.version <= 3:
                # V1-3: 9 bytes per object
                # 4 bytes attributes
                result.extend(struct.pack('>I', obj['attributes']))
                # 1 byte parent, sibling, child
                result.append(obj['parent'] & 0xFF)
                result.append(obj['sibling'] & 0xFF)
                result.append(obj['child'] & 0xFF)
                # 2 bytes property table address (placeholder)
                result.extend(struct.pack('>H', 0))
            else:
                # V4+: 14 bytes per object
                # 6 bytes attributes (48 bits)
                attr_bytes = struct.pack('>Q', obj['attributes'])[-6:]  # Last 6 bytes
                result.extend(attr_bytes)
                # 2 bytes each: parent, sibling, child
                result.extend(struct.pack('>H', obj['parent']))
                result.extend(struct.pack('>H', obj['sibling']))
                result.extend(struct.pack('>H', obj['child']))
                # 2 bytes property table address (placeholder)
                result.extend(struct.pack('>H', 0))

        return bytes(result)
