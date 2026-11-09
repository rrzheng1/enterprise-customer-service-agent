"""Offline installed-version checks for critical contracts and committed direct constraints."""
from importlib.metadata import version
from pathlib import Path
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def main():
    for filename in ["requirements.in", "constraints.txt"]:
        for line in (ROOT / filename).read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            assert Version(version(requirement.name)) in requirement.specifier, f"Incompatible dependency: {requirement.name}"
    assert Version("1.28") <= Version(version("mcp")) < Version("2")
    assert Version("1.18") <= Version(version("qdrant-client")) < Version("1.19")
    from langgraph.graph.state import CompiledStateGraph
    from inspect import signature
    assert "stream_mode" in signature(CompiledStateGraph.astream).parameters
    print("Installed dependencies satisfy committed constraints and MCP/Graph/Qdrant contracts")


if __name__ == "__main__":
    main()
