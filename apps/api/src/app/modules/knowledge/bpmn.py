"""BPMN 2.0 XML export (docs/06 M2).

Diagrams are data, deterministically rendered from the PKM graph — the
LLM proposed the graph during extraction; drawing it is not an LLM job
(docs/03 §5). The XML interoperates with Visio, Camunda, Signavio,
bpmn.io. Layout: columns by sequence order, lanes by actor.
"""

import uuid
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

NODE_W, NODE_H = 160, 70
COL_GAP, LANE_H = 220, 140
LANE_X, LANE_LABEL_W = 40, 30


@dataclass
class GraphNode:
    id: str
    name: str
    step_type: str
    order: int
    lane: str
    pain_points: list[dict]


@dataclass
class GraphEdge:
    from_id: str
    to_id: str


def build_bpmn(process_name: str, nodes: list[GraphNode], edges: list[GraphEdge]) -> str:
    lanes = sorted({n.lane for n in nodes}) or ["Unassigned"]
    lane_index = {lane: i for i, lane in enumerate(lanes)}
    pid = f"Process_{uuid.uuid4().hex[:8]}"

    def el(parent, tag, ns=BPMN_NS, **attrs):
        node = ET.SubElement(parent, f"{{{ns}}}{tag}")
        for key, value in attrs.items():
            node.set(key, value)
        return node

    definitions = ET.Element(
        f"{{{BPMN_NS}}}definitions",
        {"targetNamespace": "https://atc.example/bpmn", "exporter": "AI Transformation Copilot"},
    )
    process = el(definitions, "process", id=pid, name=escape(process_name),
                 isExecutable="false")

    lane_set = el(process, "laneSet", id=f"LaneSet_{pid}")
    lane_els = {}
    for lane in lanes:
        lane_els[lane] = el(lane_set, "lane", id=f"Lane_{lane_index[lane]}",
                            name=escape(lane))

    for node in nodes:
        task = el(process, "userTask" if node.step_type == "manual" else
                  "exclusiveGateway" if node.step_type == "decision" else "task",
                  id=f"n{node.id.replace('-', '')}", name=escape(node.name[:80]))
        if node.pain_points:
            doc = el(task, "documentation")
            doc.text = "Pain points: " + "; ".join(
                p.get("name", "")[:100] for p in node.pain_points
            )
        el(lane_els[node.lane], "flowNodeRef").text = f"n{node.id.replace('-', '')}"

    for i, edge in enumerate(edges):
        el(process, "sequenceFlow", id=f"flow_{i}",
           sourceRef=f"n{edge.from_id.replace('-', '')}",
           targetRef=f"n{edge.to_id.replace('-', '')}")

    # Diagram interchange: simple deterministic grid.
    diagram = el(definitions, "BPMNDiagram", ns=BPMNDI_NS, id="Diagram_1")
    plane = el(diagram, "BPMNPlane", ns=BPMNDI_NS, id="Plane_1", bpmnElement=pid)

    max_order = max((n.order for n in nodes), default=0)
    for lane in lanes:
        shape = el(plane, "BPMNShape", ns=BPMNDI_NS,
                   id=f"Lane_{lane_index[lane]}_di",
                   bpmnElement=f"Lane_{lane_index[lane]}", isHorizontal="true")
        el(shape, "Bounds", ns=DC_NS, x=str(LANE_X),
           y=str(40 + lane_index[lane] * LANE_H),
           width=str(LANE_LABEL_W + (max_order + 1) * COL_GAP + 60),
           height=str(LANE_H))
    for node in nodes:
        shape = el(plane, "BPMNShape", ns=BPMNDI_NS,
                   id=f"n{node.id.replace('-', '')}_di",
                   bpmnElement=f"n{node.id.replace('-', '')}")
        el(shape, "Bounds", ns=DC_NS,
           x=str(LANE_X + LANE_LABEL_W + 40 + node.order * COL_GAP),
           y=str(40 + lane_index[node.lane] * LANE_H + (LANE_H - NODE_H) // 2),
           width=str(NODE_W), height=str(NODE_H))

    ET.register_namespace("bpmn", BPMN_NS)
    ET.register_namespace("bpmndi", BPMNDI_NS)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("di", DI_NS)
    return ET.tostring(definitions, encoding="unicode", xml_declaration=True)
