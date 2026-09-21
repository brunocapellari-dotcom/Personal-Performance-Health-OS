from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from dataclasses import asdict
from typing import Annotated
from uuid import uuid4

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api_models import (
    ChallengeRequest,
    ChallengeResponse,
    DeviceEnrollRequest,
    DeviceEnrollResponse,
    FoodRecordOut,
    NextBlockRequest,
    NextBlockResponse,
    NutritionSearchResponse,
    PairingTokenRequest,
    PairingTokenResponse,
    SyncChangeOut,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
    TokenResponse,
    VerifyRequest,
)
from .audit import append_audit, verify_audit_chain
from .auth import (
    Principal,
    authenticate_active_token,
    consume_pairing_token,
    create_challenge,
    create_pairing_token,
    enroll_device,
    enrolled_device_count,
    public_key_fingerprint,
    require_owner,
    secure_compare,
    sha256_hex,
    verify_challenge,
)
from .config import Settings
from .contracts import NutritionDataProvider, PackagedFoodProvider
from .db import Database
from .domain import (
    AvailabilityWindow,
    Event,
    Goal,
    NutritionTrend,
    Observation,
    ReadinessInput,
    TrainingEnvironment,
    TrainingResponse,
)
from .models import PlanSnapshotModel
from .nutrition_sources import OpenFoodFactsProvider, UsdaFoodDataCentralProvider
from .orchestrator import HealthOS
from .state import PlanningStateResolver
from .sync import IncomingChange, current_cursor, pull_changes, push_changes


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    nutrition_provider: NutritionDataProvider | None = None,
    packaged_food_provider: PackagedFoodProvider | None = None,
    initialize_schema: bool = False,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_settings.validate()
    resolved_database = database or Database(resolved_settings)
    if initialize_schema:
        resolved_database.create_schema_for_tests(resolved_settings)
    healthos = HealthOS()
    resolved_nutrition_provider = nutrition_provider
    if resolved_nutrition_provider is None and resolved_settings.fdc_api_key:
        resolved_nutrition_provider = UsdaFoodDataCentralProvider(resolved_settings.fdc_api_key)
    resolved_packaged_provider = packaged_food_provider or OpenFoodFactsProvider(
        user_agent=resolved_settings.open_food_facts_user_agent
    )

    app = FastAPI(
        title="Personal Performance & Health OS",
        version="0.2.0",
        docs_url=None if resolved_settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database

    def get_session() -> Iterator[Session]:
        with resolved_database.session() as db:
            yield db

    DbSession = Annotated[Session, Depends(get_session)]

    def get_principal(
        db: DbSession,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bearer token required")
        try:
            return authenticate_active_token(
                db,
                authorization.removeprefix("Bearer ").strip(),
                resolved_settings,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    Actor = Annotated[Principal, Depends(get_principal)]

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "environment": resolved_settings.environment}

    @app.post("/v1/devices/enroll", response_model=DeviceEnrollResponse)
    def device_enroll(
        payload: DeviceEnrollRequest,
        db: DbSession,
        authorization: Annotated[str | None, Header()] = None,
    ) -> DeviceEnrollResponse:
        supplied = None
        if authorization and authorization.startswith("Bearer "):
            supplied = authorization.removeprefix("Bearer ").strip()
        device_count = enrolled_device_count(db)
        if device_count == 0:
            if payload.role != "owner_device":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="the first enrolled device must be owner_device",
                )
            if not secure_compare(supplied, resolved_settings.bootstrap_token):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bootstrap authorization failed")
        else:
            if supplied is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="pairing token required")
            try:
                consume_pairing_token(db, token=supplied, requested_role=payload.role)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        try:
            device = enroll_device(
                db,
                device_id=payload.device_id,
                public_key_pem=payload.public_key_pem,
                role=payload.role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        append_audit(
            db,
            resolved_settings,
            actor_device_id=payload.device_id,
            action="device.enroll",
            target=payload.device_id,
            payload={"role": payload.role, "fingerprint": public_key_fingerprint(payload.public_key_pem)},
        )
        return DeviceEnrollResponse(
            device_id=device.device_id,
            role=device.role,
            fingerprint=public_key_fingerprint(device.public_key_pem),
        )

    @app.post("/v1/devices/pairing-token", response_model=PairingTokenResponse)
    def device_pairing_token(payload: PairingTokenRequest, db: DbSession, actor: Actor) -> PairingTokenResponse:
        try:
            require_owner(actor)
            token, expires_at = create_pairing_token(
                db,
                issued_by_device_id=actor.device_id,
                role=payload.role,
                ttl_seconds=payload.ttl_seconds,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        append_audit(
            db,
            resolved_settings,
            actor_device_id=actor.device_id,
            action="device.pairing_token.create",
            target=payload.role,
            payload={"role": payload.role, "expires_at": expires_at.isoformat()},
        )
        return PairingTokenResponse(token=token, role=payload.role, expires_at=expires_at)

    @app.post("/v1/auth/challenge", response_model=ChallengeResponse)
    def auth_challenge(payload: ChallengeRequest, db: DbSession) -> ChallengeResponse:
        try:
            challenge = create_challenge(db, device_id=payload.device_id, settings=resolved_settings)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return ChallengeResponse(
            challenge_id=challenge.challenge_id,
            nonce=challenge.nonce,
            expires_at=challenge.expires_at,
        )

    @app.post("/v1/auth/verify", response_model=TokenResponse)
    def auth_verify(payload: VerifyRequest, db: DbSession) -> TokenResponse:
        try:
            token = verify_challenge(
                db,
                challenge_id=payload.challenge_id,
                signature_b64=payload.signature_b64,
                settings=resolved_settings,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        return TokenResponse(access_token=token)

    @app.post("/v1/sync/push", response_model=SyncPushResponse)
    def sync_push(payload: SyncPushRequest, db: DbSession, actor: Actor) -> SyncPushResponse:
        try:
            require_owner(actor)
            result = push_changes(
                db,
                resolved_settings,
                device_id=actor.device_id,
                changes=tuple(
                    IncomingChange(
                        change_id=item.change_id,
                        entity_type=item.entity_type,
                        entity_id=item.entity_id,
                        logical_clock=item.logical_clock,
                        deleted=item.deleted,
                        payload=item.payload,
                    )
                    for item in payload.changes
                ),
            )
        except (PermissionError, ValueError) as exc:
            code = (
                status.HTTP_403_FORBIDDEN
                if isinstance(exc, PermissionError)
                else status.HTTP_422_UNPROCESSABLE_ENTITY
            )
            raise HTTPException(status_code=code, detail=str(exc)) from exc
        return SyncPushResponse(
            accepted=list(result.accepted),
            duplicates=list(result.duplicates),
            conflicts=list(result.conflicts),
            cursor=result.cursor,
        )

    @app.get("/v1/sync/pull", response_model=SyncPullResponse)
    def sync_pull(
        db: DbSession,
        actor: Actor,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 500,
    ) -> SyncPullResponse:
        del actor
        changes = pull_changes(db, after_cursor=after, limit=limit)
        cursor = changes[-1].server_seq if changes else current_cursor(db)
        return SyncPullResponse(
            changes=[
                SyncChangeOut(
                    server_seq=item.server_seq,
                    change_id=item.change_id,
                    entity_type=item.entity_type,
                    entity_id=item.entity_id,
                    logical_clock=item.logical_clock,
                    origin_device_id=item.origin_device_id,
                    deleted=item.deleted,
                    payload=item.payload,
                    created_at=item.created_at,
                )
                for item in changes
            ],
            cursor=cursor,
        )

    @app.get("/v1/nutrition/search", response_model=NutritionSearchResponse)
    def nutrition_search(
        actor: Actor,
        q: Annotated[str, Query(min_length=1, max_length=200)],
    ) -> NutritionSearchResponse:
        del actor
        if resolved_nutrition_provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="USDA FoodData Central integration is not configured",
            )
        try:
            foods = resolved_nutrition_provider.search(q)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="nutrition source unavailable") from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="nutrition source returned invalid data") from exc
        return NutritionSearchResponse(foods=[FoodRecordOut.model_validate(asdict(food)) for food in foods])

    @app.get("/v1/nutrition/barcode/{barcode}", response_model=FoodRecordOut)
    def nutrition_barcode(barcode: str, actor: Actor) -> FoodRecordOut:
        del actor
        try:
            food = resolved_packaged_provider.lookup_barcode(barcode)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="packaged food source unavailable") from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        if food is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="barcode not found")
        return FoodRecordOut.model_validate(asdict(food))

    @app.post("/v1/plans/next-block", response_model=NextBlockResponse)
    def next_block(payload: NextBlockRequest, db: DbSession, actor: Actor) -> NextBlockResponse:
        try:
            require_owner(actor)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

        resolver = PlanningStateResolver()
        planning_now = datetime(
            payload.today.year,
            payload.today.month,
            payload.today.day,
            23,
            59,
            59,
            tzinfo=UTC,
        )
        health_pipeline = resolver.health_pipeline(db, now=planning_now)
        synced_goals = resolver.goals(db, now=planning_now, pipeline=health_pipeline)
        synced_environment = resolver.environment(db)
        synced_readiness = resolver.readiness(db, now=planning_now, pipeline=health_pipeline)

        if payload.goals is None and not synced_goals:
            raise HTTPException(status_code=422, detail="no active goals are available")
        if payload.environment is None and synced_environment is None:
            raise HTTPException(status_code=422, detail="no training environment is available")
        if payload.readiness is None and synced_readiness is None:
            raise HTTPException(status_code=422, detail="no readiness input is available")

        goals = (
            tuple(
                Goal(
                    goal_id=goal.goal_id,
                    description=goal.description,
                    priority=goal.priority,
                    baseline=goal.baseline,
                    target=goal.target,
                    target_date=goal.target_date,
                    metric=goal.metric,
                    constraints=tuple(goal.constraints),
                    current=goal.current,
                )
                for goal in payload.goals
            )
            if payload.goals is not None
            else synced_goals
        )

        environment = (
            TrainingEnvironment(
                environment=payload.environment.environment,
                equipment=frozenset(payload.environment.equipment),
                space_m2=payload.environment.space_m2,
                fixation_points=frozenset(payload.environment.fixation_points),
                noise_limit=payload.environment.noise_limit,
                surface=payload.environment.surface,
                available_minutes=payload.environment.available_minutes,
                load_options_kg=tuple(sorted(payload.environment.load_options_kg)),
            )
            if payload.environment is not None
            else synced_environment
        )
        readiness = (
            ReadinessInput(**payload.readiness.model_dump())
            if payload.readiness is not None
            else synced_readiness
        )
        assert environment is not None
        assert readiness is not None

        fields_set = payload.model_fields_set
        nutrition_trend = (
            NutritionTrend(**payload.nutrition_trend.model_dump())
            if "nutrition_trend" in fields_set and payload.nutrition_trend is not None
            else None
            if "nutrition_trend" in fields_set
            else resolver.nutrition(db)
        )
        event = (
            Event(
                event_id=payload.event.event_id,
                name=payload.event.name,
                event_date=payload.event.event_date,
                demands=tuple(payload.event.demands),
                duration_minutes=payload.event.duration_minutes,
                distance_km=payload.event.distance_km,
                priority=payload.event.priority,
            )
            if "event" in fields_set and payload.event is not None
            else None
            if "event" in fields_set
            else resolver.event(db, payload.today)
        )
        training_response = (
            TrainingResponse(**payload.training_response.model_dump())
            if "training_response" in fields_set and payload.training_response is not None
            else None
            if "training_response" in fields_set
            else resolver.training_response(db)
        )
        availability = (
            tuple(
                AvailabilityWindow(day=window.day, available_minutes=window.available_minutes)
                for window in payload.availability
            )
            if payload.availability is not None
            else resolver.availability(db, payload.today, payload.weeks)
        )
        strength_progressions = resolver.strength_progressions(db, environment)

        resolved_request = jsonable_encoder(
            {
                "goals": [asdict(goal) for goal in goals],
                "environment": asdict(environment),
                "readiness": asdict(readiness),
                "nutrition_trend": None if nutrition_trend is None else asdict(nutrition_trend),
                "event": None if event is None else asdict(event),
                "training_response": None if training_response is None else asdict(training_response),
                "availability": [asdict(window) for window in availability],
                "strength_progressions": {
                    exercise_id: asdict(decision)
                    for exercise_id, decision in sorted(strength_progressions.items())
                },
                "today": payload.today,
                "weeks": payload.weeks,
            }
        )
        request_hash = sha256_hex(resolved_request)
        existing = db.scalar(
            select(PlanSnapshotModel).where(
                PlanSnapshotModel.device_id == actor.device_id,
                PlanSnapshotModel.request_hash == request_hash,
            )
        )
        if existing is not None:
            return NextBlockResponse(
                snapshot_id=existing.snapshot_id,
                plan=dict(existing.plan_json),
                audit=dict(existing.audit_json),
            )

        try:
            result = healthos.next_block(
                goals=goals,
                environment=environment,
                readiness=readiness,
                nutrition_trend=nutrition_trend,
                event=event,
                today=payload.today,
                weeks=payload.weeks,
                training_response=training_response,
                availability=availability,
                strength_progressions=strength_progressions,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        plan_json = jsonable_encoder(asdict(result.plan))
        audit_json = jsonable_encoder(asdict(result.audit))
        snapshot = PlanSnapshotModel(
            snapshot_id=uuid4().hex,
            device_id=actor.device_id,
            request_hash=request_hash,
            request_json=resolved_request,
            plan_json=plan_json,
            audit_json=audit_json,
        )
        db.add(snapshot)
        append_audit(
            db,
            resolved_settings,
            actor_device_id=actor.device_id,
            action="plan.next_block",
            target=snapshot.snapshot_id,
            payload={"request_hash": request_hash, "audit_passed": result.audit.passed},
        )
        db.flush()
        return NextBlockResponse(snapshot_id=snapshot.snapshot_id, plan=plan_json, audit=audit_json)

    @app.get("/v1/observations/timeline")
    def observations_timeline(
        db: DbSession,
        actor: Actor,
        metric: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> dict[str, object]:
        del actor
        pipeline = PlanningStateResolver().health_pipeline(db)
        if pipeline is None:
            return {"observations": [], "count": 0}
        filtered = (
            tuple(item for item in pipeline.canonical if item.metric == metric)
            if metric is not None
            else pipeline.canonical
        )
        selected = tuple(sorted(filtered, key=lambda item: item.observed_at, reverse=True)[:limit])
        return jsonable_encoder(
            {
                "observations": [
                    {
                        "observation_id": item.observation_id,
                        "metric": item.metric,
                        "value": item.value,
                        "unit": item.unit,
                        "observed_at": item.observed_at,
                        "recorded_at": item.recorded_at,
                        "source_id": item.source_id,
                        "source_type": item.source_type,
                        "quality": item.quality,
                        "confidence": item.confidence,
                        "metadata": item.metadata,
                    }
                    for item in selected
                ],
                "count": len(selected),
            }
        )

    @app.get("/v1/observations/sources")
    def observation_sources(db: DbSession, actor: Actor) -> dict[str, object]:
        del actor
        pipeline = PlanningStateResolver().health_pipeline(db)
        if pipeline is None:
            return {"sources": []}

        grouped: dict[str, list[Observation]] = {}
        for item in pipeline.canonical:
            grouped.setdefault(item.source_id, []).append(item)

        sources: list[dict[str, object]] = []
        for source_id, items in sorted(grouped.items()):
            metrics = sorted({item.metric for item in items})
            confidences = [item.confidence for item in items if item.confidence is not None]
            latest_at = max(item.observed_at for item in items)
            sources.append(
                {
                    "source_id": source_id,
                    "source_type": items[0].source_type,
                    "metrics": metrics,
                    "observation_count": len(items),
                    "latest_at": latest_at,
                    "avg_confidence": None
                    if not confidences
                    else round(sum(confidences) / len(confidences), 3),
                }
            )
        return jsonable_encoder({"sources": sources})

    @app.get("/v1/observations/summary")
    def observations_summary(db: DbSession, actor: Actor) -> dict[str, object]:
        del actor
        pipeline = PlanningStateResolver().health_pipeline(db)
        if pipeline is None:
            return {
                "raw_count": 0,
                "normalized_count": 0,
                "canonical_count": 0,
                "source_version_suppressed_ids": [],
                "suppressed_ids": [],
                "quality_findings": [],
                "missing_findings": [],
                "baselines": {},
                "analytics": {},
                "baseline_contract": {"passed": True, "findings": []},
                "analytics_contract": {"passed": True, "findings": []},
            }
        return jsonable_encoder(
            {
                "raw_count": pipeline.raw_count,
                "normalized_count": pipeline.normalized_count,
                "canonical_count": len(pipeline.canonical),
                "source_version_suppressed_ids": pipeline.source_version_suppressed_ids,
                "suppressed_ids": pipeline.suppressed_ids,
                "quality_findings": [asdict(item) for item in pipeline.quality_findings],
                "missing_findings": [asdict(item) for item in pipeline.missing_findings],
                "baselines": {
                    metric: asdict(value)
                    for metric, value in sorted(pipeline.baselines.items())
                },
                "analytics": {
                    metric: asdict(value)
                    for metric, value in sorted(pipeline.analytics.items())
                },
                "baseline_contract": asdict(pipeline.baseline_contract),
                "analytics_contract": asdict(pipeline.analytics_contract),
            }
        )

    @app.get("/v1/audit/verify")
    def audit_verify(db: DbSession, actor: Actor) -> dict[str, bool]:
        del actor
        return {"valid": verify_audit_chain(db, resolved_settings)}

    return app


def run() -> None:
    settings = Settings.from_env()
    settings.validate()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8000, proxy_headers=False)


app = create_app()
