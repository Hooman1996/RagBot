"""Canonical datasource-to-prompt-category behavior shared by all executors."""

import hashlib


def get_document_category(doc_name: str) -> str:
    if "قرارداد" in doc_name:
        return "قرارداد ها"
    if "ابلاغیه" in doc_name:
        return "ابلاغیه ها"
    if "FAQ" in doc_name:
        return "FAQ"
    digest = hashlib.md5(doc_name.encode()).hexdigest()
    return "قرارداد ها" if int(digest[0], 16) < 8 else "ابلاغیه ها"

