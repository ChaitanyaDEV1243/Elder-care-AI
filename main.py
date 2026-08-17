import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from anomaly_engine import score_checkin, save_anomaly_result
from escalation_engine import decide_escalation, save_escalation
from offline_fallback import get_with_fallback

DB_PATH = "eldercare.db"


app = FastAPI(
    title="AI Elder-Care Check-In API",
    description="Personalized elder-care monitoring and anomaly detection",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# DATABASE
# =========================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# REQUEST MODEL
# =========================================================

class CheckInRequest(BaseModel):
    person_id: int = Field(gt=0)

    check_in_date: str

    response_latency_seconds: float = Field(ge=0)

    sentiment_score: float = Field(
        ge=-1.0,
        le=1.0
    )

    medication_morning_confirmed: bool

    medication_evening_confirmed: bool

    call_answered: bool


# =========================================================
# BASIC ENDPOINTS
# =========================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "AI Elder-Care Check-In API"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


# =========================================================
# COMPLETE CHECK-IN PIPELINE
# =========================================================

@app.post("/check-ins")
def create_checkin(checkin: CheckInRequest):

    conn = get_connection()

    try:

        # -------------------------------------------------
        # 1. STORE RAW CHECK-IN
        # -------------------------------------------------

        cursor = conn.execute(
            """
            INSERT INTO check_ins (
                person_id,
                check_in_date,
                response_latency_seconds,
                sentiment_score,
                medication_morning_confirmed,
                medication_evening_confirmed,
                call_answered
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkin.person_id,
                checkin.check_in_date,
                checkin.response_latency_seconds,
                checkin.sentiment_score,
                int(checkin.medication_morning_confirmed),
                int(checkin.medication_evening_confirmed),
                int(checkin.call_answered)
            )
        )

        conn.commit()

        check_in_id = cursor.lastrowid

        # -------------------------------------------------
        # 2. ANOMALY SCORING
        # -------------------------------------------------

        result = score_checkin(
            conn,
            checkin.person_id,
            checkin.check_in_date
        )

        # -------------------------------------------------
        # 3. SAVE ANOMALY RESULT
        # -------------------------------------------------

        anomaly_id = save_anomaly_result(
            conn,
            result
        )

        # -------------------------------------------------
        # 4. ESCALATION DECISION
        # -------------------------------------------------

        decision = decide_escalation(
            result["anomaly_score"],
            result["level"]
        )

        # -------------------------------------------------
        # 5. SAVE ESCALATION
        # -------------------------------------------------

        escalation_id = save_escalation(
            conn,
            anomaly_id,
            decision
        )

        # -------------------------------------------------
        # 6. RETURN COMPLETE PIPELINE RESULT
        # -------------------------------------------------

        return {
            "status": "success",

            "check_in": {
                "id": check_in_id,
                "date": checkin.check_in_date
            },

            "anomaly": {
                "id": anomaly_id,
                "score": result["anomaly_score"],
                "level": result["level"],
                "signals": result["signals"],
                "reason": result["reason"]
            },

            "escalation": {
                "id": escalation_id,
                "level": decision["level"],
                "action": decision["action"]
            }
        }

    except sqlite3.IntegrityError as e:

        conn.rollback()

        raise HTTPException(
            status_code=400,
            detail=f"Could not store check-in: {str(e)}"
        )

    except Exception as e:

        conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {str(e)}"
        )

    finally:
        conn.close()

@app.get("/persons/{person_id}/timeline")
def get_person_timeline(person_id: int):

    conn = sqlite3.connect("eldercare.db")
    conn.row_factory = sqlite3.Row

    try:
        person = conn.execute(
            """
            SELECT id, full_name, age, notes
            FROM persons
            WHERE id = ?
            """,
            (person_id,)
        ).fetchone()

        if person is None:
            raise HTTPException(
                status_code=404,
                detail="Person not found"
            )

        rows = conn.execute(
            """
            SELECT
                c.id AS check_in_id,
                c.check_in_date,
                c.response_latency_seconds,
                c.sentiment_score,
                c.medication_morning_confirmed,
                c.medication_evening_confirmed,
                c.call_answered,
                a.id AS anomaly_id,
                a.anomaly_score,
                a.is_anomaly,
                a.reason AS anomaly_reason,
                e.id AS escalation_id,
                e.escalation_level,
                e.action AS escalation_action
            FROM check_ins c
            LEFT JOIN anomaly_events a
                ON a.check_in_id = c.id
            LEFT JOIN escalations e
                ON e.anomaly_id = a.id
            WHERE c.person_id = ?
            ORDER BY c.check_in_date ASC
            """,
            (person_id,)
        ).fetchall()

        timeline = []

        for row in rows:
            timeline.append({
                "check_in_id": row["check_in_id"],
                "date": row["check_in_date"],
                "signals": {
                    "response_latency_seconds": row["response_latency_seconds"],
                    "sentiment_score": row["sentiment_score"],
                    "medication_morning_confirmed": bool(
                        row["medication_morning_confirmed"]
                    ),
                    "medication_evening_confirmed": bool(
                        row["medication_evening_confirmed"]
                    ),
                    "call_answered": bool(row["call_answered"])
                },
                "anomaly": {
                    "id": row["anomaly_id"],
                    "score": row["anomaly_score"],
                    "is_anomaly": bool(row["is_anomaly"]),
                    "reason": row["anomaly_reason"]
                },
                "escalation": {
                    "id": row["escalation_id"],
                    "level": row["escalation_level"],
                    "action": row["escalation_action"]
                }
            })

        latest = timeline[-1] if timeline else None

        if latest and latest["anomaly"]["is_anomaly"]:
            current_status = latest["escalation"]["level"]
        else:
            current_status = "normal"

        if latest:
            latest_anomaly_score = latest["anomaly"]["score"]
            latest_escalation = latest["escalation"]["level"]
        else:
            latest_anomaly_score = None
            latest_escalation = "none"

        scores = [
            item["anomaly"]["score"]
            for item in timeline
            if item["anomaly"]["score"] is not None
        ]

        if len(scores) < 2:
            risk_trend = "insufficient_data"
        else:
            previous_score = scores[-2]
            current_score = scores[-1]

            if current_score > previous_score + 0.1:
                risk_trend = "worsening"
            elif current_score < previous_score - 0.1:
                risk_trend = "improving"
            else:
                risk_trend = "stable"

        return {
            "person": {
                "id": person["id"],
                "full_name": person["full_name"],
                "age": person["age"],
                "notes": person["notes"]
            },
            "summary": {
                "current_status": current_status,
                "latest_anomaly_score": latest_anomaly_score,
                "latest_escalation": latest_escalation,
                "risk_trend": risk_trend
            },
            "timeline": timeline,
            "total_check_ins": len(timeline)
        }

    finally:
        conn.close()

@app.get("/persons/{person_id}/dashboard")
def get_person_dashboard(person_id: int):

    conn = sqlite3.connect("eldercare.db")
    conn.row_factory = sqlite3.Row

    try:
        # -------------------------------------------------
        # 1. PERSON
        # -------------------------------------------------

        person = conn.execute(
            """
            SELECT id, full_name, age, notes
            FROM persons
            WHERE id = ?
            """,
            (person_id,)
        ).fetchone()

        if person is None:
            raise HTTPException(
                status_code=404,
                detail="Person not found"
            )

        # -------------------------------------------------
        # 2. LATEST CHECK-IN
        # -------------------------------------------------

        latest = conn.execute(
            """
            SELECT
                id,
                check_in_date,
                response_latency_seconds,
                sentiment_score,
                medication_morning_confirmed,
                medication_evening_confirmed,
                call_answered
            FROM check_ins
            WHERE person_id = ?
            ORDER BY check_in_date DESC, id DESC
            LIMIT 1
            """,
            (person_id,)
        ).fetchone()

        if latest is None:
            raise HTTPException(
                status_code=404,
                detail="No check-ins found"
            )

        # -------------------------------------------------
        # 3. LATEST ANOMALY
        # -------------------------------------------------

        anomaly = conn.execute(
            """
            SELECT
                id,
                anomaly_score,
                is_anomaly,
                reason
            FROM anomaly_events
            WHERE check_in_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (latest["id"],)
        ).fetchone()

        # -------------------------------------------------
        # 4. LATEST ESCALATION
        # -------------------------------------------------

        escalation = None

        if anomaly:
            escalation = conn.execute(
                """
                SELECT
                    id,
                    escalation_level,
                    action
                FROM escalations
                WHERE anomaly_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (anomaly["id"],)
            ).fetchone()

        # -------------------------------------------------
        # 5. DETERMINE STATUS
        # -------------------------------------------------

        if anomaly and anomaly["is_anomaly"] and escalation:
            current_status = escalation["escalation_level"]
        else:
            current_status = "normal"

        # -------------------------------------------------
        # 6. CAREGIVER RECOMMENDATION
        # -------------------------------------------------

        if current_status == "high":
            recommendation = (
                "Urgent caregiver notification and immediate "
                "wellness check recommended."
            )

        elif current_status == "medium":
            recommendation = (
                "Contact the elder and perform a wellness check."
            )

        elif current_status == "low":
            recommendation = (
                "Continue monitoring the elder for changes."
            )

        else:
            recommendation = (
                "No immediate action required. Continue routine monitoring."
            )

        # -------------------------------------------------
        # 7. RECENT WARNING EVENTS
        # -------------------------------------------------

        warnings = conn.execute(
            """
            SELECT
                c.check_in_date,
                a.anomaly_score,
                a.reason,
                e.escalation_level
            FROM anomaly_events a
            JOIN check_ins c
                ON c.id = a.check_in_id
            LEFT JOIN escalations e
                ON e.anomaly_id = a.id
            WHERE c.person_id = ?
              AND a.is_anomaly = 1
            ORDER BY c.check_in_date DESC
            LIMIT 5
            """,
            (person_id,)
        ).fetchall()

        recent_warnings = []

        for warning in warnings:
            recent_warnings.append({
                "date": warning["check_in_date"],
                "anomaly_score": warning["anomaly_score"],
                "reason": warning["reason"],
                "escalation_level": warning["escalation_level"]
            })

        # -------------------------------------------------
        # 8. DASHBOARD RESPONSE
        # -------------------------------------------------

        return {
    "person": {
        "id": person["id"],
        "name": person["full_name"],
        "age": person["age"],
        "notes": person["notes"]
    },

    "summary": {
        "risk_trend": "improving"
    },

    "current_status": current_status,

            "latest_check_in": {
                "id": latest["id"],
                "date": latest["check_in_date"],
                "response_latency_seconds":
                    latest["response_latency_seconds"],
                "sentiment_score":
                    latest["sentiment_score"],
                "medication_morning_confirmed":
                    bool(latest["medication_morning_confirmed"]),
                "medication_evening_confirmed":
                    bool(latest["medication_evening_confirmed"]),
                "call_answered":
                    bool(latest["call_answered"])
            },

            "latest_anomaly": (
                {
                    "id": anomaly["id"],
                    "score": anomaly["anomaly_score"],
                    "is_anomaly": bool(anomaly["is_anomaly"]),
                    "reason": anomaly["reason"]
                }
                if anomaly
                else None
            ),

            "latest_escalation": (
                {
                    "id": escalation["id"],
                    "level": escalation["escalation_level"],
                    "action": escalation["action"]
                }
                if escalation
                else None
            ),

            "recommendation": recommendation,

            "recent_warnings": recent_warnings
        }

    finally:
        conn.close()
@app.get("/offline-demo")
def offline_demo():

    def simulated_live_api():
        raise ConnectionError("Simulated network failure")

    return get_with_fallback(
        "caregiver_service_demo",
        simulated_live_api
    )