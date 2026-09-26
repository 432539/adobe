import base64
import json

import pytest
from pydantic import ValidationError

from app.arp.models import ArpPublishItem, decode_arp_token


def make_token() -> str:
    payload = {"sid": "sid", "ark": "ark", "bfp": "bfp", "ftr": "id_ts__UDF43-xx=-3-v2_tt"}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def make_item() -> ArpPublishItem:
    return ArpPublishItem.model_validate(
        {
            "t": make_token(),
            "proxy_url": "socks5h://user:password@proxy.example:1080",
            "egress_id": "residential-1",
            "ua": "Mozilla/5.0 Chrome/148.0.0.0 Safari/537.36",
            "ch": {
                "platform": "Windows",
                "platformVersion": "15.0.0",
                "fullVersionList": [{"brand": "Google Chrome", "version": "148.0.0.0"}],
                "architecture": "x86",
                "bitness": "64",
            },
        }
    )


def test_decode_arp_token_requires_all_four_parts() -> None:
    decoded = decode_arp_token(make_token())

    assert decoded["sid"] == "sid"
    assert decoded["ftr"] == "id_ts__UDF43-xx=-3-v2_tt"


def test_publish_item_hides_secrets_in_repr() -> None:
    item = make_item()

    rendered = repr(item)
    assert "password" not in rendered
    assert make_token() not in rendered


def test_publish_item_requires_proxy_url() -> None:
    data = make_item().model_dump()
    data["proxy_url"] = "   "

    with pytest.raises(ValidationError, match="proxy_url"):
        ArpPublishItem.model_validate(data)


def test_publish_item_requires_chrome_148() -> None:
    data = make_item().model_dump()
    data["ua"] = "Mozilla/5.0 Chrome/147.0.0.0 Safari/537.36"

    with pytest.raises(ValidationError, match="Chrome 148"):
        ArpPublishItem.model_validate(data)


def test_decode_arp_token_rejects_missing_part() -> None:
    token = base64.b64encode(json.dumps({"sid": "sid"}).encode()).decode()

    with pytest.raises(ValueError, match="missing required parts"):
        decode_arp_token(token)


def test_decode_arp_token_rejects_ftr_without_v2_tt() -> None:
    token = base64.b64encode(
        json.dumps({"sid": "sid", "ark": "ark", "bfp": "bfp", "ftr": "id_ts__UDF43-xx"}).encode()
    ).decode()

    with pytest.raises(ValueError, match="v2_tt"):
        decode_arp_token(token)
