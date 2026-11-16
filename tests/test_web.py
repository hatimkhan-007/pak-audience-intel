import pytest

PAGES = ["/", "/content", "/audience", "/segments", "/anomalies", "/recommendations", "/posts", "/posts/P0001",
         "/comments", "/youtube", "/posts/YT-UYaY2Kb_PKI", "/comments?platform=YouTube", "/analyze", "/database", "/about", "/?platform=Instagram", "/content?platform=TikTok",
         "/comments?q=price&topic=Price%20inquiry", "/export/posts.csv", "/export/recommendations.csv", "/healthz"]

@pytest.mark.parametrize("url", PAGES)
def test_pages_ok(client, url):
    assert client.get(url).status_code == 200

@pytest.mark.parametrize("url", ["/?platform=Nope", "/segments?platform=Nope", "/content?brand=Nope", "/audience?brand=Nope", "/anomalies?brand=Nope"])
def test_empty_filters_do_not_crash(client, url):
    assert client.get(url).status_code == 200

def test_404(client):
    assert client.get("/posts/NOPE").status_code == 404

def test_classifier_api(client):
    r = client.post("/api/analyze", json={"text": "Price bohat zyada hai"})
    assert r.status_code == 200 and r.json["topic"] == "Price concern" and r.json["segment"]
    assert client.post("/api/analyze", json={"text": ""}).status_code == 400

@pytest.mark.parametrize("sql", ["DROP TABLE post", "SELECT 1; DELETE FROM post", "DELETE FROM post", "PRAGMA writable_schema=1"])
def test_sql_console_is_read_only(client, sql):
    assert client.post("/api/sql", json={"sql": sql}).status_code == 400

def test_sql_console_select(client):
    r = client.post("/api/sql", json={"sql": "SELECT COUNT(*) AS n FROM post"})
    assert r.status_code == 200 and r.json["rows"][0][0] == 501


def test_analysis_pages_exclude_youtube_but_explorers_include_it(client):
    assert b"YouTube" not in client.get("/segments").data.split(b"<main")[1].split(b"</form>")[0]   # no YouTube in filter options
    assert b">YouTube<" in client.get("/comments").data
