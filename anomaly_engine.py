import sqlite3
from statistics import mean, stdev


DB_PATH = "eldercare.db"


def get_baseline(conn, person_id, before_date):
    """
    Use all check-ins before the date being scored
    to establish the person's normal baseline.
    """

    rows = conn.execute(
        """
        SELECT
            response_latency_seconds,
            sentiment_score,
            medication_morning_confirmed,
            medication_evening_confirmed,
            call_answered
        FROM check_ins
        WHERE person_id = ?
          AND check_in_date < ?
        ORDER BY check_in_date
        """,
        (person_id, before_date)
    ).fetchall()

    if not rows:
        raise ValueError("Not enough historical data for baseline.")

    latency_values = [row[0] for row in rows]
    sentiment_values = [row[1] for row in rows]

    return {
        "latency_mean": mean(latency_values),
        "latency_std": stdev(latency_values)
            if len(latency_values) > 1 else 1.0,

        "sentiment_mean": mean(sentiment_values),
        "sentiment_std": stdev(sentiment_values)
            if len(sentiment_values) > 1 else 0.1,

        "medication_adherence": mean(
            (
                row[2] + row[3]
            ) / 2
            for row in rows
        ),

        "call_success_rate": mean(
            row[4] for row in rows
        ),

        "sample_count": len(rows)
    }


def clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def calculate_latency_signal(current, baseline):
    """
    Measures how unusual today's response latency is.

    Uses relative increase from the person's baseline.
    """

    baseline_latency = baseline["latency_mean"]

    if baseline_latency <= 0:
        return 0.0

    increase = (
        current - baseline_latency
    ) / baseline_latency

    # Ignore faster responses.
    if increase <= 0:
        return 0.0

    # 100% increase or more = maximum signal.
    return clamp(increase)


def calculate_sentiment_signal(current, baseline):
    """
    Measures deterioration in sentiment compared with baseline.
    """

    baseline_sentiment = baseline["sentiment_mean"]

    drop = baseline_sentiment - current

    if drop <= 0:
        return 0.0

    # A 1-point sentiment drop represents maximum signal.
    return clamp(drop)


def calculate_medication_signal(
    morning_confirmed,
    evening_confirmed,
    baseline
):
    """
    Detects medication adherence deterioration.
    """

    current_adherence = (
        morning_confirmed + evening_confirmed
    ) / 2

    baseline_adherence = baseline["medication_adherence"]

    deterioration = (
        baseline_adherence - current_adherence
    )

    if deterioration <= 0:
        return 0.0

    return clamp(deterioration)


def calculate_call_signal(call_answered, baseline):
    """
    Detects deterioration in call-answer behavior.
    """

    baseline_success = baseline["call_success_rate"]

    current_success = 1 if call_answered else 0

    deterioration = baseline_success - current_success

    if deterioration <= 0:
        return 0.0

    return clamp(deterioration)


def score_checkin(
    conn,
    person_id,
    check_in_date
):
    """
    Calculate today's anomaly score using only
    historical data before today's check-in.
    """

    baseline = get_baseline(
        conn,
        person_id,
        check_in_date
    )

    row = conn.execute(
        """
        SELECT
            id,
            response_latency_seconds,
            sentiment_score,
            medication_morning_confirmed,
            medication_evening_confirmed,
            call_answered
        FROM check_ins
        WHERE person_id = ?
          AND check_in_date = ?
        """,
        (person_id, check_in_date)
    ).fetchone()

    if row is None:
        raise ValueError("Check-in not found.")

    (
        check_in_id,
        latency,
        sentiment,
        morning_med,
        evening_med,
        call_answered
    ) = row

    # -----------------------------------------------------
    # INDIVIDUAL SIGNAL SCORES
    # -----------------------------------------------------

    latency_signal = calculate_latency_signal(
        latency,
        baseline
    )

    sentiment_signal = calculate_sentiment_signal(
        sentiment,
        baseline
    )

    medication_signal = calculate_medication_signal(
        morning_med,
        evening_med,
        baseline
    )

    call_signal = calculate_call_signal(
        call_answered,
        baseline
    )

    # -----------------------------------------------------
    # WEIGHTED SCORE
    #
    # Latency       40%
    # Sentiment     40%
    # Medication    10%
    # Call behavior 10%
    # -----------------------------------------------------

    score = (
        latency_signal * 0.40
        + sentiment_signal * 0.40
        + medication_signal * 0.10
        + call_signal * 0.10
    )

    score = clamp(score)

    # -----------------------------------------------------
    # CLASSIFICATION
    # -----------------------------------------------------

    if score >= 0.70:
        level = "high"

    elif score >= 0.50:
        level = "medium"

    elif score >= 0.30:
        level = "low"

    else:
        level = "normal"

    # -----------------------------------------------------
    # EXPLANATION
    # -----------------------------------------------------

    reasons = []

    if latency_signal >= 0.30:
        reasons.append(
            f"response latency increased "
            f"from {baseline['latency_mean']:.1f}s "
            f"baseline to {latency:.1f}s"
        )

    if sentiment_signal >= 0.30:
        reasons.append(
            f"sentiment dropped from "
            f"{baseline['sentiment_mean']:.2f} "
            f"baseline to {sentiment:.2f}"
        )

    if medication_signal > 0:
        reasons.append(
            "medication adherence decreased"
        )

    if call_signal > 0:
        reasons.append(
            "call-answer behavior deteriorated"
        )

    if not reasons:
        reasons.append(
            "signals remain within normal range"
        )

    reason = "; ".join(reasons)

    return {
        "check_in_id": check_in_id,
        "person_id": person_id,
        "date": check_in_date,

        "anomaly_score": round(score, 3),
        "level": level,

        "signals": {
            "latency": round(latency_signal, 3),
            "sentiment": round(sentiment_signal, 3),
            "medication": round(medication_signal, 3),
            "call": round(call_signal, 3)
        },

        "baseline": baseline,

        "reason": reason
    }


def save_anomaly_result(conn, result):
    """
    Store the scoring result in anomaly_events.
    """

    is_anomaly = (
        1 if result["level"] != "normal" else 0
    )

    cursor = conn.execute(
        """
        INSERT INTO anomaly_events (
            check_in_id,
            anomaly_score,
            is_anomaly,
            reason,
            scoring_version
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            result["check_in_id"],
            result["anomaly_score"],
            is_anomaly,
            result["reason"],
            "v1"
        )
    )

    conn.commit()

    return cursor.lastrowid


def main():

    conn = sqlite3.connect(DB_PATH)

    # Find Ram
    person = conn.execute(
        """
        SELECT id, full_name
        FROM persons
        WHERE full_name = ?
        """,
        ("Ram Prakash Verma",)
    ).fetchone()

    if person is None:
        raise ValueError(
            "Ram Prakash Verma not found."
        )

    person_id, name = person

    # Score the final day.
    result = score_checkin(
        conn,
        person_id,
        "2026-08-16"
    )

    anomaly_id = save_anomaly_result(
        conn,
        result
    )

    print("\n" + "=" * 65)
    print("ANOMALY ANALYSIS")
    print("=" * 65)

    print(f"\nPerson: {name}")
    print(f"Date: {result['date']}")

    print(
        f"\nAnomaly score: "
        f"{result['anomaly_score']:.3f}"
    )

    print(
        f"Classification: "
        f"{result['level'].upper()}"
    )

    print("\nSignal contributions:")

    for signal, value in result["signals"].items():
        print(
            f"  {signal:<12}: {value:.3f}"
        )

    print("\nBaseline:")

    print(
        f"  Response latency: "
        f"{result['baseline']['latency_mean']:.2f}s"
    )

    print(
        f"  Sentiment: "
        f"{result['baseline']['sentiment_mean']:.2f}"
    )

    print(
        f"  Medication adherence: "
        f"{result['baseline']['medication_adherence']:.2f}"
    )

    print(
        f"  Call success rate: "
        f"{result['baseline']['call_success_rate']:.2f}"
    )

    print("\nReason:")
    print(f"  {result['reason']}")

    print(f"\nSaved anomaly ID: {anomaly_id}")

    print("\n" + "=" * 65)

    conn.close()


if __name__ == "__main__":
    main()