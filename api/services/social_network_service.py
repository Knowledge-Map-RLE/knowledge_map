"""
Layer: Services
Package: services.social_network_service
Responsibility: Социальная сеть: чаты-обсуждения (статьи, триплеты, профили,
сообщества) с лайками и ответами, друзья, сообщества, тренды, уведомления,
жалобы. Сырые Cypher-запросы через neomodel db (паттерн article_editor_service).
"""
import base64
import json
import logging
import mimetypes
import os
from datetime import datetime, timezone
from typing import Any, Optional

from neomodel import db

from services import get_s3_client, settings
from src.uuid8 import uuid8_str, uuid8_timestamp

logger = logging.getLogger(__name__)

_TARGET_TYPES = {"article", "statement", "user", "community"}

_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tif", ".tiff",
}


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _loads(data: Any) -> dict:
    if not data:
        return {}
    if isinstance(data, dict):
        return data
    try:
        return json.loads(data)
    except (TypeError, ValueError):
        return {}


def _dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _encode_contacts(contacts: Any) -> dict:
    """Обфусцирует контакты (base64) в API-ответах.

    Хранится открытым текстом в Neo4j, наружу отдаётся base64: массовые
    краулеры не могут собрать контакты простым парсингом HTML/JSON — значение
    расшифровывается в браузере JS-клиентом перед отрисовкой.
    """
    if not isinstance(contacts, dict):
        return {}
    encoded: dict[str, str] = {}
    for key, value in contacts.items():
        raw = str(value).strip()
        if not raw:
            continue
        encoded[str(key)] = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return encoded


def _row_user(row) -> dict:
    """Преобразует запись User в словарь профиля."""
    n = row.get("n")
    if n is None:
        n = row.get("u")
    if n is None:
        n = row.get("user")
    if n is None:
        return {}
    data = _loads(n.get("data"))
    return {
        "uid": n.get("uid", ""),
        "login": n.get("login", ""),
        "nickname": n.get("nickname", ""),
        "bio": data.get("bio", ""),
        "avatar_key": data.get("avatar_key", ""),
        "contacts": _encode_contacts(data.get("contacts")),
    }


class SocialNetworkService:
    # ── Пользователи ──────────────────────────────────────────────────────────

    def ensure_user(self, user: dict) -> dict:
        """Создаёт (MERGE) узел User в Neo4j по данным авторизации.

        Существующий узел никогда не затирается пустыми значениями: login/nickname
        обновляются только когда в данных авторизации пришли непустые значения
        (внутренние вызовы с partial-dict вида {"uid": ...} не должны стирать имя).
        """
        uid = user.get("uid")
        if not uid:
            return {}
        login = str(user.get("login", "") or "").strip()
        nickname = str(user.get("nickname", "") or "").strip()
        results, _ = db.cypher_query(
            "MATCH (u:User {uid: $uid}) RETURN u",
            {"uid": uid},
        )
        existing = results[0][0] if results else None
        if existing is None:
            db.cypher_query(
                "CREATE (u:User {uid: $uid, login: $login, nickname: $nickname, data: '{}'})",
                {"uid": uid, "login": login, "nickname": nickname},
            )
            return _row_user({"n": {
                "uid": uid,
                "login": login,
                "nickname": nickname,
            }})
        set_clause = []
        params: dict = {"uid": uid}
        if login:
            set_clause.append("u.login = $login")
            params["login"] = login
        if nickname:
            set_clause.append("u.nickname = $nickname")
            params["nickname"] = nickname
        if set_clause:
            db.cypher_query(
                f"MATCH (u:User {{uid: $uid}}) SET {', '.join(set_clause)}",
                params,
            )
        return _row_user({"n": existing})

    def get_user(self, uid: str) -> Optional[dict]:
        results, _ = db.cypher_query(
            "MATCH (u:User {uid: $uid}) RETURN u",
            {"uid": uid},
        )
        return _row_user({"n": results[0][0]}) if results else None

    def search_users(self, query: str, limit: int = 20) -> list[dict]:
        q = f"%{query.strip()}%"
        results, _ = db.cypher_query(
            "MATCH (u:User) WHERE toLower(u.nickname) CONTAINS toLower($q) "
            "OR toLower(u.login) CONTAINS toLower($q) "
            "RETURN u ORDER BY u.nickname LIMIT $limit",
            {"q": q, "limit": limit},
        )
        return [_row_user({"n": r[0]}) for r in results]

    def update_profile(
        self,
        uid: str,
        bio: Optional[str] = None,
        avatar_key: Optional[str] = None,
        contacts: Optional[dict] = None,
    ) -> dict:
        results, _ = db.cypher_query(
            "MATCH (u:User {uid: $uid}) RETURN u",
            {"uid": uid},
        )
        if not results:
            return {"success": False, "error": "user_not_found"}
        node = results[0][0]
        data = _loads(node.get("data"))
        if bio is not None:
            data["bio"] = bio
        if avatar_key is not None:
            data["avatar_key"] = avatar_key
        if contacts is not None:
            if not isinstance(contacts, dict):
                return {"success": False, "error": "bad_contacts"}
            data["contacts"] = {
                str(k): str(v).strip()
                for k, v in contacts.items()
                if v is not None and str(v).strip()
            }
        db.cypher_query(
            "MATCH (u:User {uid: $uid}) SET u.data = $data",
            {"uid": uid, "data": _dumps(data)},
        )
        profile = _row_user({"n": node})
        profile["bio"] = data.get("bio", "")
        profile["avatar_key"] = data.get("avatar_key", "")
        profile["contacts"] = _encode_contacts(data.get("contacts"))
        return {"success": True, "profile": profile}

    # ── Друзья ────────────────────────────────────────────────────────────────

    def _friend_relation(self, a: str, b: str) -> bool:
        results, _ = db.cypher_query(
            "MATCH (a:User {uid: $a})-[:FRIEND]-(b:User {uid: $b}) RETURN count(*) AS c",
            {"a": a, "b": b},
        )
        return bool(results and results[0][0] > 0)

    def add_friend(self, a: str, b: str) -> dict:
        self.ensure_user({"uid": a})
        self.ensure_user({"uid": b})
        if a == b:
            return {"success": False, "error": "self_friend"}
        if self._friend_relation(a, b):
            return {"success": True, "is_friend": True}
        db.cypher_query(
            "MATCH (a:User {uid: $a}), (b:User {uid: $b}) "
            "CREATE (a)-[:FRIEND {created_at: $ts}]->(b) "
            "CREATE (a)<-[:FRIEND {created_at: $ts}]-(b)",
            {"a": a, "b": b, "ts": _now()},
        )
        self._notify(b, "friend_request", "user", a,
                     "Вас добавили в друзья")
        return {"success": True, "is_friend": True}

    def remove_friend(self, a: str, b: str) -> dict:
        db.cypher_query(
            "MATCH (a:User {uid: $a})-[r:FRIEND]-(b:User {uid: $b}) DELETE r",
            {"a": a, "b": b},
        )
        return {"success": True, "is_friend": False}

    def list_friends(self, uid: str, limit: int = 200) -> list[dict]:
        results, _ = db.cypher_query(
            "MATCH (u:User {uid: $uid})-[:FRIEND]->(f:User) "
            "RETURN f ORDER BY f.nickname LIMIT $limit",
            {"uid": uid, "limit": limit},
        )
        return [_row_user({"n": r[0]}) for r in results]

    # ── Сообщества ────────────────────────────────────────────────────────────

    def list_owned_communities(self, owner_uid: str) -> list[dict]:
        results, _ = db.cypher_query(
            "MATCH (c:Community {created_by_uid: $uid}) "
            "OPTIONAL MATCH (m:User)-[:MEMBER]->(c) "
            "WITH c, count(m) AS members "
            "RETURN c, members ORDER BY c.name",
            {"uid": owner_uid},
        )
        communities = [{
            "uid": r[0].get("uid", ""),
            "name": r[0].get("name", ""),
            "description": r[0].get("description", ""),
            "member_count": r[1],
            "created_by_uid": owner_uid,
        } for r in results]
        self._add_member_flags(communities, owner_uid)
        return communities

    def create_community(self, owner_uid: str, name: str, description: str = "") -> dict:
        uid = uuid8_str()
        db.cypher_query(
            "CREATE (c:Community {uid: $uid, name: $name, description: $description, "
            "created_by_uid: $owner, created_at: $ts})",
            {"uid": uid, "name": name, "description": description,
             "owner": owner_uid, "ts": _now()},
        )
        self.ensure_user({"uid": owner_uid})
        db.cypher_query(
            "MATCH (u:User {uid: $owner}), (c:Community {uid: $uid}) "
            "CREATE (u)-[:MEMBER {created_at: $ts, role: 'owner'}]->(c)",
            {"owner": owner_uid, "uid": uid, "ts": _now()},
        )
        return self.get_community(uid) or {"uid": uid, "name": name}

    def _add_member_flags(self, communities: list[dict], viewer_uid: Optional[str]) -> None:
        if not viewer_uid or not communities:
            return
        member_set = {c["uid"] for c in self.list_communities_member_of(viewer_uid)}
        for c in communities:
            c["is_member"] = c["uid"] in member_set

    def list_communities(self, limit: int = 100, viewer_uid: Optional[str] = None) -> list[dict]:
        results, _ = db.cypher_query(
            "MATCH (c:Community) OPTIONAL MATCH (m:User)-[:MEMBER]->(c) "
            "RETURN c, count(m) AS members "
            "ORDER BY members DESC, c.name LIMIT $limit",
            {"limit": limit},
        )
        communities = [{
            "uid": r[0].get("uid", ""),
            "name": r[0].get("name", ""),
            "description": r[0].get("description", ""),
            "member_count": r[1],
            "created_by_uid": r[0].get("created_by_uid", ""),
        } for r in results]
        self._add_member_flags(communities, viewer_uid)
        return communities

    def search_communities(self, query: str, limit: int = 20, viewer_uid: Optional[str] = None) -> list[dict]:
        q = f"%{query.strip()}%"
        results, _ = db.cypher_query(
            "MATCH (c:Community) WHERE toLower(c.name) CONTAINS toLower($q) "
            "OR toLower(coalesce(c.description, '')) CONTAINS toLower($q) "
            "OPTIONAL MATCH (m:User)-[:MEMBER]->(c) "
            "WITH c, count(DISTINCT m) AS members "
            "RETURN c, members ORDER BY members DESC, c.name LIMIT $limit",
            {"q": q, "limit": limit},
        )
        communities = [{
            "uid": r[0].get("uid", ""),
            "name": r[0].get("name", ""),
            "description": r[0].get("description", ""),
            "member_count": r[1],
            "created_by_uid": r[0].get("created_by_uid", ""),
        } for r in results]
        self._add_member_flags(communities, viewer_uid)
        return communities

    def get_community(self, uid: str, viewer_uid: Optional[str] = None) -> Optional[dict]:
        results, _ = db.cypher_query(
            "MATCH (c:Community {uid: $uid}) OPTIONAL MATCH (m:User)-[:MEMBER]->(c) "
            "RETURN c, count(m) AS members",
            {"uid": uid},
        )
        if not results:
            return None
        r = results[0]
        members, _ = db.cypher_query(
            "MATCH (c:Community {uid: $uid})<-[:MEMBER]-(u:User) "
            "RETURN u ORDER BY u.nickname",
            {"uid": uid},
        )
        owner_uid = r[0].get("created_by_uid", "")
        community = {
            "uid": r[0].get("uid", ""),
            "name": r[0].get("name", ""),
            "description": r[0].get("description", ""),
            "member_count": r[1],
            "created_by_uid": owner_uid,
            "members": [_row_user({"n": m[0]}) for m in members],
        }
        if viewer_uid:
            community["is_member"] = self._is_member(viewer_uid, uid)
            community["is_owner"] = viewer_uid == owner_uid
        return community

    def _is_member(self, user_uid: str, community_uid: str) -> bool:
        results, _ = db.cypher_query(
            "MATCH (u:User {uid: $u})-[:MEMBER]->(c:Community {uid: $c}) RETURN count(*) AS c",
            {"u": user_uid, "c": community_uid},
        )
        return bool(results and results[0][0] > 0)

    def join_community(self, user_uid: str, community_uid: str) -> dict:
        self.ensure_user({"uid": user_uid})
        comm = self.get_community(community_uid)
        if comm is None:
            return {"success": False, "error": "community_not_found"}
        if self._is_member(user_uid, community_uid):
            return {"success": True, "is_member": True}
        db.cypher_query(
            "MATCH (u:User {uid: $u}), (c:Community {uid: $c}) "
            "CREATE (u)-[:MEMBER {created_at: $ts, role: 'member'}]->(c)",
            {"u": user_uid, "c": community_uid, "ts": _now()},
        )
        if comm.get("created_by_uid") and comm["created_by_uid"] != user_uid:
            self._notify(comm["created_by_uid"], "community_join", "community", community_uid,
                         "В ваше сообщество вступил новый участник")
        return {"success": True, "is_member": True}

    def leave_community(self, user_uid: str, community_uid: str) -> dict:
        db.cypher_query(
            "MATCH (u:User {uid: $u})-[r:MEMBER]->(c:Community {uid: $c}) DELETE r",
            {"u": user_uid, "c": community_uid},
        )
        return {"success": True, "is_member": False}

    def update_community(
        self,
        owner_uid: str,
        community_uid: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Обновляет название/описание сообщества (только владелец)."""
        results, _ = db.cypher_query(
            "MATCH (c:Community {uid: $uid}) RETURN c.created_by_uid",
            {"uid": community_uid},
        )
        if not results:
            return {"success": False, "error": "community_not_found"}
        if results[0][0] != owner_uid:
            return {"success": False, "error": "forbidden"}
        if name is not None:
            name = name.strip()
            if not name:
                return {"success": False, "error": "empty_name"}
            db.cypher_query(
                "MATCH (c:Community {uid: $uid}) SET c.name = $name",
                {"uid": community_uid, "name": name},
            )
        if description is not None:
            db.cypher_query(
                "MATCH (c:Community {uid: $uid}) SET c.description = $description",
                {"uid": community_uid, "description": description.strip()},
            )
        return {"success": True, "community": self.get_community(community_uid) or {}}

    def delete_community(self, owner_uid: str, community_uid: str) -> dict:
        """Удаляет сообщество и связанные обсуждения (только владелец)."""
        results, _ = db.cypher_query(
            "MATCH (c:Community {uid: $uid}) RETURN c.created_by_uid",
            {"uid": community_uid},
        )
        if not results:
            return {"success": False, "error": "community_not_found"}
        if results[0][0] != owner_uid:
            return {"success": False, "error": "forbidden"}
        db.cypher_query(
            "MATCH (m:ChatMessage {target_type: 'community', target_uid: $uid}) DETACH DELETE m",
            {"uid": community_uid},
        )
        db.cypher_query(
            "MATCH (n:Notification {target_type: 'community', target_uid: $uid}) DETACH DELETE n",
            {"uid": community_uid},
        )
        db.cypher_query(
            "MATCH (c:Community {uid: $uid}) DETACH DELETE c",
            {"uid": community_uid},
        )
        return {"success": True}

    # ── Чат ───────────────────────────────────────────────────────────────────

    def _target_label(self, target_type: str, target_uid: str) -> str:
        """Человекочитаемое имя цели обсуждения."""
        try:
            if target_type == "article":
                results, _ = db.cypher_query(
                    "MATCH (d:Document {uid: $uid}) RETURN coalesce(d.title, d.original_filename, '')",
                    {"uid": target_uid},
                )
                return results[0][0] if results else target_uid
            if target_type == "statement":
                results, _ = db.cypher_query(
                    "MATCH (s:KnowledgeStatement {uid: $uid}) "
                    "RETURN coalesce(s.subject_text, '') + ' ' + coalesce(s.predicate, '') "
                    "+ ' ' + coalesce(s.object_text, '')",
                    {"uid": target_uid},
                )
                return results[0][0] if results else target_uid
            if target_type == "community":
                results, _ = db.cypher_query(
                    "MATCH (c:Community {uid: $uid}) RETURN c.name",
                    {"uid": target_uid},
                )
                return results[0][0] if results else target_uid
            if target_type == "user":
                results, _ = db.cypher_query(
                    "MATCH (u:User {uid: $uid}) RETURN coalesce(u.nickname, u.login)",
                    {"uid": target_uid},
                )
                return results[0][0] if results else target_uid
        except Exception as e:  # noqa: BLE001
            logger.warning("social: target label error %s: %s", target_type, e)
        return target_uid

    def send_message(
        self,
        author: dict,
        target_type: str,
        target_uid: str,
        text: str,
        parent_uid: Optional[str] = None,
        references: Optional[list[dict]] = None,
    ) -> dict:
        if target_type not in _TARGET_TYPES:
            return {"success": False, "error": "bad_target_type"}
        if not text or not text.strip():
            return {"success": False, "error": "empty_text"}
        author_uid = author.get("uid", "")
        author_info = self.ensure_user(author)
        author_nickname = author_info.get("nickname", "") or str(author.get("nickname", "") or "").strip()
        author_login = author_info.get("login", "") or str(author.get("login", "") or "").strip()
        uid = uuid8_str()
        ts = _now()
        refs = [
            {
                "uid": str(r.get("uid", "")),
                "type": str(r.get("type", "")),
                "label": str(r.get("label", "")),
                "block_type": r.get("block_type"),
                "order": r.get("order"),
                "data": r.get("data") or {},
            }
            for r in (references or [])
            if r.get("uid")
        ]
        db.cypher_query(
            "CREATE (m:ChatMessage {uid: $uid, target_type: $tt, target_uid: $tu, "
            "author_uid: $au, author_nickname: $an, author_login: $al, "
            "text: $text, parent_uid: $pu, references: $refs, "
            "created_at: $ts, updated_at: $ts})",
            {"uid": uid, "tt": target_type, "tu": target_uid, "au": author_uid,
             "an": author_nickname, "al": author_login,
             "text": text.strip(), "pu": parent_uid or "", "refs": _dumps(refs), "ts": ts},
        )
        message = {
            "uid": uid,
            "target_type": target_type,
            "target_uid": target_uid,
            "author_uid": author_uid,
            "author_nickname": author_nickname,
            "author_login": author_login,
            "text": text.strip(),
            "parent_uid": parent_uid or "",
            "references": refs,
            "like_count": 0,
            "reply_count": 0,
            "liked_by_me": False,
            "created_at": ts,
        }
        # Уведомления
        if parent_uid:
            results, _ = db.cypher_query(
                "MATCH (p:ChatMessage {uid: $uid}) RETURN p.author_uid",
                {"uid": parent_uid},
            )
            if results and results[0][0] != author_uid:
                self._notify(results[0][0], "reply", "chat", uid,
                             "Вам ответили в обсуждении")
        elif target_type == "user" and target_uid != author_uid:
            self._notify(target_uid, "chat_message", "chat", uid,
                         "Вам написали сообщение")
        elif target_type == "community":
            results, _ = db.cypher_query(
                "MATCH (u:User)-[:MEMBER]->(c:Community {uid: $uid}) "
                "WHERE u.uid <> $au RETURN u.uid",
                {"uid": target_uid, "au": author_uid},
            )
            for row in results:
                self._notify(row[0], "community_message", "chat", uid,
                             "Новое сообщение в сообществе")
        return {"success": True, "message": message}

    def get_messages(
        self,
        target_type: str,
        target_uid: str,
        viewer_uid: Optional[str] = None,
        before: Optional[float] = None,
        limit: int = 50,
    ) -> dict:
        """Сообщения обсуждения (по убыванию времени, до курсора before)."""
        if target_type not in _TARGET_TYPES:
            return {"success": False, "error": "bad_target_type"}
        params: dict = {"tt": target_type, "tu": target_uid, "limit": limit}
        extra = ""
        if before:
            extra = "AND m.created_at < $before"
            params["before"] = before
        results, _ = db.cypher_query(
            "MATCH (m:ChatMessage {target_type: $tt, target_uid: $tu}) "
            f"WHERE m.created_at IS NOT NULL {extra} "
            "WITH m ORDER BY m.created_at DESC LIMIT $limit "
            "OPTIONAL MATCH (liker:User)-[:LIKES]->(m) "
            "OPTIONAL MATCH (rep:ChatMessage {parent_uid: m.uid}) "
            "WITH m, count(DISTINCT liker) AS likes, count(DISTINCT rep) AS replies "
            "ORDER BY m.created_at DESC "
            "RETURN m, likes, replies",
            params,
        )
        author_uids = {r[0].get("author_uid", "") for r in results}
        authors: dict[str, dict] = {}
        if author_uids:
            a_res, _ = db.cypher_query(
                "MATCH (u:User) WHERE u.uid IN $uids RETURN u",
                {"uids": list(author_uids)},
            )
            for row in a_res:
                p = _row_user({"n": row[0]})
                authors[p["uid"]] = p
        liked = set()
        if viewer_uid:
            l_res, _ = db.cypher_query(
                "MATCH (u:User {uid: $uid})-[:LIKES]->(m:ChatMessage) "
                "WHERE m.target_type = $tt AND m.target_uid = $tu RETURN m.uid",
                {"uid": viewer_uid, "tt": target_type, "tu": target_uid},
            )
            liked = {r[0] for r in l_res}
        messages = []
        for r in results:
            node, likes, replies = r[0], r[1], r[2]
            au = node.get("author_uid", "")
            author = authors.get(au, {})
            messages.append({
                "uid": node.get("uid", ""),
                "target_type": target_type,
                "target_uid": target_uid,
                "author_uid": au,
                "author_nickname": author.get("nickname") or node.get("author_nickname") or "",
                "author_login": author.get("login") or node.get("author_login") or "",
                "text": node.get("text", ""),
                "parent_uid": node.get("parent_uid", "") or "",
                "references": _loads(node.get("references")) or [],
                "like_count": likes,
                "reply_count": replies,
                "liked_by_me": node.get("uid", "") in liked,
                "created_at": node.get("created_at") or 0,
            })
        return {"success": True, "messages": messages, "total": len(messages)}

    def toggle_like(self, user_uid: str, message_uid: str) -> dict:
        results, _ = db.cypher_query(
            "MATCH (m:ChatMessage {uid: $uid}) RETURN m",
            {"uid": message_uid},
        )
        if not results:
            return {"success": False, "error": "message_not_found"}
        self.ensure_user({"uid": user_uid})
        exists, _ = db.cypher_query(
            "MATCH (u:User {uid: $u})-[:LIKES]->(m:ChatMessage {uid: $m}) RETURN count(*) AS c",
            {"u": user_uid, "m": message_uid},
        )
        is_liked = bool(exists and exists[0][0] > 0)
        if is_liked:
            db.cypher_query(
                "MATCH (u:User {uid: $u})-[r:LIKES]->(m:ChatMessage {uid: $m}) DELETE r",
                {"u": user_uid, "m": message_uid},
            )
        else:
            db.cypher_query(
                "MATCH (u:User {uid: $u}), (m:ChatMessage {uid: $m}) "
                "CREATE (u)-[:LIKES {created_at: $ts}]->(m)",
                {"u": user_uid, "m": message_uid, "ts": _now()},
            )
            results, _ = db.cypher_query(
                "MATCH (m:ChatMessage {uid: $m}) RETURN m.author_uid",
                {"m": message_uid},
            )
            if results and results[0][0] != user_uid:
                self._notify(results[0][0], "like", "chat", message_uid,
                             "Ваше сообщение понравилось пользователю")
        count, _ = db.cypher_query(
            "MATCH (:User)-[:LIKES]->(m:ChatMessage {uid: $m}) RETURN count(*) AS c",
            {"m": message_uid},
        )
        return {"success": True, "liked": not is_liked,
                "like_count": count[0][0] if count else 0}

    # ── Стена профиля ─────────────────────────────────────────────────────────

    def get_wall(self, target_uid: str, viewer_uid: Optional[str] = None, limit: int = 50) -> Optional[dict]:
        """Посты стены пользователя с комментариями под ними.

        Посты создаёт только владелец стены; комментарии — любой авторизованный.
        Время формируется из UUIDv8 (uid) записей. Возвращает None, если
        пользователь с target_uid не существует.
        """
        if self.get_user(target_uid) is None:
            return None
        results, _ = db.cypher_query(
            "MATCH (p:WallPost {owner_uid: $uid}) "
            "OPTIONAL MATCH (c:WallComment {post_uid: p.uid}) "
            "WITH p, count(c) AS comments "
            "RETURN p, comments ORDER BY p.uid DESC LIMIT $limit",
            {"uid": target_uid, "limit": limit},
        )
        posts = []
        for r in results:
            node, comment_count = r[0], r[1]
            posts.append({
                "uid": node.get("uid", ""),
                "owner_uid": node.get("owner_uid", ""),
                "text": node.get("text", ""),
                "created_at": uuid8_timestamp(node.get("uid", "")),
                "comment_count": comment_count,
                "comments": [],
            })
        self._attach_wall_comments(posts)
        return {"success": True, "posts": posts, "total": len(posts)}

    def _attach_wall_comments(self, posts: list[dict]) -> None:
        """Заполняет posts[*]["comments"] (по возрастанию времени — UUIDv8
        упорядочен) и обновляет nick/login авторов из актуальных данных User."""
        post_uids = [p["uid"] for p in posts]
        if not post_uids:
            return
        c_res, _ = db.cypher_query(
            "MATCH (c:WallComment) WHERE c.post_uid IN $uids "
            "RETURN c ORDER BY c.uid ASC",
            {"uids": post_uids},
        )
        by_post: dict[str, list[dict]] = {}
        for row in c_res:
            node = row[0]
            by_post.setdefault(node.get("post_uid", ""), []).append({
                "uid": node.get("uid", ""),
                "post_uid": node.get("post_uid", ""),
                "author_uid": node.get("author_uid", ""),
                "author_nickname": node.get("author_nickname", "") or "",
                "author_login": node.get("author_login", "") or "",
                "text": node.get("text", ""),
                "created_at": uuid8_timestamp(node.get("uid", "")),
            })
        author_uids = {c["author_uid"] for comment_list in by_post.values() for c in comment_list}
        authors: dict[str, dict] = {}
        if author_uids:
            a_res, _ = db.cypher_query(
                "MATCH (u:User) WHERE u.uid IN $uids RETURN u",
                {"uids": list(author_uids)},
            )
            for row in a_res:
                p = _row_user({"n": row[0]})
                authors[p["uid"]] = p
        for post in posts:
            comments = by_post.get(post["uid"], [])
            for c in comments:
                author = authors.get(c["author_uid"])
                if author:
                    c["author_nickname"] = author.get("nickname") or c["author_nickname"]
                    c["author_login"] = author.get("login") or c["author_login"]
            post["comments"] = comments

    def create_wall_post(self, author: dict, target_uid: str, text: str) -> dict:
        """Создаёт запись на стене. Разрешено только владельцу стены."""
        author_uid = author.get("uid", "")
        if author_uid != target_uid:
            return {"success": False, "error": "forbidden"}
        if not text or not text.strip():
            return {"success": False, "error": "empty_text"}
        if self.get_user(target_uid) is None:
            return {"success": False, "error": "user_not_found"}
        self.ensure_user(author)
        uid = uuid8_str()
        db.cypher_query(
            "CREATE (p:WallPost {uid: $uid, owner_uid: $ou, text: $text})",
            {"uid": uid, "ou": target_uid, "text": text.strip()},
        )
        return {"success": True, "post": {
            "uid": uid,
            "owner_uid": target_uid,
            "text": text.strip(),
            "created_at": uuid8_timestamp(uid),
            "comment_count": 0,
            "comments": [],
        }}

    def add_wall_comment(self, author: dict, post_uid: str, text: str) -> dict:
        """Добавляет комментарий под записью на стене (любой авторизованный)."""
        if not text or not text.strip():
            return {"success": False, "error": "empty_text"}
        author_uid = author.get("uid", "")
        results, _ = db.cypher_query(
            "MATCH (p:WallPost {uid: $uid}) RETURN p.owner_uid",
            {"uid": post_uid},
        )
        if not results:
            return {"success": False, "error": "post_not_found"}
        post_owner = results[0][0] or ""
        author_info = self.ensure_user(author)
        author_nickname = author_info.get("nickname", "") or str(author.get("nickname", "") or "").strip()
        author_login = author_info.get("login", "") or str(author.get("login", "") or "").strip()
        uid = uuid8_str()
        db.cypher_query(
            "CREATE (c:WallComment {uid: $uid, post_uid: $pu, author_uid: $au, "
            "author_nickname: $an, author_login: $al, text: $text})",
            {"uid": uid, "pu": post_uid, "au": author_uid, "an": author_nickname,
             "al": author_login, "text": text.strip()},
        )
        if post_owner and post_owner != author_uid:
            self._notify(post_owner, "wall_comment", "post", post_uid,
                         "Под вашей записью на стене оставили комментарий")
        return {"success": True, "comment": {
            "uid": uid,
            "post_uid": post_uid,
            "author_uid": author_uid,
            "author_nickname": author_nickname,
            "author_login": author_login,
            "text": text.strip(),
            "created_at": uuid8_timestamp(uid),
        }}

    # ── Тренды ────────────────────────────────────────────────────────────────

    def get_trends(self, limit: int = 10) -> dict:
        """Топ обсуждений по числу сообщений и по числу лайков."""
        by_comments, _ = db.cypher_query(
            "MATCH (m:ChatMessage) WITH m.target_type AS tt, m.target_uid AS tu, count(*) AS c "
            "RETURN tt, tu, c ORDER BY c DESC LIMIT $limit",
            {"limit": limit},
        )
        by_likes, _ = db.cypher_query(
            "MATCH (:User)-[:LIKES]->(m:ChatMessage) "
            "WITH m.target_type AS tt, m.target_uid AS tu, count(*) AS c "
            "RETURN tt, tu, c ORDER BY c DESC LIMIT $limit",
            {"limit": limit},
        )

        def build(rows) -> list[dict]:
            out = []
            for tt, tu, c in rows:
                out.append({
                    "target_type": tt,
                    "target_uid": tu,
                    "label": self._target_label(tt, tu),
                    "count": c,
                })
            return out

        return {"by_comments": build(by_comments), "by_likes": build(by_likes)}

    # ── Уведомления ───────────────────────────────────────────────────────────

    def _notify(self, user_uid: str, ntype: str, target_type: str,
                target_uid: str, text: str) -> None:
        if not user_uid:
            return
        db.cypher_query(
            "CREATE (n:Notification {uid: $uid, user_uid: $u, type: $t, "
            "target_type: $tt, target_uid: $tu, text: $text, "
            "is_read: false, created_at: $ts})",
            {"uid": uuid8_str(), "u": user_uid, "t": ntype, "tt": target_type,
             "tu": target_uid, "text": text, "ts": _now()},
        )

    def get_notifications(self, user_uid: str, limit: int = 50) -> dict:
        results, _ = db.cypher_query(
            "MATCH (n:Notification {user_uid: $uid}) "
            "RETURN n ORDER BY n.created_at DESC LIMIT $limit",
            {"uid": user_uid, "limit": limit},
        )
        unread, _ = db.cypher_query(
            "MATCH (n:Notification {user_uid: $uid, is_read: false}) RETURN count(*) AS c",
            {"uid": user_uid},
        )
        return {
            "success": True,
            "notifications": [{
                "uid": r[0].get("uid", ""),
                "type": r[0].get("type", ""),
                "target_type": r[0].get("target_type", ""),
                "target_uid": r[0].get("target_uid", ""),
                "text": r[0].get("text", ""),
                "is_read": bool(r[0].get("is_read")),
                "created_at": r[0].get("created_at") or 0,
            } for r in results],
            "unread_count": unread[0][0] if unread else 0,
        }

    def mark_notifications_read(self, user_uid: str, notification_uid: Optional[str] = None) -> dict:
        if notification_uid:
            db.cypher_query(
                "MATCH (n:Notification {uid: $n, user_uid: $u}) SET n.is_read = true",
                {"n": notification_uid, "u": user_uid},
            )
        else:
            db.cypher_query(
                "MATCH (n:Notification {user_uid: $u, is_read: false}) SET n.is_read = true",
                {"u": user_uid},
            )
        return {"success": True}

    # ── Жалобы ────────────────────────────────────────────────────────────────

    def create_complaint(
        self,
        reporter_uid: str,
        target_type: str,
        target_uid: str,
        reason: str,
        comment: str = "",
    ) -> dict:
        if target_type not in _TARGET_TYPES:
            return {"success": False, "error": "bad_target_type"}
        self.ensure_user({"uid": reporter_uid})
        uid = uuid8_str()
        db.cypher_query(
            "CREATE (c:Complaint {uid: $uid, reporter_uid: $ru, target_type: $tt, "
            "target_uid: $tu, reason: $reason, comment: $comment, "
            "status: 'open', created_at: $ts})",
            {"uid": uid, "ru": reporter_uid, "tt": target_type, "tu": target_uid,
             "reason": reason, "comment": comment, "ts": _now()},
        )
        return {"success": True, "complaint_uid": uid}

    # ── Изображения (чат) ─────────────────────────────────────────────────────

    async def upload_image(
        self, user_uid: str, filename: str, content_type: str, data: bytes
    ) -> dict:
        """Загружает изображение для чата в S3, возвращает object_key."""
        if not data:
            return {"success": False, "error": "empty_file"}
        self.ensure_user({"uid": user_uid})
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in _IMAGE_EXTENSIONS:
            ext = ".png"
        object_key = f"social/{uuid8_str()}{ext}"
        s3_client = get_s3_client()
        ok = await s3_client.upload_bytes(
            data,
            settings.S3_BUCKET_NAME,
            object_key,
            content_type=content_type or "application/octet-stream",
        )
        if not ok:
            return {"success": False, "error": "S3 upload failed"}
        return {"success": True, "object_key": object_key}

    async def get_image(self, object_key: str) -> tuple[bytes, str] | None:
        """Возвращает содержимое изображения и content-type, либо None."""
        if ".." in object_key.split("/"):
            return None
        s3_client = get_s3_client()
        if not await s3_client.object_exists(settings.S3_BUCKET_NAME, object_key):
            return None
        data = await s3_client.download_bytes(settings.S3_BUCKET_NAME, object_key)
        if data is None:
            return None
        content_type = mimetypes.guess_type(object_key)[0] or "application/octet-stream"
        return data, content_type

    async def delete_image(self, object_key: str) -> bool:
        """Удаляет изображение из S3."""
        if ".." in object_key.split("/"):
            return False
        s3_client = get_s3_client()
        if not await s3_client.object_exists(settings.S3_BUCKET_NAME, object_key):
            return False
        return await s3_client.delete_object(settings.S3_BUCKET_NAME, object_key)

    # ── Вклад пользователя ────────────────────────────────────────────────────

    def get_contributions(self, user_uid: str) -> dict:
        """Количество статей (документов) и структурных блоков пользователя."""
        docs, _ = db.cypher_query(
            "MATCH (d:Document {created_by_uid: $uid}) RETURN count(d) AS c",
            {"uid": user_uid},
        )
        article_count = docs[0][0] if docs else 0
        blocks, _ = db.cypher_query(
            "MATCH (d:Document {created_by_uid: $uid})-[:HAS_BLOCK]->(b:ArticleBlock) "
            "RETURN count(b) AS c",
            {"uid": user_uid},
        )
        block_count = blocks[0][0] if blocks else 0
        return {"article_count": article_count, "block_count": block_count}

    # ── Счётчик непрочитанных уведомлений ─────────────────────────────────────

    def get_unread_count(self, user_uid: str) -> int:
        results, _ = db.cypher_query(
            "MATCH (n:Notification {user_uid: $uid, is_read: false}) RETURN count(*) AS c",
            {"uid": user_uid},
        )
        return results[0][0] if results else 0

    # ── Разрешение UUID (отправка блока/статьи в чат) ────────────────────────

    def resolve_entity(self, uid: str) -> Optional[dict]:
        """По UUID определяет тип сущности и возвращает краткое описание.

        Поддерживает: ArticleBlock, Document (статья), KnowledgeStatement,
        Community, User, ChatMessage.
        """
        results, _ = db.cypher_query(
            "MATCH (b:ArticleBlock {uid: $uid}) RETURN b.block_type, b.order, b.data",
            {"uid": uid},
        )
        if results:
            raw_data = results[0][2]
            try:
                data = json.loads(raw_data) if isinstance(raw_data, str) else (raw_data or {})
            except (TypeError, ValueError):
                data = {}
            return {
                "uid": uid,
                "type": "block",
                "label": f"Блок T{results[0][0]}",
                "block_type": results[0][0],
                "order": results[0][1] or 0,
                "data": data,
            }
        results, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid}) RETURN coalesce(d.title, d.original_filename, '')",
            {"uid": uid},
        )
        if results:
            return {
                "uid": uid,
                "type": "article",
                "label": results[0][0] or "Статья",
            }
        results, _ = db.cypher_query(
            "MATCH (s:KnowledgeStatement {uid: $uid}) "
            "RETURN coalesce(s.subject_text, '') + ' → ' + coalesce(s.predicate, '') "
            "+ ' → ' + coalesce(s.object_text, '')",
            {"uid": uid},
        )
        if results:
            return {
                "uid": uid,
                "type": "statement",
                "label": results[0][0] or "Триплет",
            }
        results, _ = db.cypher_query(
            "MATCH (c:Community {uid: $uid}) RETURN c.name",
            {"uid": uid},
        )
        if results:
            return {"uid": uid, "type": "community", "label": results[0][0] or "Сообщество"}
        results, _ = db.cypher_query(
            "MATCH (u:User {uid: $uid}) RETURN coalesce(u.nickname, u.login)",
            {"uid": uid},
        )
        if results:
            return {"uid": uid, "type": "user", "label": results[0][0] or "Пользователь"}
        results, _ = db.cypher_query(
            "MATCH (m:ChatMessage {uid: $uid}) RETURN m.target_type",
            {"uid": uid},
        )
        if results:
            return {
                "uid": uid,
                "type": "message",
                "label": "Сообщение обсуждения",
                "target_type": results[0][0],
            }
        return None

    # ── Профиль / me / граф ───────────────────────────────────────────────────

    def get_profile(self, uid: str, viewer_uid: Optional[str] = None) -> Optional[dict]:
        user = self.get_user(uid)
        if user is None:
            return None
        friends = self.list_friends(uid)
        comms = self.list_communities_member_of(uid)
        profile = {
            **user,
            "friend_count": len(friends),
            "friends": friends,
            "communities": comms,
            "contributions": self.get_contributions(uid),
        }
        if viewer_uid:
            profile["is_friend"] = self._friend_relation(viewer_uid, uid)
        return profile

    def list_communities_member_of(self, user_uid: str) -> list[dict]:
        results, _ = db.cypher_query(
            "MATCH (u:User {uid: $uid})-[:MEMBER]->(c:Community) "
            "RETURN c ORDER BY c.name",
            {"uid": user_uid},
        )
        return [{
            "uid": r[0].get("uid", ""),
            "name": r[0].get("name", ""),
            "description": r[0].get("description", ""),
        } for r in results]

    def get_me(self, user: dict) -> dict:
        profile = self.ensure_user(user)
        uid = user.get("uid", "")
        friends = self.list_friends(uid)
        communities = self.list_communities_member_of(uid)
        notifications = self.get_notifications(uid, limit=20)
        profile["friend_count"] = len(friends)
        return {
            "success": True,
            "profile": profile,
            "friends": friends,
            "communities": communities,
            "notifications": notifications.get("notifications", []),
            "unread_count": notifications.get("unread_count", 0),
        }

    # ── Граф (pixi-react, force-directed) ─────────────────────────────────────

    def _graph_node(self, node, friend_count: int = 0, member_count: int = 0,
                    is_friend: bool = False, is_member: bool = False, is_me: bool = False) -> dict:
        """Узел графа: пользователь или сообщество, с аватаром и счётчиками."""
        data = _loads(node.get("data"))
        uid = node.get("uid", "")
        if "Community" in (node.labels or []):
            return {
                "id": uid,
                "type": "community",
                "label": node.get("name", ""),
                "description": node.get("description", ""),
                "avatar_key": data.get("avatar_key", ""),
                "member_count": member_count,
                "is_member": is_member,
            }
        return {
            "id": uid,
            "type": "user",
            "label": node.get("nickname") or node.get("login") or "Пользователь",
            "login": node.get("login", ""),
            "avatar_key": data.get("avatar_key", ""),
            "friend_count": friend_count,
            "is_friend": is_friend,
            "is_me": is_me,
        }

    def _build_graph(self, user_uids: list[str], community_uids: list[str],
                     viewer_uid: str | None = None) -> dict:
        """Строит подграф по списку uid пользователей и сообществ."""
        nodes: list[dict] = []
        edges: list[dict] = []
        user_uids = list(dict.fromkeys(user_uids))
        community_uids = list(dict.fromkeys(community_uids))
        if user_uids:
            u_res, _ = db.cypher_query(
                "MATCH (u:User) WHERE u.uid IN $uids "
                "OPTIONAL MATCH (u)-[:FRIEND]->(f:User) "
                "WITH u, count(f) AS fc RETURN u, fc ORDER BY u.nickname",
                {"uids": user_uids},
            )
            nodes += [self._graph_node(r[0], friend_count=r[1]) for r in u_res]
        if community_uids:
            c_res, _ = db.cypher_query(
                "MATCH (c:Community) WHERE c.uid IN $cids "
                "OPTIONAL MATCH (m:User)-[:MEMBER]->(c) "
                "WITH c, count(m) AS mc RETURN c, mc ORDER BY c.name",
                {"cids": community_uids},
            )
            nodes += [self._graph_node(r[0], member_count=r[1]) for r in c_res]
        if len(user_uids) > 1:
            f_res, _ = db.cypher_query(
                "MATCH (a:User)-[:FRIEND]->(b:User) "
                "WHERE a.uid IN $uids AND b.uid IN $uids RETURN a.uid, b.uid",
                {"uids": user_uids},
            )
            edges += [{"source": r[0], "target": r[1], "type": "friend"} for r in f_res]
        if user_uids and community_uids:
            m_res, _ = db.cypher_query(
                "MATCH (u:User)-[:MEMBER]->(c:Community) "
                "WHERE u.uid IN $uids AND c.uid IN $cids RETURN u.uid, c.uid",
                {"uids": user_uids, "cids": community_uids},
            )
            edges += [{"source": r[0], "target": r[1], "type": "member"} for r in m_res]
        if viewer_uid:
            viewer_friends = {f["uid"] for f in self.list_friends(viewer_uid)}
            viewer_members = {c["uid"] for c in self.list_communities_member_of(viewer_uid)}
            for node in nodes:
                if node["type"] == "user":
                    node["is_friend"] = node["id"] in viewer_friends
                    node["is_me"] = node["id"] == viewer_uid
                else:
                    node["is_member"] = node["id"] in viewer_members
        return {"success": True, "nodes": nodes, "edges": edges}

    def get_ego_graph(self, user_uid: str) -> dict:
        """Эго-граф текущего пользователя: он сам, его друзья и его сообщества."""
        self.ensure_user({"uid": user_uid})
        friends = self.list_friends(user_uid)
        friend_uids = [f["uid"] for f in friends]
        comm_uids = [c["uid"] for c in self.list_communities_member_of(user_uid)]
        user_uids = [user_uid] + friend_uids
        return self._build_graph(user_uids, comm_uids, viewer_uid=user_uid)

    def get_user_graph(self, uid: str, viewer_uid: str | None = None) -> dict:
        """Расширение графа: пользователь, его друзья и его сообщества.

        Используется при двойном клике на узле пользователя.
        """
        if self.get_user(uid) is None:
            return {"success": False, "error": "user_not_found"}
        friends = self.list_friends(uid)
        friend_uids = [f["uid"] for f in friends]
        comm_uids = [c["uid"] for c in self.list_communities_member_of(uid)]
        return self._build_graph([uid] + friend_uids, comm_uids, viewer_uid=viewer_uid)

    def get_public_graph(self) -> dict:
        """Полный граф для гостей: все пользователи и сообщества без viewer-флагов."""
        u_res, _ = db.cypher_query("MATCH (u:User) RETURN u.uid")
        c_res, _ = db.cypher_query("MATCH (c:Community) RETURN c.uid")
        return self._build_graph(
            [r[0] for r in u_res],
            [r[0] for r in c_res],
            viewer_uid=None,
        )

    def get_graph(self) -> dict:
        """Полный граф (устаревший формат, для обратной совместимости)."""
        users, _ = db.cypher_query(
            "MATCH (u:User) OPTIONAL MATCH (u)-[:FRIEND]->(f:User) "
            "WITH u, count(DISTINCT f) AS friend_count "
            "RETURN u, friend_count ORDER BY u.nickname",
        )
        communities, _ = db.cypher_query(
            "MATCH (c:Community) OPTIONAL MATCH (m:User)-[:MEMBER]->(c) "
            "WITH c, count(m) AS member_count RETURN c, member_count ORDER BY c.name",
        )
        friend_edges, _ = db.cypher_query(
            "MATCH (a:User)-[:FRIEND]->(b:User) RETURN a.uid, b.uid",
        )
        member_edges, _ = db.cypher_query(
            "MATCH (u:User)-[:MEMBER]->(c:Community) RETURN u.uid, c.uid",
        )
        nodes = [
            {
                "id": r[0].get("uid", ""),
                "type": "user",
                "label": r[0].get("nickname") or r[0].get("login") or "Пользователь",
                "login": r[0].get("login", ""),
                "friend_count": r[1],
            }
            for r in users
        ]
        nodes += [
            {
                "id": r[0].get("uid", ""),
                "type": "community",
                "label": r[0].get("name", ""),
                "description": r[0].get("description", ""),
                "member_count": r[1],
            }
            for r in communities
        ]
        edges = [{"source": r[0], "target": r[1], "type": "friend"} for r in friend_edges]
        edges += [{"source": r[0], "target": r[1], "type": "member"} for r in member_edges]
        return {"success": True, "nodes": nodes, "edges": edges}
