"""Optional persistence of finished lab3 summaries in sc-machine.

Uses the official py-sc-client WebSocket client. No summarization logic belongs
here; calling this module is optional and an unavailable server is nonfatal.
"""

from collections.abc import Mapping
import os
import warnings


DEFAULT_URL = "ws://localhost:8090/ws_json"

CLASSES = (
    "document", "summary", "sentence", "keyword", "sentence_score",
    "language", "subject_area",
)
RELATIONS = (
    "document_text", "summary", "sentence", "keyword", "sentence_score",
    "text", "index", "word", "weight", "score", "lexical_score",
    "position_document", "position_paragraph", "language", "subject_area", "value",
)


def _validate(result):
    if not isinstance(result, Mapping):
        raise ValueError("Ожидается словарь результата summarize()")
    if not isinstance(result.get("document"), str):
        raise ValueError("В результате отсутствует текст document")
    if not isinstance(result.get("summary"), list) or not isinstance(result.get("keywords"), list):
        raise ValueError("В результате отсутствуют списки summary и keywords")
    if not isinstance(result.get("sentence_scores"), list):
        raise ValueError("В результате отсутствует список sentence_scores")
    if not isinstance(result.get("language"), str) or not result["language"]:
        raise ValueError("В результате отсутствует язык; вызовите актуальный summarize()")


def _build_construction(result, keynodes, sc_type, ScConstruction,
                        ScLinkContent, ScLinkContentType):
    graph = ScConstruction()
    serial = 0

    def instance(alias, kind):
        graph.generate_node(sc_type.CONST_NODE, alias)
        graph.generate_connector(sc_type.CONST_PERM_POS_ARC, keynodes[f"class_{kind}"], alias)

    def relation(source, target, kind):
        nonlocal serial
        serial += 1
        connector = f"relation_arc_{serial}"
        graph.generate_connector(sc_type.CONST_COMMON_ARC, source, target, connector)
        graph.generate_connector(sc_type.CONST_PERM_POS_ARC, keynodes[f"nrel_{kind}"], connector)

    def value(owner, kind, content, content_type):
        nonlocal serial
        serial += 1
        alias = f"value_{serial}"
        graph.generate_link(sc_type.CONST_NODE_LINK,
                            ScLinkContent(content, content_type), alias)
        relation(owner, alias, kind)

    def text(owner, kind, content):
        value(owner, kind, str(content), ScLinkContentType.STRING)

    def integer(owner, kind, content):
        value(owner, kind, int(content), ScLinkContentType.INT)

    def number(owner, kind, content):
        value(owner, kind, float(content), ScLinkContentType.FLOAT)

    instance("document", "document")
    text("document", "document_text", result["document"])

    instance("summary", "summary")
    relation("document", "summary", "summary")
    for index, sentence in enumerate(result["summary"]):
        alias = f"summary_sentence_{index}"
        instance(alias, "sentence")
        relation("summary", alias, "sentence")
        integer(alias, "index", index)
        text(alias, "text", sentence)

    for index, keyword in enumerate(result["keywords"]):
        alias = f"keyword_{index}"
        instance(alias, "keyword")
        relation("document", alias, "keyword")
        text(alias, "word", keyword["word"])
        number(alias, "weight", keyword["weight"])

    for index, item in enumerate(result["sentence_scores"]):
        alias = f"sentence_score_{index}"
        instance(alias, "sentence_score")
        relation("document", alias, "sentence_score")
        integer(alias, "index", item["index"])
        text(alias, "text", item["sentence"])
        number(alias, "score", item["score"])
        number(alias, "lexical_score", item["lexical_score"])
        number(alias, "position_document", item["position_document"])
        number(alias, "position_paragraph", item["position_paragraph"])

    instance("language", "language")
    relation("document", "language", "language")
    text("language", "value", result["language"])

    if result.get("subject_area"):
        instance("subject_area", "subject_area")
        relation("document", "subject_area", "subject_area")
        text("subject_area", "value", result["subject_area"])

    return graph


def save_to_ostis(result: dict, url: str | None = None, *, strict: bool = False) -> bool:
    """Write one finished summary to sc-server; return False if unavailable.

    The default endpoint is ws://localhost:8090/ws_json and can be overridden
    with SC_SERVER_URL or the url argument. Set strict=True to raise failures.
    """
    _validate(result)
    endpoint = url or os.getenv("SC_SERVER_URL", DEFAULT_URL)
    connected = False
    disconnect = None
    try:
        from sc_client.client import (connect, disconnect, generate_elements,
                                      is_connected, resolve_keynodes)
        from sc_client.constants import sc_type
        from sc_client.models import (ScConstruction, ScIdtfResolveParams,
                                      ScLinkContent, ScLinkContentType)

        connect(endpoint)
        if not is_connected():
            raise ConnectionError(f"sc-server недоступен: {endpoint}")
        connected = True

        params = [ScIdtfResolveParams(idtf=f"eyazis_concept_{name}",
                                      type=sc_type.CONST_NODE_CLASS)
                  for name in CLASSES]
        params += [ScIdtfResolveParams(idtf=f"eyazis_nrel_{name}",
                                       type=sc_type.CONST_NODE_NON_ROLE)
                   for name in RELATIONS]
        addresses = resolve_keynodes(*params)
        if len(addresses) != len(params) or not all(addresses):
            raise RuntimeError("Не удалось создать ключевые узлы OSTIS")
        keynodes = {f"class_{name}": address for name, address in zip(CLASSES, addresses)}
        keynodes.update({f"nrel_{name}": address
                         for name, address in zip(RELATIONS, addresses[len(CLASSES):])})

        graph = _build_construction(result, keynodes, sc_type, ScConstruction,
                                    ScLinkContent, ScLinkContentType)
        created = generate_elements(graph)
        if not created or len(created) != len(graph.commands) or not all(created):
            raise RuntimeError("OSTIS не сохранил все элементы документа")
        return True
    except Exception as exc:
        if strict:
            raise RuntimeError(f"Не удалось сохранить результат в OSTIS: {exc}") from exc
        warnings.warn(f"OSTIS: результат не сохранён ({exc})", RuntimeWarning, stacklevel=2)
        return False
    finally:
        if connected and disconnect is not None:
            try:
                disconnect()
            except Exception as exc:
                # Cleanup must not invalidate a successfully computed summary.
                warnings.warn(f"OSTIS: соединение не закрыто ({exc})", RuntimeWarning,
                              stacklevel=2)
