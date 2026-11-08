"""A fake CJ API built from the response shapes in CJ's API 2.0 docs."""

import json

import httpx

TOKEN = {
    "openId": 123,
    "accessToken": "tok-abc",
    "accessTokenExpiryDate": "2099-05-01T09:16:33+08:00",
    "refreshToken": "ref-abc",
    "refreshTokenExpiryDate": "2099-05-01T09:16:33+08:00",
    "createDate": "2026-11-09T09:16:33+08:00",
}


def product(pid: str, name: str, price: str = "4.50") -> dict:
    return {
        "id": pid,
        "nameEn": name,
        "sku": f"SKU-{pid}",
        "bigImage": f"https://cf.cjdropshipping.com/{pid}.jpg",
        "sellPrice": price,
    }


def ok(data) -> dict:
    return {"code": 200, "result": True, "message": "Success", "data": data}


class FakeCJ:
    def __init__(self, products: list[dict] | None = None, freight_price: str = "3.20"):
        self.products = products if products is not None else [product("P1", "Dog Bowl")]
        self.freight_price = freight_price
        self.calls: list[str] = []
        self.status_for: dict[str, int] = {}  # path suffix → forced HTTP status

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api2.0/v1/")
        self.calls.append(path)
        if path in self.status_for:
            return httpx.Response(self.status_for[path], json={"code": 1600200, "result": False})
        if path != "authentication/getAccessToken":
            assert request.headers["CJ-Access-Token"] == "tok-abc"
        if path == "authentication/getAccessToken":
            assert json.loads(request.content) == {"apiKey": "CJ123@api@secret"}
            return httpx.Response(200, json=ok(TOKEN))
        if path == "product/listV2":
            return httpx.Response(200, json=ok({"content": [{"productList": self.products}]}))
        if path == "product/query":
            pid = request.url.params["pid"]
            variants = [{"vid": f"V-{pid}", "variantSellPrice": 4.5}]
            return httpx.Response(200, json=ok({"pid": pid, "variants": variants}))
        if path == "logistic/freightCalculate":
            return httpx.Response(
                200,
                json=ok(
                    [
                        {"logisticName": "Slow", "logisticPrice": 1.10, "logisticAging": "20-40"},
                        {
                            "logisticName": "USPS+",
                            "logisticPrice": float(self.freight_price),
                            "logisticAging": "7-12",
                        },
                        {"logisticName": "Express", "logisticPrice": 9.00, "logisticAging": "3-5"},
                    ]
                ),
            )
        raise AssertionError(f"unexpected path {path}")

    def http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))
