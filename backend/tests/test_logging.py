from datetime import UTC, datetime

from app.api.admin_ops import log_view
from app.core.logging import redact
from app.models.account import RequestLog
from app.models.billing import GenerationJob


def test_redact_removes_auth_cookie_and_proxy_credentials() -> None:
    message = (
        "Authorization: Bearer abc.def.ghi\n"
        "Cookie: ims_sid=secret; aux_sid=secret2\n"
        "proxy=https://user:password@example.com:443"
    )

    redacted = redact(message)

    assert isinstance(redacted, str)
    assert "abc.def.ghi" not in redacted
    assert "ims_sid" not in redacted
    assert "password" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_log_view_model_label_channel_and_strips_secrets() -> None:
    job = GenerationJob(
        id="job-1",
        user_id=1,
        idempotency_key="idem-1",
        kind="image",
        model="nano-banana-pro",
        prompt="a cat",
        params={"resolution": "2K", "cookie": "secret-cookie", "aspect_ratio": "1:1"},
        cost=10,
        source="panel",
        result_urls=["https://cdn.example/a.png"],
    )
    row = RequestLog(
        job_id="job-1",
        account_hash="abc",
        egress_id="eg-1",
        endpoint="generate",
        status_code=200,
        latency_ms=12,
        outcome="ok",
        created_at=datetime.now(UTC),
    )
    view = log_view(row, job, {"nano-banana-pro": "Pro 模型 Nano Banana Pro"})
    assert view["model_label"] == "Nano Banana Pro 2K 1:1"
    assert view["channel"] == "面板"
    assert view["prompt"] == "a cat"
    assert "cookie" not in view["params"]
    assert view["params"]["resolution"] == "2K"
    assert view["result_urls"] == ["https://cdn.example/a.png"]
    assert view["upstream_urls"] == ["https://cdn.example/a.png"]
    assert "secret-cookie" not in str(view)

    job.params = {
        "resolution": "2K",
        "upstream_urls": ["https://adobe.invalid/out-1.png", "https://adobe.invalid/out-2.png"],
    }
    with_up = log_view(row, job, {"nano-banana-pro": "Pro 模型 Nano Banana Pro"})
    assert with_up["upstream_urls"] == [
        "https://adobe.invalid/out-1.png",
        "https://adobe.invalid/out-2.png",
    ]
    assert "upstream_urls" not in with_up["params"]

    banana = GenerationJob(
        id="job-2",
        user_id=1,
        idempotency_key="idem-2",
        kind="image",
        model="nano-banana",
        prompt="a cat",
        params={"resolution": "1K"},
        cost=8,
        source="panel",
        result_urls=[],
    )
    banana_row = RequestLog(
        job_id="job-2",
        account_hash="abc",
        egress_id="eg-1",
        endpoint="generate",
        status_code=200,
        latency_ms=12,
        outcome="ok",
        created_at=datetime.now(UTC),
    )
    banana_view = log_view(banana_row, banana, {"nano-banana": "普通模型 Nano Banana / V2"})
    assert banana_view["model_label"] == "Nano Banana 1K"
    assert banana_view["trace"] == []


def test_sanitize_body_redacts_tokens_and_keeps_status() -> None:
    from app.adobe.trace import UpstreamTrace, sanitize_body

    cleaned = sanitize_body(
        {"access_token": "secret-at", "status": "RUNNING", "cookie": "ims_sid=x"}
    )
    assert cleaned["access_token"] == "[REDACTED]"
    assert cleaned["cookie"] == "[REDACTED]"
    assert cleaned["status"] == "RUNNING"

    rec = UpstreamTrace()
    rec.record(
        "ims_clio",
        method="POST",
        url="https://adobeid-na1.services.adobe.com/ims/check/v6/token",
        status_code=200,
        body={"access_token": "abc.def", "expires_in": 3600},
    )
    rec.record(
        "submit",
        method="POST",
        url="https://firefly-3p.ff.adobe.io/x",
        status_code=200,
        body={"status": "ok"},
    )
    exported = rec.export()
    assert exported[0]["body"]["access_token"] == "[REDACTED]"
    assert exported[0]["body"]["expires_in"] == 3600
    row = RequestLog(
        job_id="job-2",
        account_hash="abc",
        egress_id="eg-1",
        endpoint="generate",
        status_code=200,
        latency_ms=12,
        outcome="ok",
        created_at=datetime.now(UTC),
        trace=exported,
    )
    view = log_view(
        row,
        GenerationJob(
            id="job-3",
            user_id=1,
            idempotency_key="idem-3",
            kind="image",
            model="nano-banana",
            prompt="a cat",
            params={"resolution": "1K"},
            cost=8,
            source="panel",
            result_urls=[],
        ),
        {"nano-banana": "普通模型 Nano Banana / V2"},
    )
    assert view["trace"][0]["step"] == "ims_clio"
    assert "abc.def" not in str(view)
