def test_reject_blank_capture(db_client):
    response = db_client.post(
        "/api/v1/captures",
        json={"source_type": "text", "content": "   "},
    )
    assert response.status_code == 422


def test_reject_invalid_source_type(db_client):
    response = db_client.post(
        "/api/v1/captures",
        json={"source_type": "unknown", "content": "Test capture"},
    )
    assert response.status_code == 422


def test_reject_missing_content(db_client):
    response = db_client.post(
        "/api/v1/captures",
        json={"source_type": "text"},
    )
    assert response.status_code == 422


def test_create_capture(db_client):
    response = db_client.post(
        "/api/v1/captures",
        json={
            "source_type": "text",
            "title": "First integration test",
            "content": "Capture an idea for the PCC.",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "First integration test"
    assert data["content"] == "Capture an idea for the PCC."
    assert data["status"] == "pending"
    assert data["id"]


def test_list_captures(db_client):
    create_response = db_client.post(
        "/api/v1/captures",
        json={
            "source_type": "url",
            "content": "https://example.com/article",
        },
    )
    assert create_response.status_code == 201

    response = db_client.get("/api/v1/captures")

    assert response.status_code == 200
    captures = response.json()
    assert len(captures) == 1
    assert captures[0]["id"] == create_response.json()["id"]
