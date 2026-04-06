"""
Use case: агрегация Action-нод по лингвистической структуре.

Нормализация не зависит от порядка слов:
  norm_key = sha256(verb_lemma + "|" + sorted(subject) + "|" + sorted(object))[:16]
"""
import hashlib


def compute_norm_key(verb: str, subject: str | None, obj: str | None) -> str:
    """
    Вычисляет детерминированный ключ нормализации для Action-ноды.

    `verb` уже хранится как лемма. subject и object нормализуются
    через lowercase + сортировку токенов (инвариант к порядку слов).

    Возвращает 16-символьный hex-дайджест SHA-256.
    """
    def norm(t: str | None) -> str:
        if not t:
            return ""
        return " ".join(sorted(t.lower().strip().split()))

    key = f"{verb.lower().strip()}|{norm(subject)}|{norm(obj)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
