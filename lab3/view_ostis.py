"""Read lab 3 records directly from sc-server for a small OSTIS demo."""

import argparse
import json
import os
import sys

from .ostis_client import DEFAULT_URL


def _search(template):
    from sc_client.client import search_by_template

    return search_by_template(template)


def _documents(class_addr):
    from sc_client.constants import sc_type
    from sc_client.models import ScTemplate

    template = ScTemplate()
    template.triple(class_addr, sc_type.VAR_PERM_POS_ARC,
                    (sc_type.VAR_NODE, "document"))
    return [match.get("document") for match in _search(template)]


def _targets(source, relation_addr, *, link=False):
    from sc_client.constants import sc_type
    from sc_client.models import ScTemplate

    template = ScTemplate()
    target_type = sc_type.VAR_NODE_LINK if link else sc_type.VAR_NODE
    template.quintuple(source, sc_type.VAR_COMMON_ARC,
                       (target_type, "target"), sc_type.VAR_PERM_POS_ARC,
                       relation_addr)
    return [match.get("target") for match in _search(template)]


def _property(source, relation_addr, default=None):
    from sc_client.client import get_link_content

    links = _targets(source, relation_addr, link=True)
    if not links:
        return default
    contents = get_link_content(links[0])
    return contents[0].data if contents else default


def _record(addr, relations, *, full=False):
    prop = lambda node, name, default=None: _property(node, relations[name], default)
    record = {
        "sc_addr": addr.value,
        "document": prop(addr, "document_text", ""),
        "summary": [],
        "keywords": [],
        "sentence_scores_count": 0,
        "language": None,
        "subject_area": None,
    }

    for summary in _targets(addr, relations["summary"]):
        sentences = [
            (int(prop(node, "index", 0)), prop(node, "text", ""))
            for node in _targets(summary, relations["sentence"])
        ]
        record["summary"] = [text for _, text in sorted(sentences)]

    for keyword in _targets(addr, relations["keyword"]):
        record["keywords"].append({
            "word": prop(keyword, "word", ""),
            "weight": float(prop(keyword, "weight", 0)),
        })
    record["keywords"].sort(key=lambda item: -item["weight"])

    scores = _targets(addr, relations["sentence_score"])
    record["sentence_scores_count"] = len(scores)
    if full:
        record["sentence_scores"] = sorted(({
            "index": int(prop(node, "index", 0)),
            "sentence": prop(node, "text", ""),
            "score": float(prop(node, "score", 0)),
            "lexical_score": float(prop(node, "lexical_score", 0)),
            "position_document": float(prop(node, "position_document", 0)),
            "position_paragraph": float(prop(node, "position_paragraph", 0)),
        } for node in scores), key=lambda item: item["index"])

    for name in ("language", "subject_area"):
        nodes = _targets(addr, relations[name])
        if nodes:
            record[name] = prop(nodes[0], "value")
    return record


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="View lab 3 records stored in OSTIS")
    parser.add_argument("--document", type=int, metavar="SC_ADDR",
                        help="show a document with this OSTIS address")
    parser.add_argument("--scores", action="store_true",
                        help="include all sentence scores with --document")
    parser.add_argument("--url", default=os.getenv("SC_SERVER_URL", DEFAULT_URL),
                        help="sc-server WebSocket URL")
    args = parser.parse_args(argv)

    from sc_client.client import connect, disconnect, is_connected, resolve_keynodes
    from sc_client.models import ScIdtfResolveParams
    from .ostis_client import RELATIONS

    connected = False
    try:
        connect(args.url)
        if not is_connected():
            raise ConnectionError(f"sc-server is unavailable: {args.url}")
        connected = True
        names = ["eyazis_concept_document"] + [f"eyazis_nrel_{name}" for name in RELATIONS]
        addresses = resolve_keynodes(*(ScIdtfResolveParams(idtf=name, type=None)
                                       for name in names))
        if not addresses or not addresses[0]:
            print("No lab 3 documents have been saved in OSTIS yet.")
            return 0
        relations = dict(zip(RELATIONS, addresses[1:]))
        if not all(relations.values()):
            raise RuntimeError("The lab 3 OSTIS relations are incomplete")
        documents = _documents(addresses[0])

        if args.document is None:
            if not documents:
                print("No lab 3 documents have been saved in OSTIS yet.")
            for addr in documents:
                content = _property(addr, relations["document_text"], "")
                print(f"{addr.value}: {content[:100].replace(chr(10), ' ')}")
            return 0

        selected = next((addr for addr in documents if addr.value == args.document), None)
        if selected is None:
            raise ValueError(f"Document {args.document} was not found in OSTIS")
        print(json.dumps(_record(selected, relations, full=args.scores),
                         ensure_ascii=False, indent=2))
        return 0
    finally:
        if connected:
            disconnect()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"OSTIS read failed: {exc}", file=sys.stderr)
        sys.exit(1)
