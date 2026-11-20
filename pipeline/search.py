import json
import re


def _fts_available(connection) -> bool:
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'event_search_fts'
            """
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _status(event_row) -> str:
    try:
        entities = json.loads(event_row["entities_json"] or "{}")
        return entities.get("resolution_status", "unknown")
    except (json.JSONDecodeError, TypeError):
        return "unknown"


def build_event_search_index(connection, match_id: str) -> int:
    event_rows = connection.execute(
        """
        SELECT event_id, match_id, event_type, timestamp, title,
               description, confidence, entities_json
        FROM events
        WHERE match_id = ?
        ORDER BY timestamp, event_id
        """,
        (match_id,),
    ).fetchall()

    connection.execute(
        "DELETE FROM event_search_documents WHERE match_id = ?",
        (match_id,),
    )
    if _fts_available(connection):
        connection.execute(
            "DELETE FROM event_search_fts WHERE match_id = ?",
            (match_id,),
        )

    documents = []
    for event in event_rows:
        status = _status(event)
        evidence_rows = connection.execute(
            """
            SELECT source_type, source_id, source_timestamp,
                   source_value, confidence, weight, details_json
            FROM event_evidence
            WHERE event_id = ?
            ORDER BY source_timestamp, source_id
            """,
            (event["event_id"],),
        ).fetchall()

        evidence_parts = []
        for evidence in evidence_rows:
            source_value = evidence["source_value"] or ""
            evidence_parts.append(
                f"{evidence['source_type']} {source_value}".strip()
            )
        evidence_text = " ".join(evidence_parts)

        entities_text = event["entities_json"] or "{}"
        searchable_text = " ".join(
            part for part in (
                event["event_type"],
                status,
                event["title"] or "",
                event["description"] or "",
                entities_text,
                evidence_text,
            )
            if part
        )

        documents.append(
            (
                event["event_id"],
                match_id,
                event["event_type"],
                status,
                event["timestamp"],
                event["title"],
                event["description"],
                event["entities_json"],
                evidence_text,
                searchable_text,
            )
        )

    connection.executemany(
        """
        INSERT INTO event_search_documents (
            event_id,
            match_id,
            event_type,
            status,
            timestamp,
            title,
            description,
            entities_json,
            evidence_text,
            searchable_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            event_type = excluded.event_type,
            status = excluded.status,
            timestamp = excluded.timestamp,
            title = excluded.title,
            description = excluded.description,
            entities_json = excluded.entities_json,
            evidence_text = excluded.evidence_text,
            searchable_text = excluded.searchable_text
        """,
        documents,
    )

    if _fts_available(connection):
        fts_rows = []
        for document in documents:
            fts_rows.append(
                (
                    document[0],
                    document[1],
                    document[2],
                    document[3],
                    document[5] or "",
                    document[6] or "",
                    document[7] or "{}",
                    document[8],
                )
            )
        connection.executemany(
            """
            INSERT INTO event_search_fts (
                event_id,
                match_id,
                event_type,
                status,
                title,
                description,
                entities,
                evidence_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            fts_rows,
        )

    return len(documents)


def _fts_phrase(query: str) -> str:
    words = re.findall(r"[^\s]+", query.strip())
    return " AND ".join(
        f'"{word.replace(chr(34), chr(34) * 2)}"' 
        for word in words
    )


def search_events(
    connection,
    match_id: str,
    query: str | None = None,
    event_types: list[str] | None = None,
    statuses: list[str] | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    limit: int = 10,
    include_context: bool = True,
) -> list[dict]:
    if limit <= 0:
        return []

    conditions = ["d.match_id = ?"]
    parameters: list = [match_id]

    if event_types:
        conditions.append(
            "d.event_type IN (" + ",".join("?" for _ in event_types) + ")"
        )
        parameters.extend(event_types)

    if statuses:
        statuses = [
            status.lower()
            for status in statuses
        ]
        conditions.append(
            "d.status IN (" + ",".join("?" for _ in statuses) + ")"
        )
        parameters.extend(statuses)

    if start_time is not None:
        conditions.append("d.timestamp >= ?")
        parameters.append(start_time)
    if end_time is not None:
        conditions.append("d.timestamp <= ?")
        parameters.append(end_time)

    fts_ids = None
    if query and query.strip() and _fts_available(connection):
        try:
            fts_rows = connection.execute(
                """
                SELECT event_id
                FROM event_search_fts
                WHERE event_search_fts MATCH ?
                  AND match_id = ?
                """,
                (_fts_phrase(query), match_id),
            ).fetchall()
            fts_ids = [row["event_id"] for row in fts_rows]
        except Exception:
            fts_ids = None

    if fts_ids is not None:
        if not fts_ids:
            return []
        conditions.append(
            "d.event_id IN (" + ",".join("?" for _ in fts_ids) + ")"
        )
        parameters.extend(fts_ids)

    if query and query.strip() and fts_ids is None:
        words = [word for word in re.findall(r"[A-Za-z0-9]+", query.lower())]
        for word in words:
            conditions.append("LOWER(d.searchable_text) LIKE ?")
            parameters.append(f"%{word}%")

    rows = connection.execute(
        """
        SELECT d.event_id, d.match_id, d.event_type, d.status,
               d.timestamp, d.title, d.description, d.entities_json,
               d.evidence_text,
               e.confidence
        FROM event_search_documents d
        JOIN events e ON e.event_id = d.event_id
        WHERE """
        + " AND ".join(conditions)
        + """
        ORDER BY e.confidence DESC, d.timestamp ASC, d.event_id ASC
        """,
        parameters,
    ).fetchall()

    results = []
    for row in rows[:limit]:
        item = {
            "event_id": row["event_id"],
            "match_id": row["match_id"],
            "event_type": row["event_type"],
            "status": row["status"],
            "timestamp": row["timestamp"],
            "title": row["title"],
            "description": row["description"],
            "confidence": row["confidence"],
            "entities": json.loads(row["entities_json"] or "{}"),
        }

        if include_context:
            evidence_rows = connection.execute(
                """
                SELECT evidence_id, source_type, source_id,
                       source_timestamp, source_value, confidence, weight
                FROM event_evidence
                WHERE event_id = ?
                ORDER BY weight DESC, source_timestamp, evidence_id
                """,
                (row["event_id"],),
            ).fetchall()
            item["evidence"] = [dict(evidence) for evidence in evidence_rows]

            keyframe_rows = connection.execute(
                """
                SELECT keyframe_id, timestamp, image_path, role
                FROM event_keyframes
                WHERE event_id = ?
                ORDER BY timestamp
                """,
                (row["event_id"],),
            ).fetchall()
            item["keyframes"] = [dict(keyframe) for keyframe in keyframe_rows]

        results.append(item)

    return results
