"""Activity API routes.

Exposes paginated, filterable access to the model_invocations Activity log.
All endpoints require an authenticated session (enforced by the global auth
guard installed in app.py).

Endpoints
---------
GET  /api/activity                 — paginated list (no raw payload)
GET  /api/activity/<int:record_id> — single record with full request_payload
POST /api/activity/purge-expired   — delete records older than retention_days
"""
from __future__ import annotations

from flask import jsonify, request

from db import (
    count_activity_records,
    delete_expired_activity_records,
    get_activity_record,
    get_app_settings,
    list_activity_records,
)


def _parse_optional_int(value, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_activity_retention_days(settings: dict) -> int:
    raw = str(settings.get("activity_retention_days") or "").strip()
    try:
        days = int(raw)
        return max(1, days)
    except (TypeError, ValueError):
        return 30


def register_activity_routes(app) -> None:

    @app.route("/api/activity", methods=["GET"])
    def list_activity():
        settings = get_app_settings()
        if not _activity_enabled(settings):
            return jsonify({"error": "Activity logging is disabled."}), 404

        provider = request.args.get("provider") or None
        call_type = request.args.get("call_type") or None
        operation = request.args.get("operation") or None
        response_status = request.args.get("response_status") or None
        since_iso = request.args.get("since") or None
        until_iso = request.args.get("until") or None
        conversation_id = _parse_optional_int(request.args.get("conversation_id"))
        limit = max(1, min(200, _parse_optional_int(request.args.get("limit"), 50) or 50))
        offset = max(0, _parse_optional_int(request.args.get("offset"), 0) or 0)
        sort_by = request.args.get("sort_by") or "created_at"
        sort_dir = request.args.get("sort_dir") or "DESC"

        records = list_activity_records(
            conversation_id=conversation_id,
            provider=provider,
            call_type=call_type,
            operation=operation,
            response_status=response_status,
            since_iso=since_iso,
            until_iso=until_iso,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_dir=sort_dir,
            include_request=False,
        )
        total = count_activity_records(
            conversation_id=conversation_id,
            provider=provider,
            call_type=call_type,
            operation=operation,
            response_status=response_status,
            since_iso=since_iso,
            until_iso=until_iso,
        )
        return jsonify(
            {
                "records": records,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    @app.route("/api/activity/<int:record_id>", methods=["GET"])
    def get_activity(record_id: int):
        settings = get_app_settings()
        if not _activity_enabled(settings):
            return jsonify({"error": "Activity logging is disabled."}), 404

        record = get_activity_record(record_id)
        if record is None:
            return jsonify({"error": "Not found."}), 404
        return jsonify({"record": record})

    @app.route("/api/activity/purge-expired", methods=["POST"])
    def purge_expired_activity():
        settings = get_app_settings()
        if not _activity_enabled(settings):
            return jsonify({"error": "Activity logging is disabled."}), 404

        retention_days = _get_activity_retention_days(settings)
        deleted = delete_expired_activity_records(retention_days)
        return jsonify({"deleted": deleted, "retention_days": retention_days})


def _activity_enabled(settings: dict) -> bool:
    raw = str(settings.get("activity_enabled") or "").strip().lower()
    # Default to enabled when unset
    return raw not in {"false", "0", "off", "no"}
